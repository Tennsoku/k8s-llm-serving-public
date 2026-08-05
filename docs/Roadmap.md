# High-Level Roadmap

用两台 **DGX Spark** 作为主要 GPU 实验节点，并保留普通 x86_64 / WSL2 / VM 环境承担代码开发、CI、控制面和轻量负载生成。

该实现不把两台设备描述为生产等价的 DGX 集群，而是定位为：

> A two-node Grace Blackwell inference testbed for validating Kubernetes-native serving, scheduling, unified-memory governance, observability, failure handling, and distributed inference mechanisms.

Roadmap：

```text
环境确认
  -> 单节点推理基线
  -> Kubernetes 承载
  -> 指标与 SLO
  -> 双副本服务
  -> 控制面组件
  -> 多运行时比较
  -> 故障与生产模拟
  -> 分布式高级扩展
```

每个 Milestone 都必须形成可审阅的文档、代码、原始实验数据和结论；不能仅以“成功启动组件”作为完成标准。

---

## M0 — Platform Qualification & Reproducible Environment

### 目标

确认两台 DGX Spark 的硬件、系统、网络和容器能力，建立可重复的开发与实验环境，并识别 ARM64、Grace Blackwell、统一内存和 Kubernetes GPU 集成的兼容性边界。

这一阶段的目的不是开始跑性能数字，而是建立后续所有 Benchmark 的可信基础。

### High-level Knowledge

- DGX OS、Ubuntu、ARM64 与 `linux/arm64`
- NVIDIA Driver、CUDA Runtime、PyTorch CUDA Build
- Grace Blackwell 与 Unified Memory Architecture
- Docker / Containerd / NVIDIA Container Toolkit
- OCI multi-architecture image
- Kubernetes Node、RuntimeClass、Device Plugin
- ConnectX-7、管理网络与数据网络
- NCCL、MPI 和基础 Collective Communication
- Benchmark reproducibility 与环境指纹

### Output

```text
docs/environment/
├── dgx-spark-inventory.md
├── software-compatibility-matrix.md
├── network-topology.md
├── network-baseline.md
├── nccl-baseline.md
├── benchmark-environment-template.md
└── qualification-notes.md

deployments/bootstrap/
├── verify-host.sh
├── verify-container-runtime.sh
├── verify-gpu-container.sh
└── verify-network.sh

distributed/nccl-tests/
├── README.md
└── scripts/
    ├── nccl-m0-test-all-reduce.sh
    ├── nccl-m0-test-all-gather.sh
    └── verify-mpi.sh

# private raw evidence; never publish directly
artifacts/m0-private/<run-id>/ 

# sanitized publication copy; pending closeout
benchmarks/raw-results/m0-platform-qualification/<run-id>/

docs/adr/
└── ADR-0001-dgx-spark-primary-testbed.md

docs/reviews/
└── m0-review.md
```

至少记录：

- 两台机器的硬件与配置摘要（使用逻辑节点标签；物理标识不属于 M0 criterion）
- Ubuntu、Kernel、Driver、CUDA、Python、PyTorch 版本
- 容器运行时版本
- ARM64 镜像兼容性
- GPU 在宿主机和容器内的可见性
- 两节点管理网络与高速链路拓扑
- 已知不兼容组件及替代方案

### 实验

- [x] 宿主机 CUDA smoke test。
- [x] 容器内 CUDA / PyTorch smoke test。
- [x] vLLM 最小模型加载测试。
- [-] ARM64 自建镜像和 multi-arch CI 测试。
- [x] 两节点 TCP 带宽与延迟基线。
- [x] NCCL `all_reduce` / `all_gather` 基线。
- [x] 两节点在 captured commit 且 tracked worktree clean 的状态下完成 bootstrap qualification scripts 重放。
- [-] clean-machine provisioning / reboot recovery 测试未执行；M0 不作此声明，列为 trivial、non-blocking evidence hardening。

### Exit Criteria

