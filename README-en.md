# LLM Inference Platform on DGX Spark

Language: [中文](README.md) | English

LLM inference platform engineering on two DGX Spark nodes (GB10 Grace Blackwell / ARM64 / unified memory). Starting from a single-node runtime baseline, then layering on Kubernetes, observability, and control loops.
This is a personal research testbed for platform-layer LLM workload behavior and engineering boundaries, not a general-purpose, multi-tenant, or product platform.

**Every conclusion is backed by request-level raw data. Failures are preserved, never filtered.**

- Interactive results → [M1 Showcase](https://tennsoku.github.io/k8s-llm-serving-public/showcase/m1/)
- Plan → [Roadmap](docs/Roadmap.md) · Current state → [Status](docs/context/current-status.md)

---

## Results at a glance

Qwen2.5-0.5B-Instruct · BF16 · TP=1 · vLLM (digest-pinned NGC ARM64 image) · single node
Four workload shapes, 3 repetitions per point, **10,368 requests with 0 failures and 0 timeouts**.

| Scenario | in → out tokens | C1 TTFT p95 | C_eff | C_eff TTFT p95 | C_eff output tok/s |
|---|---|---:|---:|---:|---:|
| short-short (e.g. NPC dialogue) | 55 → 32 | **12.8 ms** | 8 | 27.4 ms | 1,364 |
| short-long (e.g. narrative generation) | 60 → 512 | **13.3 ms** | 8 | 29.3 ms | 1,482 |
| long-short (e.g. world-state Q&A) | 5,890 → 32 | **133 ms** | 4 | 307 ms | 205 |
| long-long (e.g. long session) | 5,888 → 512 | **135 ms** | 8 | 274 ms | 749 |

`C_eff` = the concurrency reference where marginal throughput gain is still meaningful and service latency is still controlled. Determined independently per workload.

**Medium-model comparison** — Qwen2.5-7B-Instruct, same workload (60 → 512):

| Model | C1 output tok/s | C1 TTFT p95 | C8 output tok/s |
|---|---:|---:|---:|
| 0.5B | 148.2 | 14.3 ms | 1,493 |
| 7B | 12.7 | 80.1 ms | 126.1 |

The 7B result reaches **65% of the estimated unified-memory bandwidth roofline** (273 GB/s ÷ 14 GB BF16 weights ≈ 19.5 tok/s). This is consistent with a memory-bandwidth constraint on decode, but does not by itself rule out scheduling or kernel effects.

---

## Three findings worth reading

### 1. Prefill and decode have entirely different cost structures

Growing input from 55 to 5,890 tokens raises C1 TTFT from 12.8 ms to 133 ms (**10.4×**) — the one-time prefill cost.

But the **scaling behavior** is the real distinction:

| | C1 → C_eff output throughput | Factor |
|---|---|---:|
| Decode-heavy (60 → 512) | 150.8 → 1,482 tok/s | **9.8×** |
| Prefill-heavy (5,890 → 32) | 92.4 → 205 tok/s | **2.2×** |

Decode-heavy work amortizes per-request overhead through continuous batching and scales near-linearly. Prefill-heavy compute grows linearly with concurrency and cannot be amortized — a waiting queue already appears at C4 (peak 2) and reaches 13 at C16.

**Implication**: capacity planning must be done per workload shape. A single concurrency setting across all scenarios either wastes decode throughput or destroys prefill latency.

### 2. The throughput saturation point is not the latency collapse point

Bounded boundary test on the long-long workload (C16 → C64):

| Concurrency | Output tok/s | TTFT p95 | Peak waiting queue | Peak KV cache |
|---:|---:|---:|---:|---:|
| 16 | 920 | 1.56 s | 13 | 7.3% |
| 32 | 900 | 4.73 s | 27 | 14.6% |
| 48 | 916 | 9.88 s | 43 | 22.1% |
| 64 | 1,005 | **16.78 s** | 56 | 28.9% |

Quadrupling concurrency yields 9% more throughput while TTFT grows **10.7×** and the waiting queue grows linearly — a textbook queueing saturation signature.

Note that **peak KV cache usage is only 28.9%**: queueing and TTFT pressure appeared before high KV-cache usage in this test. That does not rule out other runtime bottlenecks, but it does show why memory headroom alone is not a capacity criterion.

Likewise, GPU utilization held steady at 96% across C64/C96/C128 in the M1.3 measurements — **it does not track service state**. This project therefore explicitly rejects GPU utilization as a saturation or capacity criterion.

### 3. A measurement error found by self-review

The first M1.3 concurrency sweep produced 6,038 output tok/s at C64. A good-looking number.

Cross-checking runtime counters revealed the workload used a fixed prompt with a **99.31% prefix-cache token hit ratio**. Most prefill work was being skipped by the cache — the number was not measuring serving capability.

Handling:

1. The M1.3 conclusion was **kept**, but scoped to "this fixed workload only", with the hit ratio and its impact documented in the review;
2. M1.4 introduced per-request `cache_salt`, giving every request a unique cache identity;
3. After re-measurement, published summaries report `prefix_cache_token_hit_ratio = 0.0` — the tables above are the cache-isolated values.

`cache_salt` is used strictly as a workload control: it isolates cache identity and carries no evidence-authenticity role.

---

## Measurement method

The engineering constraints behind the results above:

| Aspect | Approach |
|---|---|
| **Timing** | Durations use a monotonic clock; wall-clock only for cross-log correlation |
| **Streaming semantics** | An HTTP chunk is not a model token. TTFT is taken at first generated content; TPOT is derived from decode duration ÷ actual output tokens — chunk intervals are never passed off as ITL |
| **Token counts** | Actual API-reported usage, never target values |
| **Cache control** | Unique `cache_salt` per request; hit ratios claimed only with runtime-counter evidence |
| **Repetition** | Canonical runs use 3 repetitions per point; medians reported with min/max retained |
| **Failures** | Timeouts, OOM, non-zero exits and restarts stay in `raw/` and are never filtered from summaries |
| **Recomputability** | `derived/` must regenerate from `raw/`; flawed analysis is fixed and recomputed — `raw/` is never edited |
| **Fixed configuration** | Node, image digest, model revision, server arguments and workload all recorded and fingerprinted |

Single-entry replay: `serving/vllm/run-benchmark.sh --config <workload.yaml> --node-label <label>`

---

## Testbed

| | |
|---|---|
| Nodes | 2 × DGX Spark |
| Compute | NVIDIA GB10 Grace Blackwell · ARM64 |
| Memory | CPU/GPU shared unified memory — not interpreted as discrete VRAM |
| Network | ConnectX-7, measured 96.74 Gbit/s (4 streams / 30 s), RoCE carrying NCCL collectives |

M0 qualified host CUDA, GPU containers, TCP/NCCL baselines, NIC counters and the RoCE data path, plus four-layer bootstrap replay.

**Known boundaries**: GPUDirect RDMA is not active (`GDR 0`); cross-node model parallelism is unverified; Kubernetes GPU integration is measured starting in M3. Two-node results are not extrapolated to production DGX clusters.

---

Current milestone state has a single owner: [Status](docs/context/current-status.md). Scope and exit criteria are in the [Roadmap](docs/Roadmap.md).

---

## Repository map

| Path | Contents |
|---|---|
| [`serving/vllm/`](serving/vllm/) | Server lifecycle scripts + benchmark pipeline (streaming client, runtime/system collectors, summary generation) |
| [`benchmarks/`](benchmarks/) | Workload configs, public raw results, recomputable summaries |
| [`showcase/m1/`](showcase/m1/) | M1 interactive report |
| [`labs/vllm-basics/`](labs/vllm-basics/README.md) | Runtime mechanism labs (Labs 0–4) |
| [`docs/reviews/`](docs/reviews/) | Per-milestone conclusions, limitations and unknowns |
| [`docs/experiments/`](docs/experiments/README.md) | Experiment directory convention and sanitization workflow |
| [`docs/environment/`](docs/environment/) | Hardware, network, NCCL and compatibility baselines |
| [`deployments/bootstrap/`](deployments/bootstrap/) | Host and GPU-container qualification scripts |
| [`AGENTS.md`](AGENTS.md) | Behavioral contract for AI collaboration |

---

## How AI was used

This project uses AI assistance throughout, with an explicit division of labor:

| | AI | Human |
|---|---|---|
| Design | Drafting, structural proposals | Trade-off decisions, scope rulings |
| Code | Tooling implementation | Review and acceptance |
| Audit | Continuous audit (consistency, evidence gaps, overreaching claims) | — |
| Experiments | — | **All execution** |
| Records | — | **All result recording and conclusion writing** |
| Docs | Drafts | **Document control and single-source maintenance** |
| Boundaries | — | **Capability limits and non-extrapolation rulings** |

All experiments were run and verified on real hardware by the author. AI produced no benchmark data.

[`AGENTS.md`](AGENTS.md) is the behavioral contract for this collaboration, defining budget constraints, a single-source-of-truth map, standing non-goals and stop conditions. It is itself a project artifact — M0 produced a 1,137-line evidence tool and a specification for an unbuilt component, and the contract is the structural response to those specific incidents.

## License

Except where otherwise noted, original content in this repository is licensed under Apache-2.0; third-party components retain their own licenses. Model weights, container images and other external assets are not covered by this repository license.
