# Project Context

## 1. 项目定位

本项目以 AI Infra / AI Platform 相关岗位需求为职业目标，建设一个面向真实生产环境的：

> **Kubernetes-Native LLM Inference Platform**

项目使用两台 **DGX Spark** 作为主要 GPU 实验节点，围绕大模型推理服务、GPU 与内存资源治理、Kubernetes 控制面、可观测性、弹性伸缩和分布式通信，完成一套可复现、可测量、可解释的 AI Infra 实践。

本项目不是为了实现一个完整商业化 AI 平台，也不是单纯完成若干组件部署，而是通过受控实验理解现代 AI 基础设施中的关键机制，并形成可以被技术面试官、平台工程师和基础设施工程师审阅的工程证据。

项目的核心定义是：

> A two-node Grace Blackwell inference testbed for validating Kubernetes-native serving, scheduling, unified-memory governance, observability, failure handling, and distributed inference mechanisms.

两台 DGX Spark 不应被描述为生产等价的 DGX 集群，其实验结论也不能直接外推至大规模 H100、H200 或 B200 集群。

---

## 2. 职业目标

项目主要服务于以下职业方向：

* AI Infrastructure Engineer
* AI Platform Engineer
* LLM Inference Infrastructure Engineer
* Kubernetes Platform Engineer
* GPU Infrastructure Engineer
* Distributed Systems Engineer

目标能力不是单纯“会调用或部署大模型”，而是能够：

* 设计和运行推理基础设施；
* 理解 Runtime、GPU、网络和调度之间的关系；
* 建立可复现的 Benchmark；
* 通过 Metrics、SLO 和实验结果定位瓶颈；
* 使用 Kubernetes Controller、Scheduler 和 Autoscaler 实现控制机制；
* 分析容量、可靠性、故障域和生产运行风险。

用户已有的企业级系统、平台工程、CI/CD、ETL、数据库治理、云迁移、生产支持和可观测性经验，是本项目的基础能力资产。

项目重点补齐：

* Kubernetes 控制面开发；
* LLM Serving Runtime；
* GPU 与统一内存；
* NCCL 与高速网络；
* 推理 Benchmark；
* LLM-aware scheduling；
* AI 平台 SRE 与生产治理。

---

## 3. 学习原则

项目整体学习节奏按约 **理论 6：实操 4** 设计。

每个知识点必须同时回答：

1. 它解决什么生产问题；
2. 它在系统中的位置是什么；
3. 它依赖哪些底层机制；
4. 如何通过实验观察其行为；
5. 如何证明结论；
6. 在什么条件下结论不成立。

学习过程中避免只记忆术语或执行命令。

每个知识点应尽量拆分为独立 Thread，减少上下文混乱。长期决策和最终结论写入仓库，聊天主要用于分析、学习、方案讨论和问题定位。

---

## 4. 项目架构

项目划分为四个 Plane。

```text
                         Client / Load Generator
                                   |
                                   v
                         API / Gateway Layer
                                   |
                                   v
+----------------------------------------------------------------+
|                    Serving Data Plane                          |
|       vLLM / SGLang / llama.cpp / TensorRT-LLM                 |
+----------------------------------------------------------------+
            |                                  ^
            | metrics / state                  | control actions
            v                                  |
+---------------------------+      +-----------------------------+
| Observability Plane       |      | Control Plane               |
| Prometheus / Grafana      |      | Memory Supervisor           |
| GPU Exporter / SLO        |      | Scheduler Plugin            |
| Alerts / Runbooks         |      | LLM-Aware Autoscaler        |
+---------------------------+      +-----------------------------+
            ^                                  ^
            |                                  |
            +----------------------------------+
                           |
+----------------------------------------------------------------+
|               Workload & Experiment Plane                      |
| benchmark / burst / long-context / noisy-neighbor / failures   |
+----------------------------------------------------------------+
```

该架构已在项目 Parent README 中定义，核心是让 Serving、Control、Observability 和 Experiment 形成可验证的闭环，而不是作为互不关联的组件集合。