- [x] 两台 Spark 均能在 M0 qualification smoke scope 内运行 GPU 容器。
- [x] 关键运行版本、PyTorch/vLLM 实际执行镜像 digest 和系统配置已记录。
- [x] vLLM 或选定基础 Runtime 可在单台 Spark 上加载最小模型。
- [x] 两节点网络基线已测量并区分管理链路与分布式数据链路。
- [x] 两节点均在 captured commit 且 tracked worktree clean 的状态完成四层 verification replay；不声称 clean-machine provisioning 或 reboot recovery。
- [x] ARM64、统一内存和 GPU Operator / Device Plugin 的已知边界已形成文档；Kubernetes 集成实测延至 M2。
- [x] 后续 Benchmark 可以通过固定模板记录完整实验上下文。

`[-]` 表示已明确记录并接受的部分完成项或后续 Milestone 延期项，不等同于已通过。

### 可选扩展

- Nix / Ansible 环境固化
- 本地镜像 Registry
- SBOM 与镜像签名
- Firmware / Driver 升级回滚流程
- 自动生成 environment fingerprint

---

## M1 — Single-Node vLLM Serving Baseline

### 目标

在脱离 Kubernetes 的条件下理解 vLLM 的核心执行路径，建立单节点、单运行时、可重复的推理基线，并找出第一组容量与延迟拐点。

此阶段应先理解 Runtime，再进入平台编排；不能把 Kubernetes 噪声混入最初的性能结论。

### High-level Knowledge

- Transformer inference execution path
- Tokenization、Prefill、Decode
- KV Cache、KV Block 与容量估算
- PagedAttention
- Continuous Batching
- Request Scheduler 与 Admission
- TTFT、ITL、TPOT、E2E Latency
- Request Throughput、Token Throughput、Goodput
- Warm-up、CUDA Graph、Cold Start
- Unified Memory 下的模型权重、KV Cache 和系统内存关系

### Output

```text
labs/vllm-basics/
serving/vllm/
benchmarks/configs/vllm-single-node/
benchmarks/raw-results/vllm-single-node/
benchmarks/reports/vllm-single-node-baseline.md
```

包括：

- Offline inference 示例
- OpenAI-compatible server 启动脚本
- Streaming / non-streaming client
- Async concurrent load generator
- 标准 workload 配置
- 原始 request-level CSV / JSONL
- GPU、内存与 Runtime 参数记录
- 第一版瓶颈假设

### 实验

1. Cold start 与 warm start 对比。
2. Concurrency sweep：`1 / 2 / 4 / 8 / 16 / saturation`。
3. Short-input / short-output。
4. Short-input / long-output。
5. Long-input / short-output。
6. Long-input / long-output。
7. `max_model_len`、`max_num_seqs`、memory utilization 参数扫描。
8. Small / Medium 模型容量和吞吐对比。
9. 统一内存使用量随模型、上下文和并发变化的曲线。

### Exit Criteria

- [ ] Offline 与 online serving 均可通过脚本复现。
- [ ] Streaming client 能记录 TTFT 和 token timestamp。
- [ ] 每组实验区分 warm-up 与 measured runs。
- [ ] 所有失败、timeout、OOM 和 server restart 均被保留。
- [ ] 已获得稳定的 TTFT、ITL/TPOT、E2E、吞吐和内存数据。
- [ ] 已识别至少一个性能拐点和一个容量边界。
- [ ] 能解释 Prefill-heavy 与 Decode-heavy workload 的差异。
- [ ] 结论基于原始数据，而非单次观察。

### 可选扩展

- Prefix Cache
- Chunked Prefill
- Quantization：BF16 / FP8 / INT4
- Speculative Decoding
- CUDA Graph 开关对比
- 70B 量化模型的容量边界测试

---

## M2 — Kubernetes Foundation & GPU Workload Deployment

### 目标

建立可重复的 Kubernetes 集群，将 DGX Spark 作为 GPU Worker 纳入集群，并把单节点 vLLM Baseline 转化为可部署、可升级、可恢复的 Kubernetes Workload。

推荐拓扑：

```text
x86_64 / VM Control Plane
├── Kubernetes API / Scheduler / Controllers
├── Prometheus / Grafana
└── Load Generator

DGX Spark A
└── GPU Worker A

DGX Spark B
└── GPU Worker B
```

若必须在 Spark 上承载控制面，需要在 Benchmark 中明确记录 control-plane noise。

### High-level Knowledge

