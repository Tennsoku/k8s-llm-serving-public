# Lab 1: Offline Inference

## Outcome

Load one model through the vLLM Python API, separate initialization from generation, submit several prompts in one call, and record token, timing, memory, repeatability, and shutdown evidence.

Run every command below from `labs/vllm-basics/`.

## Fixed inputs and measurement boundaries

The script contains four source-controlled prompt sets:

| Case | Prompt set | Prompt count | Max output tokens per request |
|---|---|---:|---:|
| A | first short prompt from B | 1 | 32 |
| B | default short prompts | 4 | 32 |
| C | B plus four additional short prompts | 8 | 64 |
| D | four medium prompts | 4 | 128 |

`--max-tokens` is a ceiling for each request, not the actual batch output count. The authoritative input count is `len(RequestOutput.prompt_token_ids)`; the script prints the per-request list and total. Do not derive prompt-token counts by multiplying the progress bar's rounded `input toks/s` by `generation_seconds`.

The timers mean:

- `model_initialization_seconds`: construction of `LLM`, including model/engine initialization.
- `generation_seconds`: one complete `llm.generate(...)` call. It includes prompt rendering/tokenization and engine execution, but excludes model initialization and result printing.
- Whole-process wall time from `time`, if collected separately: imports, initialization, generation, printing, and shutdown. Do not put this value in the matrix's `Elapsed seconds` column.

## 1. Fix the runtime context

Use the same container/environment recorded by Lab 0. Point `MODEL` at either the pinned local mirror or the Hugging Face model ID:

```bash
export MODEL=/models/Qwen2.5-0.5B-Instruct
export LAB1_GPU_MEMORY_UTILIZATION=0.15
export VLLM_LABS_REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB1_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-lab1"
export LAB1_RUN_DIR="${VLLM_LABS_REPO_ROOT}/artifacts/private/m1/${LAB1_RUN_ID}"
mkdir -p "${LAB1_RUN_DIR}"
```

When using `Qwen/Qwen2.5-0.5B-Instruct` from the Hub, also export the immutable `MODEL_REVISION`. For a local model directory, record the source commit/checksum in [observations.md](observations.md); do not assume the directory name proves its revision.

Before loading the model, retain:

```bash
date --iso-8601=seconds | tee "${LAB1_RUN_DIR}/pre-load-time.txt"
nvidia-smi | tee "${LAB1_RUN_DIR}/pre-load-nvidia-smi.txt"
free -b | tee "${LAB1_RUN_DIR}/pre-load-system-memory.txt"
```

On DGX Spark, GPU and CPU share unified memory and `nvidia-smi` may report framebuffer memory as `N/A`. Preserve that output, but do not relabel it as zero usage or independent discrete-GPU VRAM.

## 2. Run the four matrix cases

The following Bash helper preserves the complete log and the Python exit code:

```bash
run_lab1_case() {
  local case_name="$1"
  local max_tokens="$2"
  local log="${LAB1_RUN_DIR}/case-${case_name}.log"

  set -o pipefail
  python lab1-offline-inference/offline_inference.py \
    --case "${case_name}" \
    --max-tokens "${max_tokens}" \
    --gpu-memory-utilization "${LAB1_GPU_MEMORY_UTILIZATION}" \
    2>&1 | tee "${log}"
  local rc=${PIPESTATUS[0]}
  printf 'exit_code=%d\n' "${rc}" | tee -a "${log}"
  return "${rc}"
}
```

Run the required cases without changing model, dtype, seed, or memory setting:

```bash
run_lab1_case A 32
run_lab1_case B 32
run_lab1_case C 64
run_lab1_case D 128
```

For each case, copy these exact fields into the matrix:

- `prompt_tokens_per_prompt=[...]`
- `prompt_tokens_total=...`
- `output_tokens_total=...`
- `generation_seconds=...`
- process `exit_code`
- any Triton JIT, OOM, timeout, teardown, or other warning

The A/B comparison changes prompt count while keeping the shared prompt and output ceiling compatible. C and D are exploratory shape cases and change more than one dimension relative to B, so do not use them alone to claim a causal effect.

