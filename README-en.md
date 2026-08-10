# Kubernetes-Native LLM Inference Platform

Language: [中文](README.md) | English

> An experimental Kubernetes-native LLM inference platform built on two DGX Spark nodes, developing reproducible and explainable engineering practices around inference serving, GPUs / unified memory, Kubernetes, observability, scheduling, autoscaling, failure handling, and distributed extensions.

Current status: **M0 Platform Qualification is complete; M1 Single-Node vLLM Baseline is in progress.**

## Project Goal

Learn and implement a reasonably complete AI infrastructure engineering chain:

```text
Runtime
  → Resource
  → Scheduling
  → Observability
  → Control Loop
  → Reliability
```

The project uses controlled workloads and failure scenarios to study how runtimes, GPUs and memory, Kubernetes control mechanisms, and service quality interact. Findings are captured in code, raw results, design documents, and explicit operating boundaries.

## Target Architecture

The diagram below is the target structure delivered milestone by milestone. It does not imply that every component has already been implemented:

```text
Client / Load Generator
        |
        v
Gateway / API
        |
        v
Serving Data Plane
        |
   +----+----+
   |         |
   v         v
Observability   Control Plane
        \       /
         \     /
      Workload / Experiment
```

- **Serving Data Plane**: start with vLLM, then compare inference runtimes progressively.
- **Observability**: correlate Kubernetes, GPU and memory, runtime, TTFT/TPOT/E2E, goodput, and SLOs.
- **Control Plane**: investigate memory protection, locality-aware scheduling, and LLM-aware autoscaling.
- **Workload / Experiment**: generate concurrency, long-context, burst, contention, and failure scenarios to validate the other planes.

## Testbed

| Item | Current environment |
|---|---|
| Nodes | 2 × DGX Spark |
| Compute | NVIDIA GB10 Grace Blackwell |
| Architecture | ARM64 / AArch64 |
| Memory model | Unified Memory shared by CPU and GPU; results are not interpreted as discrete-GPU VRAM behavior |
| Network | ConnectX-7; the high-speed data link recorded during M0 negotiated at 200 Gb/s |
| Primary use | Single-node serving baselines, two replicas, resource governance, and optional distributed experiments |

> This is a two-node experimental environment. It is not equivalent to a production DGX/H100/H200/B200 cluster, and its results should not be extrapolated directly to large data-center GPU clusters.

M0 NCCL qualification validated only the collective and network baseline. Cross-node model parallelism has not been validated.

## Current Progress

| Milestone | Status | Current scope |
|---|---|---|
| M0 — Platform Qualification | ✅ Complete | Both nodes completed host CUDA, GPU container, TCP/NCCL, and compatibility-boundary validation within the M0 smoke scope |
| M1 — Single-Node vLLM Baseline | 🚧 In Progress | Lab and tooling scaffolding exist; the formal benchmark baseline and capacity findings are not complete |
| M2 — Kubernetes GPU Deployment | Planned | GPU workers, RuntimeClass / Device Plugin, and a vLLM workload |
| M3 — Observability & SLO | Planned / Design available | An initial SLO draft exists; metrics, dashboards, and alerts remain to be implemented |
| M4 — Two-Replica Serving | Planned | Routing, failover, and rolling updates |
| M5–M7 — Control Plane | Planned | Memory Supervisor, Scheduler Plugin, and LLM Autoscaler |
| M8 — Multi-Runtime Benchmark | Planned | Runtime comparison under a common workload |
| M9 — Production Simulation | Planned | Cross-plane failure, recovery, and capacity evaluation |
| M10 — Distributed Extensions | Optional | NCCL, Tensor Parallel, and cross-node failure boundaries |

See the [Roadmap](docs/Roadmap.md) for each milestone's scope and exit criteria.

## M0 Highlights