- Kubernetes Control Plane 与 Worker Node
- Pod、Deployment、Service、ConfigMap、Secret
- Requests、Limits、QoS、Eviction
- RuntimeClass 与 NVIDIA Container Runtime
- Device Plugin、Extended Resource
- Node Label、Taint、Toleration、Affinity
- Liveness、Readiness、Startup Probe
- Graceful Shutdown 与 Pod Termination
- Persistent model cache
- Helm / Kustomize
- ARM64 容器构建和调度约束

### Output

```text
deployments/kubernetes/
├── base/
├── overlays/dgx-spark/
└── bootstrap/

serving/vllm/chart/
docs/deployment/kubernetes-cluster.md
docs/deployment/vllm-on-dgx-spark.md
docs/adr/ADR-0002-gpu-integration-strategy.md
```

### 实验

1. 普通 CPU workload 调度和资源限制验证。
2. GPU Pod 资源申请与设备可见性验证。
3. vLLM Deployment 单副本部署。
4. Model cache cold / warm start 对比。
5. Readiness 与 Startup Probe 行为。
6. Pod 删除、重建和 graceful shutdown。
7. 节点 taint、affinity 和指定节点部署。
8. Spark A / B 间的同配置可重放测试。

### Exit Criteria

- [ ] 集群可通过文档和脚本重建。
- [ ] 两台 Spark 均以 GPU Worker 身份稳定加入集群。
- [ ] GPU workload 使用明确的 resource request 调度。
- [ ] vLLM Deployment 和 Service 可重复部署。
- [ ] Probe 能正确区分加载中、可服务和异常状态。
- [ ] Pod 重启不会造成不可解释的模型缓存或数据状态。
- [ ] ARM64、GPU Runtime 和镜像依赖均被版本固定。
- [ ] 单节点 Kubernetes 结果与 M1 裸机基线差异得到记录。

### 可选扩展

- Helm Chart 发布
- GitOps：Argo CD / Flux
- Local Registry 与 image pre-pull
- Model artifact init container
- PodDisruptionBudget
- Canary / Blue-Green deployment

---

## M3 — Observability Foundation, Workload Contract & Initial SLO

### 目标

使平台从“能运行”升级为“可测量、可解释、可告警”，并建立所有后续控制器共同依赖的指标契约、负载分类和第一版 SLO。

### High-level Knowledge

- RED / USE Method
- Prometheus metric types
- Counter、Gauge、Histogram、Summary
- Histogram bucket 与 percentile
- PromQL、Recording Rule、Alert Rule
- kube-state-metrics、Node Exporter
- GPU / Unified Memory telemetry
- vLLM runtime metrics
- SLI、SLO、Error Budget、Burn Rate
- Workload Class 与 Eligible Request
- Goodput 与 raw throughput 的区别
- Trace / log / metric correlation

### Output

```text
observability/prometheus/
observability/grafana/
observability/alertmanager/
observability/recording-rules/

docs/slo/inference-service-slo.md
docs/observability/metric-contract.md
docs/observability/dashboard-guide.md
workloads/contracts/workload-classes.yaml
```

至少建立：

- Cluster Dashboard
- Node / Unified Memory Dashboard
- GPU Dashboard
- vLLM Runtime Dashboard
- SLO / Goodput Dashboard
- 初始 Recording Rules
- 可执行 Alert Rules

### 实验

1. 客户端测量与服务端指标一致性校验。
2. TTFT、ITL/TPOT、E2E Histogram 精度验证。
3. 不同 workload class 的延迟分布对比。
4. 队列增长与 TTFT 上升的关联分析。
5. KV Cache / memory pressure 与失败率关联。
6. 人为触发 timeout、Pod restart 和 OOM 风险告警。
7. 根据 M1/M2 Baseline 校准第一版 SLO。

### Exit Criteria

- [ ] Kubernetes、节点、GPU/内存、Runtime 和 SLO 指标可以在统一时间轴关联。
- [ ] 能回答延迟来自排队、Prefill 还是 Decode。
- [ ] 能判断系统处于空闲、有效饱和还是无效拥塞。
- [ ] Workload class 明确规定 input/output token 边界。
- [ ] SLO 包含 SLI、阈值、统计窗口、适用范围和排除项。
- [ ] Goodput 可由请求级数据或 Recording Rule 计算。
- [ ] 至少一个告警通过受控实验触发并完成定位。
- [ ] Dashboard 可支持诊断，而非仅展示图表。

