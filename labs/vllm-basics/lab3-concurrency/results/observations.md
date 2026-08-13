# Lab 3 Observations

## Fixed conditions

| Setting | Value |
|---|---|
| Environment evidence | `{benchmark}/m1/20260810-lab3/image.txt` |
| Runtime/container and vLLM/PyTorch versions | vLLM `0.24.0+092c4842.dev`, PyTorch `2.13.0a0+9186a08b2c.nv26.07` |
| Model/revision | Qwen2.5-0.5B-Instruct `7ae557604adf67be50417f59c2c2f167def9a775` |
| Exact server command/log | `{benchmark}/m1/20260810-lab3/server.log` |
| Served API model name | `qwen2.5-0.5B-Instruct` |
| Prompt | `Explain continuous batching in two sentences.` |
| Prompt tokens from API usage | 37 |
| Max output tokens/request | 64 |
| Temperature / seed | 0 / 42 |
| Requests per measured run | 32 |
| Warm-up procedure | 2 unmeasured requests before each row |
| Timeout | 120 seconds/request |
| Concurrency levels | 1, 2, 4, 8, 16 |
| Repetitions | 3/level |
| Aggregate CSV | `{benchmark}/m1/20260810-lab3/baseline.csv` |
| Per-run logs/exit codes | `{benchmark}/m1/20260810-lab3/logs/` |

## Evidence completeness

| Concurrency | Measured rows | Successful/failed requests | Linked log/exit codes | Server/GPU evidence |
|---:|---:|---|---|---|
| 1 | 3 | 32 / 0 | `{benchmark}/m1/20260810-lab3/logs/rep-*-c-1.log` / 0 | `{benchmark}/m1/20260810-lab3/server.log` |
| 2 | 3 | 32 / 0 | `{benchmark}/m1/20260810-lab3/logs/rep-*-c-2.log` / 0 | `{benchmark}/m1/20260810-lab3/server.log` |
| 4 | 3 | 32 / 0 | `{benchmark}/m1/20260810-lab3/logs/rep-*-c-4.log` / 0 | `{benchmark}/m1/20260810-lab3/server.log` |
| 8 | 3 | 32 / 0 | `{benchmark}/m1/20260810-lab3/logs/rep-*-c-8.log` / 0 | `{benchmark}/m1/20260810-lab3/server.log` |
| 16 | 3 | 32 / 0 | `{benchmark}/m1/20260810-lab3/logs/rep-*-c-16.log` / 0 | `{benchmark}/m1/20260810-lab3/server.log` |

## Findings

- Throughput range/central value by concurrency: 
  - 1: 2.71 - 2.73 req/s
  - 2: 5.95 - 6.00 req/s
  - 4: 11.73 - 11.90 req/s
  - 8: 22.68 - 22.80 req/s
  - 16: 40.78 - 59.71 req/s
- Latency p50/p95 trend by concurrency: Not significant in this lab
- Concurrency with best stable request throughput: C16, at the current lab's scope
- First candidate performance knee and decision rule: Candidate knee was not reached at this lab' range.
- Tail-latency behavior and 32-sample limitation: 32 requests per measured run is too small to characterize tail latency. The p95 and p99 values are not statistically significant, so this lab is just a proof of concept for later implementation.
- Failures, timeouts, restarts, and server evidence: No failures, timeouts, or restarts were observed. Server evidence see above.
- Why requests/second is incomplete: RPS is only meaningful when the input prompt and output token counts are fixed. I/O token counts can be variable in real workloads, so RPS is not a complete performance metric. Also other metrics like TTFT and TPOT are important to e2e experience.
- Client-side E2E versus TTFT/TPOT limitation: This lab's scope only measures client-side e2e latency and throughput and does not measure TTFT or TPOT. 
- Unified-memory/GPU telemetry limitation: Current lab does not reach the memory limit and the scope is too trivial to measure GPU telemetry. 
- Observed facts: All tested concurrency levels C=1/2/4/8/16 completed without measured request failures. RPS significantly increased with concurrency, but the p50/p95 latency trend was not significant. The candidate performance knee was not reached at this lab's range. 
- Interpretation: C=16 remained within the observed successful operating range. Neither a performance knee nor a capacity boundary was demonstrated.
- Unresolved hypotheses and next controlled experiment: Need more intensive testing to pressure test the server and GPU to reach a performance knee or capacity boundary. Next experiment should include more requests per measured run, higher concurrency levels, and possibly larger prompt/output sizes
