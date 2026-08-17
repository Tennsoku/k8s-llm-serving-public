# Lab 4 Close Observations

Do not fill TODO fields from expectation. Preserve failed rows.

## Fixed conditions

| Setting | Value |
|---|---|
| Scope | Four workload shapes at C8; no knee/capacity search |
| Environment/runtime/container evidence | `${benchmarks}/raw-results/20260812-lab4/image.txt` |
| Model/revision and served API name | Qwen2.5-0.5B-Instruct `7ae557604adf67be50417f59c2c2f167def9a775` |
| Exact server command/log | `${benchmarks}/raw-results/20260812-lab4/server*` |
| Workload source commit | _private commit_ |
| Prefix-caching state | `cache_salt` per request |
| Cache isolation / API compatibility | Request-unique `cache_salt`; namespace `20260812-lab4-c8` /evidence `workload-results.csv` |
| Concurrency / requests for shape comparison | 8 / 16 |
| Warm-up / timeout | 1 request/case / 600 seconds |
| Repetitions | 1 exploratory run |
| Optional supporting telemetry | `${benchmarks}/raw-results/20260812-lab4/system-samples.jsonl` |
| Shape-check CSV/log | `${benchmarks}/raw-results/20260812-lab4/shape-check.csv`  |
| Measured CSV and per-run logs | `${benchmarks}/raw-results/20260812-lab4/` |

## Shape validation

| Case | Actual input tokens/request | Actual output tokens/request | Intended shape valid? | Evidence/notes |
|---|---:|---:|---|---|
| short-short | 55 / 1 | 32 / 1 | yes | `shape-check.csv` |
| short-long | 60 / 1 | 512 / 1 | yes | `shape-check.csv` |
| long-short | 5890 / 1 | 32 / 1 | yes | `shape-check.csv` |
| long-long | 5888 / 1 | 263 / 1 | yes | `shape-check.csv` |

## Fixed-C8 comparison

| Case | E2E/throughput facts | Interpretation | Unresolved hypothesis and M1.4 signal |
|---|---|---|---|
| short-short | Fastest E2E, High RPS | Input/Output token usage low, lowest cost among all shapes | 最低 E2E+最高 RPS, overhead-sensitive candidate. M1.4 - throughput marginal, TTFT/E2E, waiting requests |
| short-long | High E2E, Low RPS | Output token usage high, need more decoding time and resources | decode-heavy candidate. M1.4 - output TPS knee and TPOT/E2E/queue |
| long-short | Low E2E, Medium RPS | Input token usage high, prefill dominates, better performance under UMA | prefill-load candidate. M1.4 - TTFT/input TPS/waiting |
| long-long | Highest E2E, Lowest RPS | Input and output token usage high, combined prefill and decode pressure | 最高 E2E+最低 RPS，mixed/KV-footprint candidate. M1.4 - TTFT/TPOT/waiting/KV usage/preemption |

## Scope boundary and M1.4 handoff

| Field | Disposition |
|---|---|
| Saturation / latency-queue knee | Not tested |
| Hard capacity boundary | Not tested / Unknown |
| Per-workload C_eff / C_pressure | Pending M1.4 |

M1.3 concurrency labels are workload-scoped and are not inherited here.

## Interpretation

- Highest E2E latency, with evidence: long-long, total-sequence-footprint candidate.
- Prefill-heavy candidate and evidence: long-* shapes, input token way higher
- Decode-heavy candidate and evidence: *-long shapes, output token way higher
- Greatest KV-cache-pressure candidate and evidence: Not collected.
- TTFT claim status (must remain a hypothesis without streaming/server metric): Long input should result in longer TTFT.
- OOM, timeout, failure, and recovery behavior: none observed, all four shapes completed successfully.
- Blank/unsupported GB10 telemetry interpretation: not supported, bypass
- GPU utilization status: system telemetry shows GPU utilization is not a reliable indicator of saturation or capacity for this workload.
- TTFT/ITL/TPOT status: not measured by this non-streaming runner
- Observed facts: The cost shape matrix matches expectation. 
  When prefilling/decoding pressure is high, the counterpart resource 
  will also be taken and overall performance will be lower. The short-short shape is least E2E and RPS,
  while the long-long shape is the highest E2E and lowest RPS. However this does not mean the tps and overall performance.
- Interpretation: Prefilling is compute intensive, decoding is memory intensive and takes more resources, comparing to prefilling. 
- Unresolved hypotheses and next one-variable experiment:   
  In M1.4, vary concurrency independently for each frozen workload and
  collect repeated streaming TTFT/E2E/token throughput plus waiting,
  KV usage, or preemption.

## Close decision

- [X] All four token shapes are valid.
- [X] All four C8 rows and failures are retained.
- [X] Every invocation used a distinct request namespace.
- [X] Facts, interpretations, hypotheses, and unknowns remain distinct.
- [X] C8 or GPU utilization was not used to claim saturation/capacity.
- [X] Each workload has a concise M1.4 investigation signal.

**Disposition:** Close

**Reason:** The retained evidence satisfies Lab 4’s exploratory collection scope; stable phase, pressure, and operating-point conclusions remain deferred to M1.4.