### 可选扩展

- OpenTelemetry trace
- Loki / structured log aggregation
- Exemplars
- Multi-window burn-rate alerts
- Automated benchmark-to-Grafana annotations
- SLO report generator

---

## M4 — Two-Replica Serving, Routing & Failure Domain Baseline

### 目标

让两台 DGX Spark 分别承载独立模型副本，形成第一个真实的双节点在线服务，并研究扩容收益、请求路由、模型局部性和节点故障。

这是比跨节点 Tensor Parallel 更优先的生产型 Milestone。

### High-level Knowledge

- Replica Parallelism
- L4 / L7 Load Balancing
- Round Robin、Least Connections、Least Queue
- Queue-aware routing
- Session affinity 与 cache locality
- Health checking 与 endpoint removal
- Retry、timeout、circuit breaking
- Failure domain
- Rolling update 与 graceful drain
- Capacity scaling 与 Goodput scaling

### Output

```text
gateway/
├── config/
├── routing-policy/
└── metrics/

deployments/kubernetes/vllm-replicas/
benchmarks/reports/two-replica-scaling.md
docs/adr/ADR-0003-routing-policy.md
docs/runbooks/replica-failure.md
```

### 实验

1. 单副本与双副本吞吐 / Goodput 对比。
2. Round Robin 与 Least Queue 对比。
3. 不对称负载下的 routing fairness。
4. 模型 warm cache / cold cache 节点路由。
5. Kill 一个 vLLM Pod。
6. Drain 一个 Spark Node。
7. Rolling update 期间的请求成功率和尾延迟。
8. 节点恢复后的重新纳入和流量爬坡。
9. Shared-prefix workload 下的 locality-aware routing。

### Exit Criteria

- [ ] 两个副本可独立服务并由统一入口路由。
- [ ] Gateway 能根据健康状态移除异常 endpoint。
- [ ] 单节点故障不会造成整个平台不可用。
- [ ] 双副本扩展收益通过 Goodput 而非仅 RPS 评价。
- [ ] 至少两种 routing policy 完成可重复对比。
- [ ] Failover、恢复时间和 SLO 影响已量化。
- [ ] Rolling update 期间的请求行为得到记录。
- [ ] 已形成 Replica Failure Runbook。

### 可选扩展

- Envoy / NGINX / custom Go gateway 对比
- Hedged requests
- Prefix-aware router
- Per-tenant rate limiting
- Priority queue
- Multi-model routing

---

## M5 — Unified Memory & KV Cache Supervisor

### 目标

实现项目的第一个自定义 Kubernetes Control Loop，面向 DGX Spark 的统一内存、容器内存、Runtime KV Cache 和请求队列建立风险检测与保护动作。

Memory Supervisor 不应把 Host RAM 和传统离散 GPU VRAM 简单视为互不相关的资源，而应建立统一内存节点的组合压力模型。

### High-level Knowledge

- Kubernetes CRD、Controller、Reconciliation
- Informer、Work Queue、Finalizer、Status Condition
- cgroup v2：`memory.current`、`memory.high`、`memory.max`
- PSI：`memory.pressure`
- Kubernetes QoS、OOM score、Eviction
- Unified Memory accounting
- Model weights、KV Cache reservation 与实际占用
- Queue depth、active sequence、preemption
- Admission control、load shedding、priority
- Control-loop stability、hysteresis、cooldown

### Output

```text
control-plane/memory-supervisor/
├── api/
├── controller/
├── policy/
├── metrics/
└── tests/

config/crd/
docs/adr/ADR-0004-unified-memory-pressure-model.md
docs/design/memory-supervisor.md
docs/runbooks/memory-pressure.md
benchmarks/reports/memory-protection-experiments.md
```

### 实验

1. CPU / system memory noisy neighbor。
2. 长上下文请求造成 KV Cache pressure。
3. 高并发造成 queue + cache saturation。
4. 低优先级 workload 与在线服务竞争。
5. 无保护 baseline：timeout / OOM / restart。
6. Warning-only policy。
7. Admission control / rate limit policy。
8. Low-priority rejection / eviction policy。
9. 控制动作前后 Availability、TTFT、Goodput 对比。
10. 错误信号和阈值抖动下的控制稳定性。