## 3. Run controlled comparisons

Compare first and subsequent generation against the same loaded engine:

```bash
set -o pipefail
python lab1-offline-inference/offline_inference.py \
  --case B \
  --max-tokens 32 \
  --generation-repeats 2 \
  --gpu-memory-utilization "${LAB1_GPU_MEMORY_UTILIZATION}" \
  2>&1 | tee "${LAB1_RUN_DIR}/case-B-same-engine-repeat.log"
printf 'exit_code=%d\n' "${PIPESTATUS[0]}" | \
  tee -a "${LAB1_RUN_DIR}/case-B-same-engine-repeat.log"
```

`generation_index=1` may include first-shape JIT/graph/cache work; `generation_index=2` is the same prompt set and sampling configuration on the same engine. Compare both elapsed values and outputs. Temperature zero plus a fixed seed improves repeatability but does not prove cross-version or cross-kernel bitwise determinism.

The required A–D matrix does not isolate the output ceiling. Run this companion case when interpreting the effect of `max_tokens`:

```bash
python lab1-offline-inference/offline_inference.py \
  --case B --max-tokens 128 \
  --gpu-memory-utilization "${LAB1_GPU_MEMORY_UTILIZATION}" \
  2>&1 | tee "${LAB1_RUN_DIR}/case-B-max128-control.log"
```

Compare it only with Case B. Remember that early EOS can make actual output lengths smaller than either ceiling.

## 4. Capture memory during generation

The script records CUDA-visible free/total memory immediately before load, after load, and after every generation. For a timestamped external trace, run this in a second shell while a case is active:

```bash
while true; do
  date --iso-8601=seconds
  free -b | sed -n '1,2p'
  if [[ -r /sys/fs/cgroup/memory.current ]]; then
    printf 'cgroup_memory_current=%s\n' "$(</sys/fs/cgroup/memory.current)"
  fi
  sleep 1
done | tee "${LAB1_RUN_DIR}/memory-samples.log"
```

Stop the sampler with Ctrl-C after generation. Record the sampling interval and whether the sample actually overlapped generation. A short 0.2-second case may complete between one-second samples; use the longer cases or repeat generation when collecting a peak. Keep `nvidia-smi --loop=1` as supplemental GPU evidence, but treat unsupported memory fields as unavailable.

## Expected result and errors

A successful case prints the fixed case name, initialization time, every prompt/output, exact prompt/output token counts, generation time, and memory observations. It submits each case's prompt list through one `generate` call.

Classify failures by phase:

- Before `model_initialization_seconds`: environment, model path/revision, runtime compatibility, or allocation failure.
- Inside a generation iteration: request execution failure; retain the entire case as failed.
- After complete results: lifecycle/teardown deviation. Record the traceback and exit code separately from the successful generation observation.
- OOM, timeout, signal, or nonzero exit: never delete the log or silently replace the run.

A Hugging Face download or gated-model error is environment evidence, not a performance result. vLLM Python APIs and CLI arguments are version-sensitive; retain the exact vLLM/PyTorch versions and any adapted help output.

## Submission and review criteria

Submit:

- exact commands and uncropped per-case logs;
- completed [observations.md](observations.md);
- model/revision and runtime/container identity;
- timestamped memory evidence with its measurement method;
- same-engine first/repeat log;
- every exit code and error/deviation.

**Pass:** A–D use the fixed prompt sets; at least two prompts share one `generate` call; token counts come from returned token IDs; initialization and generation timing are separated; first and subsequent same-engine calls are compared; 32/128 output ceilings are compared with a controlled prompt set; unified-memory evidence is labeled accurately.

**Revise:** prompts are changed without recording them; progress-bar throughput is converted into token counts; whole-process time is reported as generation time; only successful logs are kept; memory values lack timestamps/methods; or one run is claimed deterministic.

**Human review:** Explain `LLM`, `SamplingParams`, prefill, decode, KV cache, first-run JIT/caching overhead, and which sampling settings affect output quality versus resource use.