---

## 5. Serving Data Plane

Serving Data Plane 负责模型加载、请求调度、推理执行、KV Cache 管理和 API Serving。

优先 Runtime：

1. vLLM
2. SGLang
3. TensorRT-LLM
4. llama.cpp
5. Ray Serve 或 Triton Inference Server 作为扩展集成

核心知识：

* Transformer inference execution path
* Tokenization
* Prefill
* Decode
* KV Cache
* PagedAttention
* Continuous Batching
* Prefix Cache
* Request Scheduler
* Admission Control
* CUDA Graph
* Quantization
* Model Loading
* Tensor Parallel

vLLM 是第一基线 Runtime。其学习目标不只是启动 OpenAI-compatible API，而是理解模型加载、Prefill、Decode、KV Cache、调度和并发行为，并建立可重复的单节点 Serving Baseline。

主要性能指标：

* Time to First Token，TTFT
* Inter-Token Latency，ITL
* Time per Output Token，TPOT
* End-to-End Latency
* Request Throughput
* Input Token Throughput
* Output Token Throughput
* Goodput
* GPU Utilization
* Memory Usage
* KV Cache Utilization
* Error / Timeout / OOM Rate

---

## 6. Control Plane

Control Plane 负责管理推理工作负载的生命周期、资源压力、调度和容量。

项目计划实现三个主要组件。

### 6.1 Unified Memory & KV Cache Supervisor

监控并组合以下信号：

* Host / System Memory
* cgroup v2 memory accounting
* Memory PSI
* Kubernetes QoS
* GPU / Unified Memory
* KV Cache Utilization
* Active Sequences
* Waiting Requests
* Runtime Preemption
* OOM Risk

目标不是简单监控内存，而是实现可解释的保护策略，例如：

* Warning；
* Admission Control；
* Load Shedding；
* Low-Priority Rejection；
* Rate Limiting；
* Protective Scaling。

该组件需要使用 Kubernetes CRD 和 Controller Reconciliation Loop 实现，并暴露决策原因、状态和指标。

### 6.2 GPU / Model Locality-Aware Scheduler

基于 Kubernetes Scheduler Framework 实现推理工作负载的 Filter 和 Score 逻辑。

候选信号：

* GPU / Unified Memory Capacity
* Model Cache Locality
* Image Cache Locality
* Existing Runtime Load
* Queue Pressure
* Node Pressure
* Cold-Start Cost
* Replica Distribution
* Network Topology

两台 DGX Spark 硬件同构，因此实验重点不是异构 GPU 型号选择，而是验证模型局部性、节点压力和冷启动成本。

### 6.3 LLM-Aware Autoscaler

Autoscaler 不应只依赖 CPU Utilization。

候选扩缩容信号：

* Waiting Request Count
* Queue Latency
* Running Requests
* TTFT
* Goodput
* SLO Violation Rate
* KV Cache Pressure
* GPU Utilization
* Error-Budget Burn Rate

实验需要比较：

* CPU HPA；
* GPU Utilization；
* KEDA；
* Prometheus Custom Metrics；
* 自定义 Autoscaler。

---

## 7. Observability Plane

Observability Plane 负责将基础设施、GPU、Runtime 和服务质量数据关联在同一时间轴上。

目标不是制作展示型 Dashboard，而是支持：

* 性能分析；
* 故障诊断；
* 容量判断；
* 控制面决策；
* SLO 计算；
* Incident Response。

监控层级包括：

### Kubernetes Layer

* Node CPU / Memory
* Pod CPU / Memory
* Restart Count
* OOMKilled
* Pending Pod
* Eviction
* Node Pressure
* cgroup Throttling

### GPU / Memory Layer

* GPU Utilization
* Unified Memory Usage
* Temperature
* Power
* PCIe / Network Activity
* GPU Error Events

### Runtime Layer

* Request Rate
* Running / Waiting Requests
* TTFT
* TPOT / ITL
* Token Throughput
* Active Batch
* KV Cache Usage
* Prefix Cache
* Failed Requests

