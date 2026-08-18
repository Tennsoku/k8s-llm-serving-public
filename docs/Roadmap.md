# Roadmap (v2)

> **版本**：v2，2026-08-15 重写。v1 的十 Milestone 全量计划保存在
> [`Roadmap-v1-archive.md`](Roadmap-v1-archive.md)，作为长期 backlog 参考，不再是执行计划。


---

## 1. 预算分配

| 阶段 | 周次 | 计划工时 |
|---|---|---:|
| **M1.5** Repackage & 呈现修复 | W1 | 12 h |
| **M2** Serving 优化实验室 | W1–W2 | 30 h |
| **M2.5** 多 adapter 准备 | W2–W3 | 12 h |
| **M3** Kubernetes 基础与 GPU workload | W3–W5 | 50 h |
| **M4** 可观测性、SLO 与 Tracing | W5–W6 | 35 h |
| **M5** 路由 / 灰度 / 伸缩 / 故障 | W6–W8 | 45 h |
| **M6** 容量成本与收尾 | W8 | 12 h |
| **缓冲** | — | 44 h |
| | | **240 h** |

### 甘特概览

```text
        W1      W2      W3      W4      W5      W6      W7      W8
M1.5   ████
M2     ████    ██████
M2.5           ██      ██
M3                     ████    ██████  ████
M4                                     ████    ██████
M5                                             ██      ██████  ████
M6                                                             ████
```

每周 30 h 的稳态构成：

```text
Milestone 工作   24.5 h/week   (196 h / 8 weeks)
缓冲              5.5 h/week   (44 h / 8 weeks)
                ───────────
                 30 h/week
```

缓冲**按周消耗、不结转**：某周没用完就用来推进 stretch 或提前开下一阶段；某周超支就从下一周的 stretch 额度里借，绝不从 exit criteria 里借。

---

## 2. M1.5 — Repackage & 呈现修复（W1，12 h）

**这不是技术 Milestone，是让前两个月的工作变得可见。** 目标是让 showcase、公开证据和项目入口在 fresh clone 中自洽；执行状态只见 [current-status](context/current-status.md)。

### 任务

| # | 任务 | 工时 |
|---|---|---:|
| 1.1 | `showcase/m1/index.json` + `comparisons.json` 的 `summary_path` 改指 `benchmarks/raw-results/m1-vllm-baseline/<run-id>/derived/summary.json`；`source_status` → `published`；开启 GitHub Pages | 3 h |
| 1.2 | 四种 workload shape 增加通用交互场景示例：短多轮对话 / 长文本生成 / 带状态上下文的问答 / 长会话 | 1 h |
| 1.3 | README 顶部 "Results at a glance" 表：模型 / 四场景 / C1 / C_eff / TTFT p95 / output TPS / 失败数 / 7B decode roofline 占比 | 2 h |
| 1.4 | README 用 3 句话记录 M1.3 prefix-cache confound、影响与修正后的结论 | 0.5 h |
| 1.5 | 加 LICENSE（Apache-2.0）；删 `.codex/config.toml`；repo description + topics | 0.5 h |
| 1.6 | GitHub Actions CI：pytest `serving/vllm/tests/` + ruff + shellcheck + jsonschema 校验 `benchmarks/configs/` | 2 h |
| 1.7 | raw-results 按 [证据留存标准](experiments/evidence-retention.md) 发布 representative evidence；完整 raw 留在 git 外，目标 clone < 10 MB | 2 h |
| 1.8 | milestone 状态收敛到 [当前状态](context/current-status.md) 单一来源，其余三处改链接 | 1 h |

### Exit Criteria

- [ ] GitHub Pages 上 showcase 的 6 个 single-run 与 4 个 comparison 全部渲染出真实数字
- [ ] clone 体积 < 10 MB
- [ ] CI 在 main 上绿
- [ ] README 前 30 行内出现至少 6 个实测数字
- [ ] 有 LICENSE，无 vendor 示例配置
- [ ] M1 的单一 Tier B Release asset 已发布，并从 milestone showcase 链接