### Exit Criteria

- [ ] CRD 具有清晰的 Spec、Status 和 Condition。
- [ ] Controller 遵循幂等 Reconciliation。
- [ ] 压力模型至少组合系统内存、PSI、KV Cache 和队列信号。
- [ ] 所有决策、原因和动作暴露为 metric / event / status。
- [ ] Controller 不依赖单一瞬时阈值做破坏性动作。
- [ ] 在 supported workload 下实现零 OOM-caused failure，或明确记录无法满足的边界。
- [ ] 相比无保护 baseline，Goodput 或 Availability 有可量化改善。
- [ ] Controller 自身故障时不会阻断 Serving Data Plane。
- [ ] 保护策略和失败模型已形成 ADR 与 Runbook。

### 可选扩展

- Predictive pressure model
- PSI-based early warning
- KV Cache-aware request admission
- MemoryQoS integration
- Node-level eBPF observer
- Multi-tenant quota

---

## M6 — GPU / Model Locality-Aware Scheduler

### 目标

通过 Kubernetes Scheduler Framework 实现面向推理工作负载的节点选择逻辑，并与默认 Scheduler 对比调度质量、冷启动成本和 SLO 表现。

两台 Spark 硬件同构，因此本阶段重点不是 GPU 型号选择，而是验证模型局部性、可用统一内存、节点压力、队列和副本分布信号。

### High-level Knowledge

- Scheduler Framework 生命周期
- PreFilter、Filter、PreScore、Score、Reserve
- Extended Resource 与 Node Allocatable
- Node Label、Affinity、Taint
- Device Plugin data model
- Resource fragmentation
- Model locality 与 image/model cache locality
- Cold-start cost
- Queue-aware placement
- Topology-aware scheduling
- Scheduler extender 与 framework plugin 的取舍

### Output

```text
control-plane/scheduler-plugin/
├── plugin/
├── scoring/
├── config/
└── tests/

docs/design/scheduler-plugin.md
docs/adr/ADR-0005-scheduling-signals.md
benchmarks/reports/scheduler-comparison.md
```

### 实验

1. Default Scheduler baseline。
2. Model cache locality scoring。
3. Free unified-memory scoring。
4. Runtime queue / pressure scoring。
5. 单节点已有高负载时的新副本 placement。
6. 节点不可用或信号陈旧时的 fallback。
7. 调度后 cold-start time 与 SLO 的关联。
8. Scheduler restart / plugin failure 行为。

### Exit Criteria

- [ ] Plugin 使用 Scheduler Framework，而非绕过 Kubernetes 调度语义。
- [ ] Filter 与 Score 逻辑具有单元测试。
- [ ] 调度信号来源、更新频率和 stale-data 行为明确。
- [ ] Default Scheduler 作为受控 baseline。
- [ ] 自定义调度至少在一个实验中降低冷启动成本、压力失衡或 SLO violation。
- [ ] 调度失败时给出可诊断的 event / status。
- [ ] Plugin 故障具有安全 fallback，不导致集群整体不可调度。
- [ ] 设计限制明确说明两节点同构环境不能证明大规模异构 GPU 调度能力。

### 可选扩展

- Tensor Parallel gang scheduling
- Volcano / Kueue
- NCCL topology-aware placement
- Heterogeneous GPU simulation
- Model-aware descheduler
- Preemption and priority

---

## M7 — LLM-Aware Autoscaling & Capacity Control

### 目标

从 CPU-based scaling 逐步演进到基于请求队列、TTFT、KV Cache、Goodput 和 SLO burn rate 的 Serving-aware Scaling，并分析扩容收益与冷启动代价。

### High-level Knowledge

- HPA control loop
- Prometheus Adapter
- KEDA ScaledObject
- Custom Metrics / External Metrics API
- Queueing and saturation
- Waiting / running request
- TTFT、Goodput 与 SLO burn rate
- Cold-start and scale-out delay
- Stabilization window、cooldown、hysteresis
- Scale-to-zero trade-off
- Oscillation、over-scaling、under-scaling
- Capacity envelope

