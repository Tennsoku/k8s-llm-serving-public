# Lab 4: Fixed-C8 Workload Shape Analysis

## Outcome

Compare four short/long input-output shapes at fixed C8 under one online-server configuration. This lab compares workload shape and does not search for saturation, a performance knee, or a capacity boundary.

Run every command below from `labs/vllm-basics/`. This runner is non-streaming: it does not measure TTFT, ITL, or TPOT.

## 1. Freeze the environment and understand the cases

Keep the node, runtime image, model/revision, served name, vLLM arguments, prefix-caching state, prompt source, request count, C8, and background load fixed. If any setting changes, start a new comparison group.

Read [workload_cases.md](workload_cases.md). The exact prompt strings and output ceilings are source-controlled in `run_workloads.py:CASES`:

| Case | Intended shape | Output ceiling/request | Primary pressure |
|---|---|---:|---|
| `short-short` | 32–64 input tokens | 32 | request/runtime overhead |
| `short-long` | 32–64 input tokens | 512 | sustained decode |
| `long-short` | more than 2,000 input tokens | 32 | prefill |
| `long-long` | more than 2,000 input tokens | 512 | prefill, decode, KV-cache pressure hypothesis |

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

## 2. Isolate cache reuse and validate token shapes

Keep prefix caching enabled. The runner uses a deterministic request-unique vLLM cache_salt while keeping each case prompt unchanged. cache_salt is version-sensitive, so the shape check must confirm that the pinned API accepts it. Use a new request namespace for every invocation; per-row counter gates and cache-reset orchestration are outside this lab.

Run one request per case into a separate shape-check CSV:

```bash
set -o pipefail
python3 lab4-workload-analysis/run_workloads.py \
  --base-url "${BASE_URL}" \
  --model "${SERVED_MODEL_NAME}" \
  --case all \
  --concurrency 1 \
  --requests 1 \
  --warmup 0 \
  --request-namespace "${LAB4_RUN_ID}-shape" \
  --timeout 600 \
  --output "${LAB4_RUN_DIR}/shape-check.csv" \
  2>&1 | tee "${LAB4_RUN_DIR}/logs/shape-check.log"
rc=${PIPESTATUS[0]}
printf 'exit_code=%d\n' "${rc}" | \
  tee -a "${LAB4_RUN_DIR}/logs/shape-check.log"
test "${rc}" -eq 0
```

Inspect `input_tokens_per_request`:

- both short cases should fall in the documented short range;
- both long cases should exceed 2,000 tokens;
- successful responses must contain nonzero API usage counts;
- actual output tokens may be below the ceiling because of EOS.

If a shape misses its range, adjust only that source prompt, commit/record the change, rerun the shape check and measured comparison in a new run group. Do not edit a prompt after measured rows already exist in the same comparison group.

A successful response with zero token usage means the required metric was unavailable or not parsed; it does not prove a zero-token request. Mark the shape run invalid until the API/runner supplies usage.

## 3. Run the fixed-C8 shape comparison

The primary comparison holds concurrency at 8 and runs each case sequentially. Requests inside a case are concurrent; the four cases are not concurrent with one another.

```bash
set -o pipefail
python3 lab4-workload-analysis/run_workloads.py \
  --base-url "${BASE_URL}" \
  --model "${SERVED_MODEL_NAME}" \
  --case all \
  --concurrency 8 \
  --requests 16 \
  --warmup 1 \
  --request-namespace "${LAB4_RUN_ID}-c8" \
  --timeout 600 \
  --sample-interval 0.5 \
  --output "${LAB4_RUN_DIR}/workload-results.csv" \
  2>&1 | tee "${LAB4_RUN_DIR}/logs/shape-comparison-c8.log"
rc=${PIPESTATUS[0]}
printf 'exit_code=%d\n' "${rc}" | \
  tee -a "${LAB4_RUN_DIR}/logs/shape-comparison-c8.log"
test "${rc}" -eq 0
```

Keep the case order fixed and note that later cases may benefit from already compiled kernels/caches. The per-case warm-up reduces but does not eliminate order and thermal effects. This exploratory run produces one measured row per case.

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

## 5. Keep telemetry proportional to the lab

The runner samples GPU utilization and memory when `nvidia-smi` exposes them. On GB10 unified memory, fields may be unsupported; preserve blanks rather than turning them into zero. GPU utilization is supporting telemetry only and must not define saturation, pressure, or capacity.

The existing `system_metrics.py` sampler may be run in a second shell around the complete matrix when system/cgroup context is useful. This preserves the sampler intent without making it a Lab 4 pass condition.

Optional sampler command (second shell; stop with Ctrl-C after the matrix):

```bash
python3 "${VLLM_LABS_REPO_ROOT}/serving/vllm/benchmark/system_metrics.py" \
  --run-id "${LAB4_RUN_ID}" \
  --container vllm-m1 \
  --interval 1 \
  --output "${LAB4_RUN_DIR}/system-samples.jsonl"
```

Lab 4 ends after the fixed-C8 comparison. M1.4 selects `C1 / C_eff / C_pressure` independently for each workload. Do not inherit M1.3 C64/C96 references or use C128 as a default point.

## Submission and review criteria

Submit:

- fixed server/model/runtime configuration and source commit;
- shape-check CSV/log;
- four fixed-C8 rows with one retained log/exit code;
- optional telemetry or an explicit unsupported/not-collected statement;
- retained failure evidence;
- completed [results/observations.md](results/observations.md).

**Pass:** all four token shapes are validated from API usage; each case has one measured C8 row; request cache identities are isolated; failures and unsupported telemetry remain visible; and each workload has a concise M1.4 hypothesis.

**Revise:** cache salts are reused; token ceilings are reported as actual outputs; unsupported telemetry is treated as zero; prompts/server settings drift; or C8/GPU utilization is used to claim saturation or capacity.

**Human review:** Defend the prefill/decode hypotheses and identify what cannot be concluded from a non-streaming, fixed-C8 experiment.