---

## 3. M2 — Serving 优化实验室（W1–W2，30 h）

### 目标

把 v1 里列为 optional 的三项——**量化、投机解码、前缀缓存**——转为正文。

M1 的 benchmark pipeline 可直接复用；M2 的主要新增成本转为 feature compatibility smoke、模型资产和各实验 axis，而不是重建测量路径。

### 任务

| # | 任务 | 内容 | 工时 |
|---|---|---|---:|
| 2.1 | **前缀缓存 hit vs miss A/B** | 使用共享 system prompt、固定上下文与多轮历史构造 prefix-heavy workload。对照组沿用 M1.4 的 request-unique `cache_salt`，实验组共享 prefix。报告 TTFT、prefill token 节省与折算成本影响，量化前缀复用对交互式服务的作用。 | 8 h |
| 2.2 | **量化 + 精度闸门** | GB10 是 sm_121。优先 FP8 KV cache，权重 FP8（W8A8）能跑则跑。<br>**必须带精度验证**——否则无法判断吞吐或内存收益是否以不可接受的输出质量退化换取。小规模 lm-eval-harness 任务或固定 prompt 集 + 输出一致性率即可。<br>**降级路径**：固定 NGC 镜像在 sm_121 上 FP8 不可用 → INT4 AWQ/GPTQ；都不可用 → 记录为可复现的 compatibility boundary（这本身是合格结论，与 M0 边界方法论一致）。 | 12 h |
| 2.3 | **投机解码** | Qwen2.5-0.5B 作 draft、7B 作 target；或 ngram / EAGLE。报告 acceptance rate、TTFT/TPOT 变化，以及**在何种 workload shape 下反而变慢**，用于界定适用边界。 | 8 h |
| 2.4 | **长上下文** | 复用 M1.5 的 `max_model_len` OVAT，向上扩到镜像支持上限，记录 KV cache 占用曲线与 TTFT 拐点。 | 2 h |

### Exit Criteria

- [ ] 四项实验各有 raw request-level 数据与可重算 summary
- [ ] 量化实验带精度结果，或量化路径被记录为可复现的兼容性边界
- [ ] 投机解码报告 acceptance rate 与至少一个无收益/负收益场景
- [ ] 前缀缓存 A/B 给出 TTFT 与 prefill token 的量化差异，并折算为成本口径
- [ ] 所有结论进入 showcase 的 comparison 视图（复用已有 contract，不新建 UI）

---

## 4. M2.5 — 多 adapter 准备（W2–W3，12 h）

### 目标

为 M3 的 multi-adapter serving 和 M5 的 adapter-aware 路由准备**真实的多 adapter workload**。这是一个 enabler，不是训练 Milestone。

### 两条路径，按可行性择一

| 路径 | 说明 | 工时 |
|---|---|---:|
| **A（推荐）单节点轻量 LoRA 微调** | Qwen2.5-7B + LoRA，4–6 个行为可区分的 persona 或 task adapter，合成语料（**必须写清是合成的**）。只求 adapter 可加载、行为可区分，**不做训练性能优化**。顺带记录吞吐 tokens/s 与统一内存下的峰值占用——为 §9 的 optional 分布式训练留一个单节点基线 | 12 h |
| **B（降级）现成 adapter** | 若 aarch64 上 peft/训练栈不可用，直接用社区已有 LoRA，或用不同 system prompt 模拟多个 persona。**记录降级原因**，作为兼容性证据 | 4 h |

> **纪律**：这一步的验收标准是"M3 能加载 4–6 个不同 adapter 并服务"，**不是**"训练效率如何"。任何超出这个目标的训练调优都算超范围，立即停手。

### Exit Criteria

