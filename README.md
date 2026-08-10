# Kubernetes-Native LLM Inference Platform

语言：中文 | [English](README-en.md)

> 基于两台 DGX Spark 的 Kubernetes-native LLM inference platform 实验项目，围绕 inference serving、GPU / unified memory、Kubernetes、observability、scheduling、autoscaling、failure handling 和 distributed extensions 建立可复现、可解释的工程实践。

当前状态：**M0 Platform Qualification 已完成；M1 Single-Node vLLM Baseline 进行中。**

## 项目目标

学习并落地一套较为完整的 AI Infra 工程链路：

```text
Runtime
  → Resource
  → Scheduling
  → Observability
  → Control Loop
  → Reliability
```

项目以受控 workload 和 failure scenario 为实验方法，观察 Runtime、GPU/内存、Kubernetes 控制机制与服务质量之间的关系，并把结论落到代码、原始结果、设计文档和运行边界中。

## 目标架构

下图是项目逐个 Milestone 实现的目标结构。当前不代表所有组件当前均已完成：

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

- **Serving Data Plane**：vLLM 起步，逐步比较不同 inference runtime。
- **Observability**：关联 Kubernetes、GPU/内存、Runtime、TTFT/TPOT/E2E、Goodput 与 SLO。
- **Control Plane**：研究 memory protection、locality-aware scheduling 和 LLM-aware autoscaling。
- **Workload / Experiment**：产生 concurrency、long-context、burst、contention 和 failure 场景，验证其他平面。

## Testbed

| 项目 | 当前实验环境 |
|---|---|
| 节点 | 2 × DGX Spark |
| Compute | NVIDIA GB10 Grace Blackwell |
| 架构 | ARM64 / AArch64 |
| 内存模型 | CPU 与 GPU 共享的 Unified Memory；不按离散 GPU VRAM 解释 |
| 网络 | ConnectX-7；M0 记录的高速数据链路协商速率为 200 Gb/s |
| 主要用途 | 单节点 serving baseline、双副本、资源治理与可选 distributed experiments |

> 双节点实验环境，不等价于生产 DGX/H100/H200/B200 集群。

M0 的 NCCL qualification 只验证 collective 与网络基线。跨节点模型并行尚未验证。

## Current Progress

| Milestone | 状态 | 当前口径 |
|---|---|---|
| M0 — Platform Qualification | ✅ Complete | 两节点在 M0 smoke scope 内完成 host CUDA、GPU container、TCP/NCCL 与兼容性边界验证 |
| M1 — Single-Node vLLM Baseline | 🚧 In Progress | Lab进度过半；正式 benchmark baseline 与容量结论尚未完成 |
| M2 — Kubernetes GPU Deployment | Planned | GPU worker、RuntimeClass / Device Plugin 与 vLLM workload |
| M3 — Observability & SLO | Planned / Design available | 已有初始 SLO draft；metrics、dashboard 和 alert 尚待实现 |
| M4 — Two-Replica Serving | Planned | Routing、failover、rolling update |
| M5–M7 — Control Plane | Planned | Memory Supervisor、Scheduler Plugin、LLM Autoscaler |
| M8 — Multi-Runtime Benchmark | Planned | 统一 workload 下的 runtime comparison |
| M9 — Production Simulation | Planned | 跨 Plane failure、recovery 与 capacity evaluation |
| M10 — Distributed Extensions | Optional | NCCL、Tensor Parallel 与跨节点 failure boundary |

每个 Milestone 的范围和 Exit Criteria 见 [Roadmap](docs/Roadmap.md)。

## M0 Highlights

- 两台节点的 host CUDA、digest-pinned PyTorch GPU-container smoke 和四层 bootstrap replay 均通过。
- 固定 digest 的 vLLM runtime image 在两节点完成 model load 并返回 HTTP 200；outer wrapper 的 exit `141` 被保留为 lifecycle harness limitation。
- TCP 初始 baseline 在 4 streams / 30 seconds 下记录 96.7404 Gbit/s receiver throughput；同时保留 43,506 retransmissions，因此不把它描述为 tuning limit。
- NCCL `all_reduce` 与 `all_gather` 均 exit `0`，correctness 和 out-of-bounds error 为 `0`。
- NCCL channel log 与两端 raw RDMA counter before/after 变化共同支持 built-in `NET/IB` over mlx5 RoCE 承载 collective traffic；`GDR 0`，GPUDirect RDMA 未启用。
- 官方 ARM64 镜像 smoke 已通过；Unified Memory telemetry、自建 multi-arch 镜像与 Kubernetes GPU integration 的边界已明确记录。

