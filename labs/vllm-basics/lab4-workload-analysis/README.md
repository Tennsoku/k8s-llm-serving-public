# Lab 4: Workload Shape Analysis

## Outcome

Compare short/long input and output shapes under one fixed online-server configuration, using actual API token counts, client-side E2E latency, request/token throughput, sampled GPU evidence, memory evidence, and retained failures.

Run every command below from `labs/vllm-basics/`. This runner is non-streaming: it does not measure TTFT, ITL, or TPOT.

## 1. Freeze the environment and understand the cases

Keep the Lab 3 server running with the same model/revision, served name, dtype, memory utilization, maximum model length, and maximum sequence count. If any server setting changes, start a new comparison group.

Read [workload_cases.md](workload_cases.md). The exact prompt strings and repetition counts are source-controlled in `run_workloads.py:CASES`:

| Case | Intended shape | Output ceiling/request | Primary pressure |
|---|---|---:|---|
| `short-short` | 32–64 input tokens | 32 | request/runtime overhead |
| `short-long` | 32–64 input tokens | 512 | sustained decode |
| `long-short` | more than 2,000 input tokens | 32 | prefill |
| `long-long` | more than 2,000 input tokens | 512 | prefill, decode, KV-cache capacity |

These are hypotheses until the selected model's API response supplies actual `usage.prompt_tokens` and `usage.completion_tokens`. Words, characters, and `max_tokens` are not substitutes for actual token counts.

Set the client context:

```bash
export BASE_URL=http://127.0.0.1:8000
export SERVED_MODEL_NAME=qwen2.5-0.5b-instruct
export VLLM_LABS_REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB4_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-lab4"
export LAB4_RUN_DIR="${VLLM_LABS_REPO_ROOT}/artifacts/private/m1/${LAB4_RUN_ID}"
mkdir -p "${LAB4_RUN_DIR}/logs"
curl --fail --silent "${BASE_URL}/health"
```

Record the exact server command/log and the source commit containing `CASES` in [results/observations.md](results/observations.md).

## 2. Validate token shapes before comparison

Run one request per case into a separate shape-check CSV:

```bash
set -o pipefail
python lab4-workload-analysis/run_workloads.py \
  --base-url "${BASE_URL}" \
  --model "${SERVED_MODEL_NAME}" \
  --case all \
  --concurrency 1 \
  --requests 1 \
  --warmup 0 \
  --timeout 600 \
  --output "${LAB4_RUN_DIR}/shape-check.csv" \
  2>&1 | tee "${LAB4_RUN_DIR}/logs/shape-check.log"
printf 'exit_code=%d\n' "${PIPESTATUS[0]}" | \
  tee -a "${LAB4_RUN_DIR}/logs/shape-check.log"
```

Inspect `input_tokens_per_request`:

- both short cases should fall in the documented short range;
- both long cases should exceed 2,000 tokens;
- successful responses must contain nonzero API usage counts;
- actual output tokens may be below the ceiling because of EOS.

If a shape misses its range, adjust only that source prompt, commit/record the change, rerun the shape check, and use the new source consistently for all repetitions. Do not edit a prompt after measured rows already exist in the same comparison group.

A successful response with zero token usage means the required metric was unavailable or not parsed; it does not prove a zero-token request. Mark the shape run invalid until the API/runner supplies usage.

## 3. Run the fixed-concurrency shape comparison

The primary comparison holds concurrency at 8 and runs each case sequentially. Requests inside a case are concurrent; the four cases are not concurrent with one another.

```bash
for repetition in 1 2 3; do
  log="${LAB4_RUN_DIR}/logs/shape-comparison-rep-${repetition}.log"

  set -o pipefail
  python lab4-workload-analysis/run_workloads.py \
    --base-url "${BASE_URL}" \
    --model "${SERVED_MODEL_NAME}" \
    --case all \
    --concurrency 8 \
    --requests 16 \
    --warmup 1 \
    --timeout 600 \
    --sample-interval 0.5 \
    --output "${LAB4_RUN_DIR}/workload-results.csv" \
    2>&1 | tee "${log}"
  rc=${PIPESTATUS[0]}
  printf 'repetition=%d exit_code=%d\n' "${repetition}" "${rc}" | \
    tee -a "${log}"
done
```

Keep the case order fixed and note that later cases may benefit from already compiled kernels/caches. The per-case warm-up reduces but does not eliminate order and thermal effects. Compare all three repetitions; do not select only the most favorable row.

If a measured request fails, the runner writes the aggregate row and returns nonzero after completing the selected cases. If a warm-up fails, it exits before writing that case's measured row. In both situations the uniquely named log is required raw evidence.

## 4. Understand the recorded metrics

For successful measured requests in each case:

- `input_tokens_per_request` and `output_tokens_per_request` are averages from HTTP `usage`.
- token throughput is the total successful input/output tokens divided by measured case wall time.
- request throughput is successful requests divided by measured case wall time.
- latency is client-side non-streaming E2E over successful requests.
- p50/p95/p99 use successful requests only.
- blank GPU fields mean unavailable/unparseable telemetry, not zero.
- failures retain status/error in the case log and increment `failed_requests`.

`max_tokens=512` does not ensure 512 generated tokens. If short-long and long-long terminate much earlier, record the actual decode separation; change the prompt format only in a new controlled run group.

Because this client does not stream, it cannot establish which case has the highest TTFT or separate prefill time from queueing. You may write a TTFT candidate hypothesis, but confirmation requires the later streaming timestamp client or server-side TTFT metrics.

## 5. Capture DGX Spark memory and GPU evidence

The runner samples:

```text
nvidia-smi --query-gpu=memory.used,utilization.gpu
```

On GB10 unified memory, `memory.used` may be unsupported. The current parser then leaves both sampled fields blank. Retain the blank rather than converting it to zero, and add timestamped system/cgroup evidence from a second shell:

```bash
while true; do
  date --iso-8601=seconds
  free -b | sed -n '1,2p'
  if [[ -r /sys/fs/cgroup/memory.current ]]; then
    printf 'cgroup_memory_current=%s\n' "$(</sys/fs/cgroup/memory.current)"
  fi
  sleep 1
done | tee "${LAB4_RUN_DIR}/memory-samples.log"
```

Start it before a measured invocation and stop it afterward. Record the sampling interval, process/cgroup scope, and clock alignment with the client/server logs. Do not describe system or CUDA-visible unified-memory values as independent discrete-GPU VRAM.

## 6. Bound a workload-specific concurrency knee

The fixed-concurrency comparison explains shape differences but cannot by itself locate saturation. Select the case with the strongest observed latency/memory pressure and sweep concurrency without changing its prompt or output ceiling:

```bash
export LAB4_KNEE_CASE=long-long

for concurrency in 1 2 4 8 16; do
  level_failed=0

  for repetition in 1 2 3; do
    log="${LAB4_RUN_DIR}/logs/knee-${LAB4_KNEE_CASE}-rep-${repetition}-c-${concurrency}.log"

    set -o pipefail
    python lab4-workload-analysis/run_workloads.py \
      --base-url "${BASE_URL}" \
      --model "${SERVED_MODEL_NAME}" \
      --case "${LAB4_KNEE_CASE}" \
      --concurrency "${concurrency}" \
      --requests 16 \
      --warmup 1 \
      --timeout 600 \
      --sample-interval 0.5 \
      --output "${LAB4_RUN_DIR}/knee-results.csv" \
      2>&1 | tee "${log}"
    rc=${PIPESTATUS[0]}
    printf 'repetition=%d concurrency=%d exit_code=%d\n' \
      "${repetition}" "${concurrency}" "${rc}" | tee -a "${log}"
    (( rc == 0 )) || level_failed=1
  done

  if (( level_failed )); then
    printf 'stopping_after_failed_concurrency=%d\n' "${concurrency}"
    break
  fi
done
```

Choose `LAB4_KNEE_CASE` from observed evidence and record why. Stop escalation when OOM, repeated timeout, service instability, or clearly degraded useful throughput establishes a capacity bound; retain that failed boundary. Do not infer a knee for the other shapes from this one selected-case sweep.

## Submission and review criteria

Submit:

- fixed server/model/runtime configuration and source commit;
- shape-check CSV/log;
- three fixed-concurrency rows per case with uniquely named logs/exit codes;
- selected-case concurrency-sweep CSV/logs;
- timestamped GPU/system/cgroup evidence or an explicit unsupported-telemetry statement;
- OOM/failure/recovery evidence;
- completed [results/observations.md](results/observations.md).

**Pass:** all four token shapes are validated from API usage; each case has three measured rows at fixed concurrency; actual output counts are distinguished from ceilings; failures/OOMs remain recorded; telemetry blanks are explained; each bottleneck hypothesis links to evidence; one selected shape's knee/capacity boundary is identified or bounded.

**Revise:** approximate words are claimed as tokenizer counts; max-token ceilings are reported as actual outputs; successful missing usage is treated as zero tokens; blank GPU samples are treated as 0%; case prompts/server settings drift within a comparison; or fixed concurrency alone is claimed to prove saturation.

**Human review:** Defend which observations support prefill-heavy, decode-heavy, mixed, KV-cache, compute, and memory-bandwidth hypotheses; identify what cannot be concluded without TTFT/TPOT and runtime queue/KV-cache metrics.