- [ ] 4–6 个可加载、行为可区分的 adapter
- [ ] 生成路径可复现（脚本或明确的下载/构造说明）
- [ ] 若走路径 B，降级原因已记录

---

## 5. M3 — Kubernetes 基础与 GPU workload（W3–W5，50 h）

### 目标

**这是全计划的第一重心。** 目标是验证 LLM workload 的可复现 Kubernetes 生命周期，而不是只完成一次 Deployment。

验收重点是 LLM workload 特有的运行约束：慢加载模型的探针设计、流式连接的优雅终止、GPU 扩展资源，以及模型缓存的存储策略。

拓扑：控制面在 x86 / VM，两台 Spark 作 GPU Worker。若控制面必须落在 Spark 上，在 benchmark 中记录 control-plane noise。

### 任务

| # | 任务 | 内容 | 工时 |
|---|---|---|---:|
| 3.1 | **集群可复现搭建** | kubeadm 或 k3s，两节点，脚本 + 文档可重建。含 CNI 选择理由、节点标签与 taint 策略。<br>**"可从零重建"是本阶段的复现性要求。** | 10 h |
| 3.2 | **GPU 接入** | device plugin / RuntimeClass / NVIDIA container runtime，GPU 作为 extended resource 被正确 request。<br>**ARM64 + GB10 上这一步的成熟度明显低于 x86**——过程中的坑与解法本身是最有价值的产出，全部记录。M0 已把此项列为未验证边界。 | 12 h |
| 3.3 | **Workload 建模与探针** | Deployment vs StatefulSet 的选择理由；requests/limits 与 QoS class；**`startupProbe` 针对 900 s 级模型加载的设计**（这是 LLM serving 的经典陷阱——用 liveness 兜加载会导致无限重启）；readiness 与 liveness 的职责分离 | 10 h |
| 3.4 | **优雅终止** | `terminationGracePeriodSeconds` + `preStop` hook，保证 Pod 删除时**进行中的流式请求不被截断**。用 M1 的 benchmark client 量化：删 Pod 时的请求失败数与截断数，以验证 K8s 生命周期与 LLM 流式响应的交互。 | 8 h |
| 3.5 | **模型缓存存储** | PVC 承载模型权重，冷启动 vs 热启动对比测量；init container 或 sidecar 的预热方案取舍 | 6 h |
| 3.6 | **打包与多 adapter 服务** | Kustomize overlay 或 Helm chart；加载 M2.5 的 4–6 个 adapter 做 multi-LoRA 共池，单次请求可指定 adapter | 4 h |

### Exit Criteria

- [ ] 集群可由脚本 + 文档从零重建，两台 Spark 以 GPU Worker 稳定加入
- [ ] GPU 通过 extended resource 被调度，容器内可见；ARM64 上的坑与解法已记录
- [ ] Probe 能正确区分「加载中 / 可服务 / 异常」；模型加载期不触发重启
- [ ] Pod 删除时进行中的流式请求不被截断，有量化数据
- [ ] 模型缓存冷/热启动差异已测量
- [ ] 多 adapter 共池可服务，单请求可指定 adapter
- [ ] K8s 单副本结果与 M1 裸机基线的差异已记录（隔离 K8s 引入的开销）

---

## 6. M4 — 可观测性、SLO 与 Tracing（W5–W6，35 h）

### 任务