### Output

```text
control-plane/llm-autoscaler/
deployments/autoscaling/hpa/
deployments/autoscaling/keda/
observability/dashboards/autoscaling.json
benchmarks/reports/autoscaling-comparison.md
docs/adr/ADR-0006-autoscaling-signal.md
```

### 实验

1. CPU HPA baseline。
2. GPU utilization baseline。
3. Waiting request / queue latency scaling。
4. TTFT violation scaling。
5. KV Cache pressure scaling。
6. Composite signal scaling。
7. Burst traffic：0 -> saturation -> recovery。
8. 不同 cooldown / stabilization 配置。
9. 冷节点模型加载期间的 temporary overload。
10. 一台节点不可用时的 capacity reduction。

### Exit Criteria

- [ ] HPA、KEDA 或自定义 Autoscaler 至少完成两类 baseline。
- [ ] 扩缩容信号具有清晰的 metric contract。
- [ ] Scale-out 和 scale-in 决策可在 Dashboard 中追踪。
- [ ] Burst 场景下 TTFT / Goodput 改善得到量化。
- [ ] 不发生持续性 oscillation 或已明确其触发边界。
- [ ] 冷启动时间被纳入策略，而非仅看稳态吞吐。
- [ ] 节点容量不足时能够拒绝或降级，而非无限扩容。
- [ ] Autoscaler 故障不影响现有副本继续服务。

### 可选扩展

- Predictive autoscaling
- Scheduled pre-warming
- Multi-model scaling
- Cost-aware scaling
- Error-budget-driven scaling
- Scale-to-zero

---

## M8 — Multi-Runtime Benchmark & Runtime Selection

### 目标

在统一硬件、模型、请求分布和测量方法下比较至少两个推理 Runtime，并形成可解释的技术选型，而不是简单排名。

建议优先级：

```text
vLLM baseline
  -> SGLang
  -> TensorRT-LLM（确认 Spark / ARM64 兼容后）
  -> llama.cpp（作为 CPU / quantized / portability 对照）
```

### High-level Knowledge

- Runtime architecture
- Request scheduler 与 batching policy
- Memory allocator 与 KV Cache implementation
- Prefix cache
- Quantization
- CUDA Graph
- Kernel fusion / Triton kernel
- Continuous batching 差异
- Runtime API 与 metric surface
- Portability、operability、ecosystem trade-off

### Output

```text
serving/sglang/
serving/llama-cpp/
serving/tensorrt-llm/
benchmarks/configs/runtime-comparison/
benchmarks/raw-results/runtime-comparison/
benchmarks/reports/runtime-selection.md
docs/adr/ADR-0007-runtime-selection.md
```

### 实验

1. 相同模型、precision 和 workload 下的单并发 latency。
2. Concurrency sweep 与 saturation point。
3. Prefill-heavy / Decode-heavy workload。
4. Long-context 与 KV Cache pressure。
5. Prefix-sharing workload。
6. Cold-start / warm-start。
7. Failure behavior 和 recovery。
8. Runtime metric completeness 和运维复杂度。
9. ARM64 镜像、构建和升级成本。

### Exit Criteria

- [ ] 至少两个 Runtime 在相同 experiment contract 下完成测试。
- [ ] 模型、revision、precision、token 分布和运行参数受控。
- [ ] 原始数据和失败案例完整保留。
- [ ] 比较同时覆盖 latency、throughput、Goodput、memory、stability 和 operability。
- [ ] 能解释差异可能来自 scheduler、kernel、memory 或 cache，而非只报告数字。
- [ ] Runtime Selection ADR 绑定明确 workload 和 SLO。
- [ ] 不支持或兼容性不足的 Runtime 被如实记录，不用替代数据伪装完成。

### 可选扩展

- Ray Serve integration
- NVIDIA Triton Inference Server
- Runtime-specific speculative decoding
- Disaggregated serving runtime comparison
- Mixed-runtime routing

---

## M9 — Production Simulation, Incident Response & Final Showcase

### 目标

将 Serving、Control、Observability 和 Experiment 四个 Plane 联动，通过受控生产场景验证系统在压力、故障和变更期间的服务质量与恢复行为。

### High-level Knowledge

