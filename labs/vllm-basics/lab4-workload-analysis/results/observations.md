# Lab 4 Observations

## Fixed conditions

| Setting | Value |
|---|---|
| Environment/runtime/container evidence | TODO |
| Model/revision and served API name | TODO |
| Exact server command/log | TODO |
| Workload source commit | TODO |
| Concurrency / requests for shape comparison | 8 / 16 |
| Warm-up / timeout | 1 request/case / 600 seconds |
| Repetitions | 3 |
| GPU sample command/interval | TODO |
| System/cgroup memory scope/interval | TODO |
| Shape-check CSV/log | TODO |
| Measured CSV and per-run logs | TODO |

## Shape validation

| Case | Actual input tokens/request | Actual output tokens/request | Intended shape valid? | Evidence/notes |
|---|---:|---:|---|---|
| short-short | TODO | TODO | TODO | TODO |
| short-long | TODO | TODO | TODO | TODO |
| long-short | TODO | TODO | TODO | TODO |
| long-long | TODO | TODO | TODO | TODO |

## Fixed-concurrency comparison

| Case | E2E/throughput observations across repetitions | GPU/system-memory evidence | Bottleneck hypothesis and support |
|---|---|---|---|
| short-short | TODO | TODO | TODO |
| short-long | TODO | TODO | TODO |
| long-short | TODO | TODO | TODO |
| long-long | TODO | TODO | TODO |

## Selected-case knee/capacity bound

| Field | Value |
|---|---|
| Selected case and evidence-based reason | TODO |
| Concurrency levels/repetitions | TODO |
| First material throughput/latency knee | TODO/not reached |
| First timeout/OOM/instability boundary | TODO/not reached |
| Failed-boundary raw evidence and recovery | TODO |
| Scope: shapes to which this conclusion applies | TODO |

## Interpretation

- Highest E2E latency, with evidence: TODO
- Prefill-heavy candidate and evidence: TODO
- Decode-heavy candidate and evidence: TODO
- Greatest KV-cache-pressure candidate and evidence: TODO
- TTFT claim status (must remain a hypothesis without streaming/server metric): TODO
- OOM, timeout, failure, and recovery behavior: TODO
- Blank/unsupported GB10 telemetry interpretation: TODO
- Limits of client-side E2E and sampled GPU metrics: TODO
- Observed facts: TODO
- Interpretation: TODO
- Unresolved hypotheses and next one-variable experiment: TODO