| # | 任务 | 内容 | 工时 |
|---|---|---|---:|
| 4.1 | **Metrics 栈** | kube-prometheus-stack；vLLM `/metrics` 经 **ServiceMonitor** 接入，与 Operator 管理的监控栈保持一致；kube-state-metrics、node exporter、GPU / 统一内存 telemetry（DCGM 或 tegrastats，按 GB10 实际可用性选） | 10 h |
| 4.2 | **四张诊断向 Dashboard** | Serving（TTFT / TPOT / E2E / queue / KV cache）、Node & 统一内存、Runtime（running / waiting / preemption / prefix hit）、SLO & Goodput。<br>验收标准是"能回答延迟来自排队、prefill 还是 decode"，不是"图好看"。 | 8 h |
| 4.3 | **日志聚合** | Loki 或 ELK 收 vLLM server log + K8s event；能按 request id 或时间窗关联到 metrics | 5 h |
| 4.4 | **Tracing** | OpenTelemetry，能定位单请求的排队 / prefill / decode 分段 | 6 h |
| 4.5 | **SLO + 告警演练** | 用 M1/M2 实测数据校准精简后的 SLO；recording rules + alert rules；**人为制造 KV cache 压力或 timeout，真实触发一次告警 → 按 dashboard 定位 → 记录 timeline**。不接受"规则已写好" | 6 h |

### Exit Criteria

- [ ] K8s / 节点 / GPU 统一内存 / Runtime / SLO 指标在统一时间轴可关联
- [ ] 能回答"延迟来自排队、prefill 还是 decode"
- [ ] 日志可按 request 或时间窗与 metrics 关联
- [ ] 至少一条 trace 展示单请求的三段分解
- [ ] SLO objective 由 M1/M2 实测校准，含窗口、eligibility、排除项
- [ ] 至少一个告警经受控实验触发并完成定位，有 timeline 记录

---

## 7. M5 — 路由 / 灰度 / 伸缩 / 故障（W6–W8，45 h）

### 目标

本阶段验证在线服务的流量调度、灰度发布、伸缩与故障恢复，并量化这些操作对请求成功率和尾延迟的影响。

### 任务

| # | 任务 | 内容 | 工时 |
|---|---|---|---:|
| 5.1 | **网关与路由策略对比** | 两副本 + 统一入口。至少两种策略可重复对比：round-robin 基线 vs **adapter / prefix-aware 路由**（同 adapter 或同 prefix 的请求粘到同一副本，提高缓存命中）。用 Goodput 而非 RPS 评价收益 | 12 h |
| 5.2 | **健康检查与 endpoint 摘除** | 副本异常时 endpoint 自动摘除的时延测量；readiness 抖动导致的流量震荡及其抑制 | 5 h |
| 5.3 | **滚动更新与灰度** | 零中断 rolling update（配合 M3.4 的优雅终止 + PDB）；一次 canary：10% 流量切新 adapter / 新镜像版本，观测后全量或回滚。**记录整个过程的请求成功率与尾延迟** | 10 h |
| 5.4 | **弹性伸缩** | HPA 经 Prometheus Adapter 或 KEDA 消费 vLLM 的 waiting-request / KV cache 指标（**不是 CPU**——这是 LLM serving 的关键判断）。跑一次 burst：0 → 饱和 → 恢复。记录冷启动代价与是否振荡 | 10 h |
| 5.5 | **三次故障演练** | ① kill 一个 vLLM Pod → endpoint 摘除与请求成功率；② drain 一台 Spark → 容量下降与降级行为；③ KV cache 压力下的 load shedding / timeout 行为。每次留 timeline + runbook | 8 h |

### Exit Criteria

- [ ] 两种路由策略完成可重复对比，收益以 Goodput 评价
- [ ] endpoint 摘除时延已测量
- [ ] Rolling update 期间请求成功率有记录；完成一次 canary 与一次回滚
- [ ] 伸缩信号是 serving 指标而非 CPU；burst 场景含冷启动代价，振荡边界已记录
- [ ] 三次故障演练各有 timeline 与 runbook

### 明确不做

自定义 CRD / Controller（v1 M5）、自写 Scheduler Framework Plugin（v1 M6）。理由写进 `ADR-0002-platform-scope.md`：两节点同构环境无法形成有效的异构调度对照，现成方案（HPA/KEDA、PDB、Kueue）已覆盖需求，8 周窗口内投入产出比不成立。

> 若缓冲有大量余量，见 §9 的 S1——一个小而完整的 controller 可单独验证声明式控制循环，但风险高，只在前 6 周顺利时才开。