- Failure domain analysis
- Fault injection
- Load shedding 与 graceful degradation
- Rolling update / rollback
- Incident command and timeline
- MTTR、RTO、recovery signal
- Error budget burn
- Capacity planning
- Runbook、Postmortem、ADR
- Production readiness review

### Output

```text
workloads/scenarios/production-simulation/
docs/runbooks/
docs/postmortems/
docs/architecture/final-architecture.md
docs/architecture/failure-domain-analysis.md
benchmarks/reports/capacity-planning.md
benchmarks/reports/final-evaluation.md
showcase/
├── demo-script.md
├── architecture-diagrams/
└── evidence-index.md
```

### 实验

1. Burst traffic 与 Autoscaler delay。
2. Pod kill 与 endpoint removal。
3. Spark Node unavailable。
4. Memory / KV Cache pressure。
5. Noisy Neighbor。
6. Rolling update 与 rollback。
7. Gateway / metric pipeline partial degradation。
8. Scheduler / Controller unavailable。
9. 双故障或故障叠加场景。
10. 从告警到定位、缓解和恢复的完整演练。

### Exit Criteria

- [ ] 至少完成一次跨 Plane 的完整故障演练。
- [ ] 告警能指向可执行 Runbook。
- [ ] Incident timeline、影响范围、根因和改进项得到记录。
- [ ] 系统在单节点故障时保持定义范围内的可用性或完成可控降级。
- [ ] 关键控制器失效不会直接中断现有 Serving。
- [ ] Capacity Report 明确 supported workload、saturation point 和安全余量。
- [ ] Final Architecture 说明数据流、指标流、控制回路和 failure domain。
- [ ] Showcase 可在有限时间内复现关键实验并链接原始证据。
- [ ] 已知限制明确说明双节点 Spark 结果不可直接外推到 H100/H200/B200 大规模集群。

### 可选扩展

- Chaos Mesh / LitmusChaos
- Automated game day
- Security boundary review
- Multi-tenant isolation
- Authentication / authorization
- Cost and energy efficiency reporting

---

## M10 — Optional Distributed Inference Extensions

本 Milestone 不阻塞核心项目完成。其目的在于利用两台 Spark 的高速链路学习多节点推理和 Collective Communication，而不是替代双副本生产型路线。

### 目标

验证跨节点模型并行的容量收益、通信开销和故障边界，并比较 Replica Parallel 与 Distributed Tensor Parallel 的适用场景。

### High-level Knowledge

- Tensor Parallel
- Pipeline Parallel
- Expert Parallel
- NCCL Collective
- All-Reduce、All-Gather、Reduce-Scatter
- Communication / computation overlap
- Rendezvous、rank、world size
- Gang scheduling
- Multi-node model loading
- Prefill / Decode disaggregation
- KV transfer

### Output

```text
distributed/nccl-tests/
distributed/tensor-parallel/
benchmarks/reports/distributed-inference.md
docs/adr/ADR-0008-replica-vs-model-parallel.md
```

### 实验

1. NCCL bandwidth / latency baseline。
2. 单节点与跨节点 Tensor Parallel。
3. 可装入单节点的模型：TP 是否反而降低性能。
4. 只能跨节点装载的模型：容量收益。
5. Collective traffic 与 management traffic 隔离。
6. 链路降级、rank failure 和 collective hang。
7. Replica Parallel 与 TP 的 Goodput / Availability 对比。
8. 可行时尝试 Prefill / Decode 分离。

### Exit Criteria

- [ ] NCCL baseline 可重放并记录拓扑和链路配置。
- [ ] 至少一个跨节点模型并行 workload 成功运行，或兼容性阻塞被完整记录。
- [ ] 通信开销通过 metric / profiler 得到量化。
- [ ] 明确区分“容量扩展”和“吞吐扩展”。
- [ ] 能解释两台机器不会自动形成透明的 256GB GPU。
- [ ] Rank / link failure 行为得到记录。
- [ ] ADR 给出 Replica Parallel 与 Tensor Parallel 的场景选择依据。

### 可选扩展

- Pipeline Parallel
- Expert Parallel / MoE
- Disaggregated Prefill / Decode
- RDMA-capable external cluster comparison
- Nsight Systems profiling

---

# Milestone Dependency Map