- Both nodes passed host CUDA smoke tests, digest-pinned PyTorch GPU-container smoke tests, and four-layer bootstrap replay.
- A digest-pinned vLLM runtime image loaded the model and returned HTTP 200 on both nodes; the outer wrapper's exit `141` is retained as a lifecycle-harness limitation.
- The initial TCP baseline recorded 96.7404 Gbit/s receiver throughput with 4 streams over 30 seconds. It also retained 43,506 retransmissions, so this result is not presented as a tuning limit.
- NCCL `all_reduce` and `all_gather` both exited `0`, with zero correctness and out-of-bounds errors.
- NCCL channel logs and changes between raw RDMA counter snapshots captured before and after the tests at both endpoints jointly support that built-in `NET/IB` over mlx5 RoCE carried collective traffic. `GDR 0` means GPUDirect RDMA was not enabled.
- The official ARM64 image smoke test passed; Unified Memory telemetry, self-built multi-arch images, and Kubernetes GPU integration remain explicitly documented compatibility boundaries.

For deeper evidence and limitations, see the [M0 Final Review](docs/reviews/m0-review.md).

## M1 Current Focus

[vLLM Basics](labs/vllm-basics/README.md) Labs 0–4 already provide instructional scripts and documentation, but formal experiment data has not yet been produced. This README does not claim TTFT, TPOT, throughput, or capacity benchmark results.

Current work focuses on:

- Offline inference and OpenAI-compatible online serving;
- Prefill, Decode, KV Cache, PagedAttention, and Continuous Batching;
- Request-level TTFT, TPOT, E2E, token throughput, and success/failure;
- A `1 / 2 / 4 / 8 / 16` concurrency sweep that advances toward saturation only as evidence supports it;
- Short/long input-output workload shapes;
- Performance knees and capacity boundaries under Grace Blackwell Unified Memory.

The streaming client measures the first generated content. HTTP chunk intervals are not described as token-level ITL until that mapping is validated.

## Experiment Method

Starting with M1, the project follows the [Lightweight Experiment Repository Convention](docs/experiments/README.md):

- Fix the runtime, model/revision, configuration, and workload;
- Change one important variable at a time;
- Separate warm-up from measured runs;
- Preserve raw results and regenerate derived summaries;
- Do not delete timeouts, OOMs, non-zero exits, or other failures;
- Separate Observed Facts, Interpretations, and Hypotheses.

Private runs use `artifacts/private/<milestone>/<run-id>/`. Only representative results that have been manually reviewed and sanitized are copied to `benchmarks/raw-results/<experiment-family>/<run-id>/`.

## Repository Navigation

| Path | Purpose | Current state |
|---|---|---|
| [`labs/`](labs/) | Learning and mechanism experiments | vLLM Basics Labs 0–4 and kind basics exist |
| `serving/` | Reusable inference-runtime launch and configuration | Planned for M1 |
| `control-plane/` | Controllers, scheduler, and autoscaler | Planned for M5–M7 |
| `observability/` | Metrics, dashboards, recording rules, and alerts | Planned for M3 |
| `workloads/` | Workload contracts and load generation | Planned for M1/M3 |
| [`benchmarks/`](benchmarks/) | Configuration, public raw results, analysis, and reports | Contains M0 public raw results; M1 reports are planned |
| [`deployments/`](deployments/) | Host bootstrap and later Kubernetes deployments | M0 bootstrap exists; M2 is planned |
| [`distributed/`](distributed/) | NCCL baseline and distributed-inference extensions | M0 NCCL tests exist; M10 model parallelism is optional |
| [`docs/`](docs/) | Roadmap, ADRs, environment, SLO, reviews, and later architecture/runbooks | Maintained continuously |

Planned paths will be created in their corresponding milestones. This README does not present target directories as existing implementations.

## Roadmap / Showcase Navigation

| Reviewer focus | Primary entry point |
|---|---|
| Project roadmap and completion criteria | [`docs/Roadmap.md`](docs/Roadmap.md) |
| Current runtime learning and M1 starting point | [`labs/vllm-basics/`](labs/vllm-basics/README.md) |
| Experiment convention | [`docs/experiments/`](docs/experiments/README.md) |
| Benchmark findings | `benchmarks/reports/` — introduced progressively from M1 |
| Architecture | `docs/architecture/` — planned; see [ADR-0001](docs/adr/ADR-0001-dgx-spark-primary-testbed.md) for the current decision |
| Control Plane implementation | `control-plane/` — planned for M5–M7 |
| Observability implementation | `observability/` — planned for M3; see the current [SLO draft](docs/SLO/inference-service-slo.md) |

M0 closeout documents are retained as historical and deep-review material, but they are not the default template for later milestones or the first reading path for a general reviewer.