---

## 8. M6 — 容量成本与收尾（W8，12 h）

| # | 任务 | 内容 | 工时 |
|---|---|---|---:|
| 6.1 | **容量与成本报告** | `benchmarks/reports/capacity-and-cost.md`：每卡并发会话数、每百万 token 的 GPU-秒、按声明的需求模型推算可支持的活跃会话量，以及前缀命中率与量化对成本的影响 | 5 h |
| 6.2 | **最终 showcase** | 扩展 `showcase/` 覆盖 serving → K8s → 可观测 → 故障全链路；一页 mermaid 架构图 | 5 h |
| 6.3 | **证据导航** | `docs/evidence-map.md`：把 §10 的系统级验收问题映射到具体证据文件 | 2 h |

### Exit Criteria

- [ ] 容量成本报告给出每卡会话数、每百万 token 成本、活跃会话量推算
- [ ] Showcase 覆盖全链路
- [ ] 每项 §10 验收问题都能在 30 秒内定位到证据

---

## 9. Stretch / Optional（缓冲有余量时才做，按此顺序）

| # | 项目 | 工时 | 说明 |
|---|---|---:|---|
| **S1** | **小型 K8s Controller** | 25 h | CRD + reconcile loop + status conditions，做一件小事（例如按 KV cache 压力调整副本的 annotation，或 adapter 版本的声明式管理）。用于验证声明式控制循环；风险高，只在前 6 周全部按期完成时才开 |
| **S2** | **分布式训练（optional）** | 30 h | 2 节点 DDP / FSDP，跑 0.5B / 1.5B 全参数，产出扩展效率表 + NCCL 通信开销分解（复用 M0 的 RoCE 基线与 NIC counter collector）。只验证小规模多节点执行与通信成本；明确不做 Megatron / DeepSpeed / TP / PP / 大规模 MoE 训练，两节点 128 GB 的结果不外推到大规模训练 |
| **S3** | **跨节点张量并行推理** | 10 h | `TP=2` over 2 nodes 对比 replica parallel，产出 ADR：什么时候该 TP、什么时候该加副本。M0 的 NCCL 基线已完成，增量成本低 |
| **S4** | **MoE 推理** | 8 h | Qwen3-30B-A3B 或 Qwen1.5-MoE-A2.7B 单节点跑通，记录 expert 激活与内存占用 |
| **S5** | **结构化输出可靠性** | 6 h | guided decoding 的 TTFT/TPOT 开销 + schema violation rate；面向需要状态机或工具调用的下游应用 |
| **S6** | **SGLang 单点对比** | 10 h | 在同一 workload contract 下选择一个 workload shape，与 vLLM 做受控对比 |
| **S7** | **上游 vLLM 贡献** | 不定 | 遇到可复现的 upstream 问题时贡献文档、测试或小修复；**不设时间预算，机会型推进** |

> **S1 与 S2 互斥选一。** 若优先研究 Kubernetes 控制循环，选 S1；若优先研究多节点训练的执行与通信边界，选 S2。

---

## 10. 项目级验收：8 周后系统应能回答什么

这是本 roadmap 的 Definition of Done：不仅让组件运行，还要让关键系统问题都有可定位、可复查的证据。

**Kubernetes（重心）**

- [ ] 集群怎么从零重建？CNI 和节点标签为什么这么选？（M3.1）
- [ ] GPU 怎么被调度？ARM64 上遇到了什么，怎么解的？（M3.2）
- [ ] 模型要加载 15 分钟，探针怎么配才不会被无限重启？（M3.3）
- [ ] 删 Pod 的时候，正在流式返回的请求会不会被截断？（M3.4）
- [ ] 滚动更新期间请求成功率是多少？怎么做到零中断？（M5.3）
- [ ] 为什么用 waiting-request 而不是 CPU 做伸缩信号？（M5.4）
- [ ] 一台节点挂掉，服务如何降级、多久恢复？（M5.5）