### Service-Level Layer

* Availability
* P95 / P99 Latency
* Goodput
* SLO Compliance
* Error Budget
* Saturation
* Scaling Effectiveness

目标技术栈：

* Prometheus
* Grafana
* Alertmanager
* Node Exporter
* kube-state-metrics
* NVIDIA DCGM Exporter
* Prometheus Adapter 或 KEDA
* 可选 OpenTelemetry / Loki

---

## 8. SLO 设计原则

LLM Serving 的 SLO 必须绑定明确的 Workload Class。

完整 SLO 应包含：

* Service；
* Workload Class；
* SLI；
* Objective；
* Statistical Window；
* Eligible Requests；
* Exclusions；
* Data Source；
* Violation Action。

不能将短 Prompt、短输出请求和长上下文、长输出请求放在同一延迟目标下。

项目第一版重点关注：

* Availability；
* P95 / P99 TTFT；
* P95 / P99 ITL 或 TPOT；
* Timeout Rate；
* OOM Failure Rate；
* Goodput。

Goodput 只统计满足服务质量要求的已完成请求。高 Raw Throughput 不代表高 Goodput，也不代表服务质量良好。

---

## 9. Workload & Experiment Plane

所有平台结论必须通过受控 Workload 和 Experiment 验证。

目标场景：

* Constant Traffic
* Concurrency Sweep
* Burst Traffic
* Prefill-Heavy Workload
* Decode-Heavy Workload
* Long Context
* Shared Prefix
* Mixed Input / Output Length
* Mixed-Priority Tenant
* CPU / Memory Noisy Neighbor
* KV Cache Pressure
* Model Cold Start
* Pod Failure
* Node Failure
* Rolling Update
* Autoscaling Oscillation
* Runtime Partial Degradation
* Network / NCCL Failure

每个实验必须定义：

* Hypothesis；
* Environment；
* Hardware / Software Version；
* Model / Revision / Precision；
* Independent Variables；
* Controlled Variables；
* Workload Distribution；
* Metrics；
* Success Criteria；
* Raw Results；
* Interpretation；
* Limitations；
* Follow-up Actions。

禁止同时改变多个关键变量后直接下结论。

---

## 10. 硬件与实验环境

主要实验环境为两台 DGX Spark。

重点硬件和平台特征：

* ARM64 / SBSA
* Grace Blackwell
* Unified Memory Architecture
* NVIDIA Driver / CUDA
* ConnectX-7
* 200 Gb/s 高速数据链路
* NVIDIA Container Runtime
* Docker / Containerd
* Kubernetes GPU Integration
* NCCL
* MPI

普通 x86_64、Windows、WSL2 或 VM 环境主要承担：

* 代码开发；
* CI；
* 控制面；
* Kubernetes Control Plane；
* 文档；
* Load Generator；
* 轻量级服务。

所有实验必须明确区分：

* Management Network；
* Data Network；
* TCP；
* RDMA；
* GPUDirect RDMA；
* NCCL Transport。

不能仅凭高速 NIC 存在、NCCL 成功或吞吐较高，就宣称 RDMA 或 GPUDirect RDMA 已生效。

---

## 11. Milestone Roadmap

项目采用 M0–M10 的递进路线。

### M0 — Platform Qualification

建立可信、可重复的硬件、软件、容器、网络与 NCCL 环境基线。

### M1 — Single-Node vLLM Baseline

理解 Runtime，并建立单节点推理性能、容量和延迟基线。

### M2 — Kubernetes Foundation

将 DGX Spark 纳入 Kubernetes，并部署 GPU Workload。

### M3 — Observability & SLO

建立 Metric Contract、Workload Contract、Dashboard、Alert 和初始 SLO。

### M4 — Two-Replica Serving

在两台 Spark 上运行独立推理副本，研究路由、扩展和故障域。

### M5 — Unified Memory Supervisor

实现统一内存、KV Cache 和队列压力保护控制器。

### M6 — Locality-Aware Scheduler