详细证据与限制请参见 [M0 Final Review](docs/reviews/m0-review.md)。

## M1 Current Focus

[vLLM Basics](labs/vllm-basics/README.md) 推进中。

当前工作集中在：

- Offline inference 与 OpenAI-compatible online serving；
- Prefill、Decode、KV Cache、PagedAttention、Continuous Batching；
- request-level TTFT、TPOT、E2E、token throughput 与 success/failure；
- `1 / 2 / 4 / 8 / 16` concurrency sweep，并按证据逐级寻找 saturation；
- short/long input-output workload shape；
- Grace Blackwell Unified Memory 下的 performance knee 与 capacity boundary。

Streaming client 会测量 first generated content；在验证映射关系前，不把 HTTP chunk interval 直接声称为 token-level ITL。

## Experiment Method

与 M0 的严格 evidence/publication framework 不同，M1 起使用 [Lightweight Experiment Repository Convention](docs/experiments/README.md)：

- 固定 Runtime、model/revision、配置和 workload；
- 一次只改变一个关键变量；
- warm-up 与 measured run 分开；
- 保留 raw result，derived summary 可以重新生成；
- timeout、OOM、non-zero exit 和其他失败不删除；
- Observed Fact、Interpretation 与 Hypothesis 分开书写。

Private run 使用 `artifacts/private/<milestone>/<run-id>/`；人工确认并脱敏后的 representative result 才进入 `benchmarks/raw-results/<experiment-family>/<run-id>/`。

## Repository Navigation

| 路径 | 用途 | 当前状态 |
|---|---|---|
| [`labs/`](labs/) | 学习与机制实验 | vLLM Basics Labs 0–4、kind basics 已存在 |
| [`serving/`](serving/) | Inference runtime 的可复用启动与配置 | M1 planned |
| [`control-plane/`](control-plane/) | Controller、Scheduler、Autoscaler | M5–M7 planned |
| [`observability/`](observability/) | Metrics、dashboard、recording rule、alert | M3 planned |
| [`workloads/`](workloads/) | Workload contract 与 load generation | M1/M3 planned |
| [`benchmarks/`](benchmarks/) | Config、public raw result、analysis、report | 当前含 M0 public raw results；M1 report planned |
| [`deployments/`](deployments/) | Host bootstrap 与后续 Kubernetes deployment | M0 bootstrap 已存在；M2 planned |
| [`distributed/`](distributed/) | NCCL baseline 与 distributed inference extension | M0 NCCL tests 已存在；M10 model parallel optional |
| [`docs/`](docs/) | Roadmap、ADR、environment、SLO、review、后续 architecture/runbook | 持续维护 |

Planned 路径按对应 Milestone 落地；本 README 不把目标目录写成现有实现。

## Roadmap / Showcase Navigation

| Reviewer 关注点 | 首选入口 |
|---|---|
| 项目路线与完成标准 | [`docs/Roadmap.md`](docs/Roadmap.md) |
| 当前 Runtime 学习与 M1 起点 | [`labs/vllm-basics/`](labs/vllm-basics/README.md) |
| 实验约定 | [`docs/experiments/`](docs/experiments/README.md) |
| Benchmark 结论 | `benchmarks/reports/` — M1 起逐步落地 |
| Architecture | `docs/architecture/` — planned；当前决策见 [ADR-0001](docs/adr/ADR-0001-dgx-spark-primary-testbed.md) |
| Control Plane 实现 | `control-plane/` — M5–M7 planned |
| Observability 实现 | `observability/` — M3 planned；当前输入见 [SLO draft](docs/SLO/inference-service-slo.md) |

M0 closeout 文档保留为历史与深入审阅资料，但不是后续 Milestone 的默认模板或普通 reviewer 的第一阅读路径。
