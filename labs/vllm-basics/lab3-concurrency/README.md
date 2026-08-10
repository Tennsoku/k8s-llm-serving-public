# Lab 3: Concurrent Request Baseline

## Outcome

Measure client-side end-to-end latency and successful-request throughput at controlled concurrency, while preserving aggregate CSV rows, per-run logs, exit codes, warm-up behavior, and every failure.

Run every command below from `labs/vllm-basics/`. This is an exploratory concurrency baseline, not yet a TTFT/TPOT or SLO benchmark.

## 1. Freeze the server and workload

Start the Lab 2 server once and keep it unchanged for the complete sweep. Record its expanded command and log in [results/observations.md](results/observations.md).

In the client shell:

```bash
export BASE_URL=http://127.0.0.1:8000
export SERVED_MODEL_NAME=qwen2.5-0.5b-instruct
export VLLM_LABS_REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB3_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-lab3"
export LAB3_RUN_DIR="${VLLM_LABS_REPO_ROOT}/artifacts/private/m1/${LAB3_RUN_ID}"
mkdir -p "${LAB3_RUN_DIR}/logs"
```

The required measured workload is:

| Setting | Fixed value |
|---|---|
| API | non-streaming `POST /v1/chat/completions` |
| Prompt | `Explain continuous batching in two sentences.` |
| Max output | 64 tokens/request |
| Temperature / seed | 0 / 42 |
| Timeout | 120 seconds/request |
| Requests | 32 per measured run |
| Warm-up | 2 requests before each measured run |
| Concurrency | 1, 2, 4, 8, 16 |
| Repetitions | 3 at each concurrency |

`concurrency` is the semaphore limit on simultaneous in-flight client requests. It is not a server batch-size setting and does not prove how many sequences execute together on the GPU.

Before the sweep, verify health and retain one exact response so the prompt token count and actual output behavior are known:

```bash
curl --fail-with-body --silent --show-error \
  -H 'Content-Type: application/json' \
  --data "{\"model\":\"${SERVED_MODEL_NAME}\",\"messages\":[{\"role\":\"user\",\"content\":\"Explain continuous batching in two sentences.\"}],\"temperature\":0,\"seed\":42,\"max_tokens\":64}" \
  "${BASE_URL}/v1/chat/completions" | \
  tee "${LAB3_RUN_DIR}/fixed-workload-response.json"
```

Use the response's `usage.prompt_tokens` in the fixed-conditions table. Lab 3's aggregate CSV intentionally does not contain token counters.

## 2. Smoke test

Write smoke output to a separate file so it is not confused with the measured sweep:

```bash
set -o pipefail
python lab3-concurrency/concurrent_client.py \
  --base-url "${BASE_URL}" \
  --model "${SERVED_MODEL_NAME}" \
  --concurrency 1 --requests 2 --warmup 1 --max-tokens 64 \
  --output "${LAB3_RUN_DIR}/smoke.csv" \
  2>&1 | tee "${LAB3_RUN_DIR}/logs/smoke.log"
printf 'exit_code=%d\n' "${PIPESTATUS[0]}" | \
  tee -a "${LAB3_RUN_DIR}/logs/smoke.log"
```

Do not continue if the health/model checks or warm-up fail. Diagnose the server/model name first and retain the failed smoke log.

## 3. Run the measured sweep

The loop below continues after a failed measured run so later evidence is not lost. Each repetition has its own stdout/stderr log; all aggregate rows append to one private CSV:

```bash
for repetition in 1 2 3; do
  for concurrency in 1 2 4 8 16; do
    log="${LAB3_RUN_DIR}/logs/rep-${repetition}-c-${concurrency}.log"

    set -o pipefail
    python lab3-concurrency/concurrent_client.py \
      --base-url "${BASE_URL}" \
      --model "${SERVED_MODEL_NAME}" \
      --concurrency "${concurrency}" \
      --requests 32 \
      --warmup 2 \
      --max-tokens 64 \
      --timeout 120 \
      --output "${LAB3_RUN_DIR}/baseline.csv" \
      2>&1 | tee "${log}"
    rc=${PIPESTATUS[0]}
    printf 'repetition=%d concurrency=%d exit_code=%d\n' \
      "${repetition}" "${concurrency}" "${rc}" | tee -a "${log}"
  done
done
```

Do not restart the server, edit the prompt, or change runtime arguments between concurrency levels. If external activity, thermal behavior, OOM, or a required restart occurs, timestamp it and start a new run group instead of silently continuing the same comparison.

The client issues two unmeasured warm-up requests for every invocation, then starts the measured wall timer. Warm-up requests do not enter the CSV. A warm-up failure produces a nonzero exit and no measured row; its log is still required evidence.

## 4. Validate the outputs

The CSV stores one aggregate row per measured invocation. It does not store individual request records. Verify that every concurrency has three rows:

```bash
awk -F, '
  NR > 1 { rows[$3]++ }
  END {
    for (i = 1; i <= 16; i *= 2) {
      printf "concurrency=%d rows=%d\n", i, rows[i] + 0
    }
  }
' "${LAB3_RUN_DIR}/baseline.csv"
```

Interpret each field according to the implementation:

- `wall_time_seconds`: time from scheduling the measured tasks until all measured tasks return.
- `throughput_rps`: successful measured requests divided by measured wall time.
- latency fields: client-side non-streaming E2E latency over successful measured requests only.
- `failed_requests`: HTTP error, timeout, connection error, or response-processing failure.
- p50/p95/p99: linear interpolation over successful requests.

With only 32 requests, especially at high concurrency, p95/p99 are exploratory estimates and should not be presented as stable SLO percentiles. A zero percentile when no request succeeds means “no successful latency samples,” not observed zero latency.

Correlate every row with:

- its uniquely named client log and exit code;
- the same-time server log;
- timestamped system/cgroup/GPU observations;
- any OOM, timeout, restart, JIT, preemption, or queueing message.

Preserve [results/baseline.csv](results/baseline.csv) as a header/example template. Use the private output path above for actual exploratory raw results unless deliberately preparing a reviewed representative result.

## 5. Compare repetitions and locate a candidate knee

For each concurrency, compare all three repetitions before drawing a conclusion. Report:

- median/range of request throughput across repetitions;
- p50 and p95 latency trend;
- failure and timeout counts;
- the first concurrency where throughput gains flatten while latency or failures rise materially;
- whether the candidate knee is observed, merely bounded above/below, or not reached by concurrency 16.

Request throughput alone is insufficient because requests may contain different token counts. This lab fixes one prompt/output ceiling to make RPS comparisons meaningful; Lab 4 adds actual input/output token throughput.

## Submission and review criteria

Submit:

- immutable model/revision and exact server command/log;
- fixed prompt and one retained response with usage;
- unedited private aggregate CSV;
- 15 uniquely named measured-run logs and exit codes;
- timestamped supporting memory/GPU evidence;
- completed [results/observations.md](results/observations.md).

**Pass:** levels 1/2/4/8/16 each have three measured rows; workload and server remain fixed; warm-ups are excluded; percentiles use successful measured requests; failures remain counted and linked to logs; reruns require no source edits; the candidate knee is stated with uncertainty.

**Revise:** request count is lower than concurrency without justification; repetitions overwrite one another; percentiles mix warm-up/failure data; no-success zeroes are treated as zero latency; failed rows/logs are deleted; or server/workload settings drift.

**Human review:** Explain why throughput and latency can rise together, what client concurrency represents, why 32-request tail percentiles are weak, and why RPS is not enough for LLM capacity planning.