实现模型局部性和压力感知的 Scheduler Plugin。

### M7 — LLM-Aware Autoscaler

实现 Queue、TTFT、Goodput 和 SLO 驱动的弹性控制。

### M8 — Multi-Runtime Benchmark

在统一实验合同下比较至少两个推理 Runtime。

### M9 — Production Simulation

完成跨 Plane 的压力、故障、升级和恢复演练。

### M10 — Distributed Extensions

可选扩展，研究 NCCL、Tensor Parallel 和跨节点模型并行。

完整 Roadmap 已对每个 Milestone 的目标、知识、产出、实验、Exit Criteria 和扩展方向作出定义。

---

## 12. 当前优先级

项目的知识优先级如下。

### 第一优先级

* Kubernetes

  * Scheduler
  * Operator
  * CRD
  * GPU Scheduling
* vLLM

  * Deployment
  * Benchmark
  * Continuous Batching
  * KV Cache
  * Prefix Cache
  * PagedAttention
* Prometheus

  * Metrics
  * Grafana
  * GPU Exporter

### 第二优先级

* GPU
* CUDA Basics
* Memory Hierarchy
* Kernel
* CUDA Stream
* NCCL

### 第三优先级

* SGLang
* TensorRT-LLM
* Triton
* Ray Serve

### 第四优先级

* Agent
* Workflow
* MCP
* Tool Calling
* Context Cache
* Prompt Cache

该优先级来自目标 AI Infra 岗位与用户现有平台工程能力之间的差距分析。相比重新转向游戏业务后端，本项目更强调训练与推理基础设施、在线服务、GPU、网络、容器和调度能力。

---

## 13. Repository Structure

目标仓库结构：

```text
ai-inference-platform/
├── control-plane/
│   ├── memory-supervisor/
│   ├── scheduler-plugin/
│   └── llm-autoscaler/
│
├── serving/
│   ├── vllm/
│   ├── sglang/
│   ├── llama-cpp/
│   └── tensorrt-llm/
│
├── observability/
│   ├── prometheus/
│   ├── grafana/
│   ├── alertmanager/
│   └── recording-rules/
│
├── workloads/
│   ├── load-generator/
│   ├── scenarios/
│   ├── contracts/
│   └── datasets/
│
├── benchmarks/
│   ├── configs/
│   ├── raw-results/
│   ├── analysis/
│   └── reports/
│
├── deployments/
│   ├── bootstrap/
│   ├── kind/
│   ├── kubernetes/
│   └── helm/
│
├── distributed/
│   ├── nccl-tests/
│   └── tensor-parallel/
│
├── docs/
│   ├── context/
│   ├── environment/
│   ├── architecture/
│   ├── design/
│   ├── adr/
│   ├── deployment/
│   ├── observability/
│   ├── slo/
│   ├── runbooks/
│   ├── reviews/
│   └── postmortems/
│
└── README.md
```

---

## 14. Evidence Standard

每个 Milestone 至少应保留六类证据：

1. **Design**

   * 目标；
   * 范围；
   * 架构；
   * 关键决策。

2. **Code**

   * 实现；
   * 配置；
   * 脚本；
   * 测试。

3. **Experiment**

   * 假设；
   * 变量；
   * 控制条件；
   * 执行命令。

4. **Raw Evidence**

   * CSV；
   * JSONL；
   * Log；
   * Prometheus Snapshot；
   * Profiler Output；
   * Environment Fingerprint。

5. **Analysis**

   * 结果；
   * 解释；
   * 瓶颈；
   * 置信度；
   * 限制；
   * 后续动作。

6. **Operations**

   * Alert；
   * Runbook；
   * Incident Timeline；
   * Postmortem；
   * Recovery Procedure。

以下情况不视为完成：

* 仅截图证明服务启动；
* 只记录平均延迟；
* 没有定义 Workload；
* 删除失败结果；
* 只保留整理后的 Summary；
* 同时改变多个变量后下结论；
* 将推测写成事实；
* 将模拟结果描述为真实硬件结果；
* 将 DGX Spark 数据直接外推至数据中心 GPU 集群。