**推理服务优化**

- [ ] 量化带来多少吞吐收益，付出多少精度代价？（M2.2）
- [ ] 投机解码在什么 workload 下有效、什么 workload 下反而更慢？（M2.3）
- [ ] 前缀缓存命中率对 prefix-heavy 交互服务成本的影响有多大？（M2.1）
- [ ] 多个 adapter 共池时，请求怎么调度才不互相拖累？（M3.6 + M5.1）

**可观测性与容量**

- [ ] 一个请求从进网关到返回第一个 token，时间花在哪三段？（M4.4）
- [ ] 怎么判断系统是空闲、有效饱和还是无效拥塞？（M4.2）
- [ ] 在声明的需求模型下，需要多少 GPU、可支持多少活跃会话？（M6.1）

**方法论**

- [ ] 是否记录了至少一次已识别并修正的实验偏差？（M1.3 prefix-cache confound，M1.5 写入 README）

---

## 附录 A — 相对 v1 的变更总结

| v1 | v2 处置 | 理由 |
|---|---|---|
| M2 Kubernetes | → **M3，扩到 50 h 并成为第一重心** | Kubernetes 是本项目的核心研究对象；重点验证 LLM 特有约束（慢加载探针、流式优雅终止、GPU 扩展资源） |
| M3 Observability & SLO | → M4，35 h；SLO 文档 1336 → ~200 行 | 指标语义已由 `metrics_utils.py` 覆盖，接栈成本低；SLO 规范先于系统存在是过度工程 |
| M4 双副本路由 | → **M5，与灰度/伸缩/故障合并为 45 h 的第二重心** | 将线上服务生命周期放在同一阶段做端到端验证 |
| **M5 Memory Supervisor（CRD + Controller）** | **删除**，降为 S1 optional | 3–4 周投入风险过高；保留为在主线按期完成后验证声明式控制循环的 stretch |
| **M6 Scheduler Plugin** | **删除** | 两节点同构无法形成有效的异构调度对照 |
| M7 LLM Autoscaler | → M5.4，改用 HPA / KEDA + Prometheus Adapter | 自建 autoscaler 收益不足；现成方案已经支持消费 serving 指标 |
| M8 Multi-Runtime | → S6 stretch | 锦上添花 |
| M9 Production Simulation | → M5.5，收缩为三次演练 | 保留核心，去掉九场景矩阵 |
| M10 Distributed Inference TP | → S3 stretch | M0 NCCL 已完成，增量成本低但优先级不高 |
| **（v1 无）** | **新增 M1.5 呈现修复，12 h** | showcase 在公开 repo 上打不开 |
| **（v1 无）** | **新增 M2 量化 / 投机解码 / 前缀缓存，30 h** | v1 列为 optional；现有 benchmark pipeline 可低边际成本复用 |
| **（v1 无）** | **新增 M2.5 多 adapter 准备，12 h** | multi-LoRA 服务的前置；顺带给 optional 分布式训练留单节点基线 |
| **（v1 无）** | **分布式训练列为 S2 optional，30 h** | 硬件规模只支持有界的小规模实验，优先级低于推理主线 |

---

## 附录 B — 历史 Milestone 证据入口

| Milestone | 结论入口 |
|---|---|
| **M0** Platform Qualification | [`reviews/m0-review.md`](reviews/m0-review.md) — host CUDA、GPU container、200 Gb RoCE、NCCL 基线、兼容性边界 |
| **M1** Single-Node vLLM Baseline | [`reviews/m1.3-review.md`](reviews/m1.3-review.md) + [`showcase/m1/`](../showcase/m1/) — 四场景 operating references、最小 OVAT、bounded boundary、7B 兼容性 |

M0/M1 的范围与 Exit Criteria 原文见 [`Roadmap-v1-archive.md`](Roadmap-v1-archive.md) 的对应章节。