```text
M0 Platform Qualification
 |
 v
M1 Single-Node vLLM Baseline
 |
 v
M2 Kubernetes GPU Deployment
 |
 v
M3 Observability + SLO
 |
 +----------------------+
 |                      |
 v                      v
M4 Two Replicas       M8 Multi-Runtime
 |
 +----------+-----------+
 |          |           |
 v          v           v
M5 Memory  M6 Scheduler M7 Autoscaler
  \         |          /
   +--------+---------+
            |
            v
M9 Production Simulation
            |
            v
M10 Distributed Extensions (Optional)
```

M5、M6、M7 可以在 M4 完成后部分并行，但每个控制组件都必须依赖 M3 已建立的 metric contract 和 workload contract。

---

# Milestone Evidence Standard

每个 Milestone 结束时，至少应提交以下证据：

1. **Design**：目标、范围、架构和关键决策。
2. **Code**：可执行实现、配置与测试。
3. **Experiment**：假设、变量、控制条件与运行命令。
4. **Raw Evidence**：CSV、JSONL、日志、Prometheus snapshot 或 profiler 输出。
5. **Analysis**：结果解释、瓶颈、限制和后续动作。
6. **Operations**：必要时提供 Runbook、Alert 或 Postmortem。

以下情况不视为完成：

- 仅截图证明服务启动；
- 只记录平均延迟而没有 workload 定义；
- 只保留整理后的表格而删除原始数据；
- 同时改变多个变量后直接下结论；
- 把模拟信号描述为真实 GPU / 节点实验；
- 把 DGX Spark 结果直接外推到数据中心 GPU 集群。

---

# Current Status

| Milestone | Status | Current Focus |
|---|---|---|
| M0 Platform Qualification | Technical Complete / Publish Prep | Canonical evidence 已完成；推进 fail-closed sanitized publication |
| M1 Single-Node vLLM Baseline | Next | Existing vLLM Basics labs and benchmark client |
| M2 Kubernetes GPU Deployment | Not Started | Cluster topology and GPU runtime integration |
| M3 Observability & SLO | Design Available | Initial SLO and dashboard input contract |
| M4 Two-Replica Serving | Not Started | Gateway and routing baseline |
| M5 Memory Supervisor | Planned | Unified-memory pressure model |
| M6 Scheduler Plugin | Planned | Model locality and pressure-aware scoring |
| M7 LLM Autoscaler | Planned | Queue / TTFT / Goodput-driven scaling |
| M8 Multi-Runtime Benchmark | Planned | vLLM versus second runtime |
| M9 Production Simulation | Planned | Cross-plane failure scenarios |
| M10 Distributed Extensions | Optional | NCCL and multi-node Tensor Parallel |
| Documentation | In Progress | Parent architecture, SLO, lab design |

---

# Core Definition of Done

核心项目在不依赖 M10 的情况下满足以下条件即视为完成：

- [x] 两台 DGX Spark 已完成 M0 技术资格检查；公开证据是发布 gate，不是技术结论 blocker。
- [ ] 单节点 vLLM serving baseline 已建立并保留原始请求级数据。
- [ ] Kubernetes 上的 GPU Serving Deployment 具备健康检查、优雅终止和恢复能力。
- [ ] Kubernetes、节点、统一内存、Runtime 与 SLO 指标接入统一可观测性体系。
- [ ] 两个独立推理副本通过统一入口提供服务，并完成节点故障实验。
- [ ] 至少实现一个解决推理特定资源问题的 Kubernetes Controller。
- [ ] Scheduler 或 Autoscaler 至少有一个完成与 Kubernetes 默认机制的受控对比。
- [ ] 至少两个推理 Runtime 完成统一方法下的 Benchmark，或兼容性阻塞被充分证明。
- [ ] Burst、Noisy Neighbor、Pod/Node Failure、Rolling Update 中至少四类场景完成复现。
- [ ] SLO、Goodput、Capacity Boundary 与 Error Budget 被用于评价系统，而非只使用平均吞吐。
- [ ] ADR、Benchmark Report、Runbook、Postmortem 和 Known Limitations 得到完整维护。
- [ ] 整个系统可以被清晰解释为一个连贯的 Kubernetes-native LLM inference platform。