---

## 15. 事实、解释与假设

文档和审阅必须明确区分：

### Observed Fact

由命令、日志、指标或原始数据直接支持的事实。

### Interpretation

根据证据得出的工程解释。

### Hypothesis

仍需要进一步实验验证的可能原因或机制。

### Unknown

当前证据不足以判断的事项。

推荐结果表：

| Claim                                      | Type       | Evidence                              | Confidence | Follow-up                              |
| ------------------------------------------ | ---------- | ------------------------------------- | ---------- | -------------------------------------- |
| CUDA kernel executed successfully          | Fact       | smoke-test log                        | High       | None                                   |
| NCCL used built-in `NET/IB` over mlx5 RoCE | Fact       | NCCL channel/provider lines           | High       | Preserve exact run context             |
| RDMA traffic was active                    | Fact       | NCCL log plus raw both-end RDMA deltas | High       | Raw deltas preserved; future parser fixed |
| Enabling GDR would improve this testbed     | Hypothesis | No controlled comparison              | Low        | Version-aligned A/B test               |

Codex 和人工审阅都不得在缺少证据时将 Hypothesis 升级为 Fact。

---

## 16. 文档语言与编码规范

项目展示型和设计型文档以中文为主，保留必要英文术语。

代码、文件名、API、Metrics 和 Kubernetes Resource 名称优先使用英文。

文档应：

* 使用 Markdown；
* 保留命令；
* 标明版本；
* 链接原始证据；
* 避免模糊的“效果很好”“性能明显提升”等描述；
* 尽量使用可量化语言；
* 明确 Known Limitations。

代码应：

* 配置与逻辑分离；
* 避免本机绝对路径；
* 使用明确错误处理；
* 保留失败数据；
* 支持非交互执行；
* 适合 CI；
* 标注版本敏感接口；
* 优先提供机器可读输出。

---

## 17. Codex 使用规则

Codex 进入仓库后，应优先读取：

1. `AGENTS.md`
2. `README.md`
3. `docs/Roadmap.md`
4. `docs/context/project-context.md`
5. `docs/context/current-status.md`
6. 当前任务对应的 Review Brief

Codex 的主要职责：

* 阅读仓库真实状态；
* 检查实现与文档是否一致；
* 映射 Milestone Exit Criteria；
* 审阅脚本和代码；
* 执行非破坏性验证；
* 标记缺失证据；
* 生成 Diff；
* 提高可重复性；
* 形成 Review Report。

Codex 不应：

* 虚构 Benchmark 数据；
* 修改 Raw Results；
* 将 Summary 当作唯一证据；
* 忽略失败日志；
* 未经授权执行破坏性命令；
* 将版本敏感命令视为普遍有效；
* 根据项目目标假定某项工作已经完成。

---

## 18. 项目完成标准

核心项目不依赖 M10 即可完成。

核心完成标准：

* 两台 DGX Spark 完成可重复的环境认证；
* 单节点 vLLM Baseline 建立；
* Kubernetes GPU Serving 可部署、升级和恢复；
* Node、Memory、GPU、Runtime 和 SLO Metrics 可关联；
* 双副本服务完成扩展和故障实验；
* 至少一个推理资源治理 Controller 完成；
* Scheduler 或 Autoscaler 至少一个完成默认机制对比；
* 至少两个 Runtime 完成统一 Benchmark，或兼容性阻塞得到充分证明；
* 至少四类生产场景完成实验；
* SLO、Goodput 和 Capacity Boundary 被用于评价系统；
* ADR、Benchmark Report、Runbook、Postmortem 和 Known Limitations 完整；
* 整个仓库能够被解释为一个连贯的 Kubernetes-native LLM inference platform。

最终成果不应只是：

> 成功在 GPU 上运行了一个模型。

而应是：

> 建立了一套可复现、可测量、可控制、可诊断的 Kubernetes-native LLM inference platform，并通过原始证据解释其性能、容量、调度、内存和故障行为。
