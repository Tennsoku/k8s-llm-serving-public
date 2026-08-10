# Lab 3 Observations

## Fixed conditions

| Setting | Value |
|---|---|
| Environment evidence | TODO |
| Runtime/container and vLLM/PyTorch versions | TODO |
| Model/revision | TODO |
| Exact server command/log | TODO |
| Served API model name | TODO |
| Prompt | `Explain continuous batching in two sentences.` |
| Prompt tokens from API usage | TODO |
| Max output tokens/request | 64 |
| Temperature / seed | 0 / 42 |
| Requests per measured run | 32 |
| Warm-up procedure | 2 unmeasured requests before each row |
| Timeout | 120 seconds/request |
| Concurrency levels | 1, 2, 4, 8, 16 |
| Repetitions | 3/level |
| Aggregate CSV | TODO |
| Per-run logs/exit codes | TODO |
| GPU/system/cgroup sampling method | TODO |

## Evidence completeness

| Concurrency | Measured rows | Successful/failed requests | Linked log/exit codes | Server/GPU evidence |
|---:|---:|---|---|---|
| 1 | TODO | TODO | TODO | TODO |
| 2 | TODO | TODO | TODO | TODO |
| 4 | TODO | TODO | TODO | TODO |
| 8 | TODO | TODO | TODO | TODO |
| 16 | TODO | TODO | TODO | TODO |

## Findings

- Throughput range/central value by concurrency: TODO
- Latency p50/p95 trend by concurrency: TODO
- Concurrency with best stable request throughput: TODO
- First candidate performance knee and decision rule: TODO
- Tail-latency behavior and 32-sample limitation: TODO
- Failures, timeouts, restarts, and server evidence: TODO
- Why requests/second is incomplete: TODO
- Client-side E2E versus TTFT/TPOT limitation: TODO
- Unified-memory/GPU telemetry limitation: TODO
- Observed facts: TODO
- Interpretation: TODO
- Unresolved hypotheses and next controlled experiment: TODO
