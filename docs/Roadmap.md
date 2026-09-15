# Roadmap (v2.2)

> **版本**：v2.2，2026-09-10。本文是执行范围、预算与验收的唯一现行入口；当前进度见 [current-status](context/current-status.md)。
> 历史计划见 [v2 archive](Roadmap-v2-archive.md) 与 [v1 archive](Roadmap-v1-archive.md)，均不作为当前执行标准。
> M0–M3 技术范围沿用既有计划；本次调整后续预算、依赖与验收归属。工时和排程是计划假设，不是实测或完工承诺。

## 1. 剩余工作预算与排程规则

| 阶段 | 本轮定位 | 工时预算 |
|---|---|---:|
| M3 Complete | 沿用已有范围；根据 gap analysis 估算剩余工作 | 待现场复核，不把原 50 h 当剩余工时 |
| M4 可观测性、SLO 与诊断闭环 | 核心主线 | 16–20 h |
| M5 服务生命周期与最小弹性闭环 | 核心主线 | 22–28 h |
| M6 深度观测、灰度与韧性扩展 | 后续深化 | 开工前重估 |
| M7 容量成本与最终收尾 | 原 M6 顺延 | 原预算 12 h；开工前复核 |

M4/M5 从原 80 h 收缩为 38–48 h；这是移出任务与缩小矩阵的预算，不是假设效率提高。
预算包含本阶段的机制梳理、实施、测量、复盘和短 review；意外返工另计。
每个新知识点仍按约 6:4 安排理论理解/复盘与实操；同一主题不重复开完整教程。

按实际可投入工时和上一阶段剩余工作滚动排程；同时只推进一个技术 milestone。
缓冲未用不自动填入 stretch，超支时重新评估后续排程。

核心任务未过验收则保留未完成状态，不通过改名伪装完成；已有测量不能替代核心功能正确。

---

## 2. M1p — Repackage & 呈现修复（原预算 12 h）

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

## 3. M2 — Serving 优化实验室（原预算 30 h）

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
- [ ] 所有结论进入 showcase 的 comparison / run set analysis 视图（复用已有 contract，不新建 UI）

---

## 4. M2p — 多 adapter 准备（原预算 12 h）

### 目标

为 M3 的 multi-adapter serving 和 M6.3 的 adapter-aware 路由准备**真实的多 adapter workload**。这是一个 enabler，不是训练 Milestone。

### 两条路径，按可行性择一

| 路径 | 说明 | 工时 |
|---|---|---:|
| **A（推荐）单节点轻量 LoRA 微调** | Qwen2.5-7B + LoRA，4–6 个行为可区分的 persona 或 task adapter，合成语料（**必须写清是合成的**）。只求 adapter 可加载、行为可区分，**不做训练性能优化**。顺带记录吞吐 tokens/s 与统一内存下的峰值占用——为 §10 的 optional 分布式训练留一个单节点基线 | 12 h |
| **B（降级）现成 adapter** | 若 aarch64 上 peft/训练栈不可用，直接用社区已有 LoRA，或用不同 system prompt 模拟多个 persona。**记录降级原因**，作为兼容性证据 | 4 h |

> **纪律**：这一步的验收标准是"M3 能加载 4–6 个不同 adapter 并服务"，**不是**"训练效率如何"。任何超出这个目标的训练调优都算超范围，立即停手。

### Exit Criteria

- [ ] 4–6 个可加载、行为可区分的 adapter
- [ ] 生成路径可复现（脚本或明确的下载/构造说明）
- [ ] 若走路径 B，降级原因已记录

---

## 5. M3 — Kubernetes 基础与 GPU workload（原预算 50 h）

### 临时执行拆分

以下保留原阶段衔接；M3 Complete 内部顺序以 [Complete plan](milestone-plan/m3-plan-complete.md#执行顺序) 为准，剩余工时按 §1 复核。

Minimal 的 2–3 天 timebox 从本节既有预算中切出，不增加新的 Milestone 或额外预算。

```text
M2 overall pre-close → M3 Minimal → M2 close → M3 Complete
```

[M3 Minimal](milestone-plan/m3-plan-minimal.md) 只做 3.1–3.3 的窄纵向闭环和一次功能实测，不满足完整 M3 Exit Criteria。[M3 Complete](milestone-plan/m3-plan-complete.md) 复用该闭环，再补齐 3.1–3.6 与本节全部验收项；M2p adapter 仍须在 3.6 前可用。

### 目标

**这是全计划的第一重心。** 目标是验证 LLM workload 的可复现 Kubernetes 生命周期，而不是只完成一次 Deployment。

验收重点是 LLM workload 特有的运行约束：慢加载模型的探针设计、流式连接的优雅终止、GPU 扩展资源，以及模型缓存的存储策略。

拓扑：Spark A 承担 single control plane，并作为显式调度的 GPU workload node；Spark B
是 worker-only。该两节点拓扑不是 HA；benchmark 中记录 Spark A 的 control-plane
activity/noise，不把它与普通 Worker 等同。

### 任务

| # | 任务 | 内容 | 工时 |
|---|---|---|---:|
| 3.1 | **集群可复现搭建** | kubeadm，两节点，脚本 + 文档可重建。含 CNI 选择理由、节点标签与 taint 策略。<br>**"可从零重建"是本阶段的复现性要求。** | 10 h |
| 3.2 | **GPU 接入** | device plugin / RuntimeClass / NVIDIA container runtime，GPU 作为 extended resource 被正确 request。<br>**ARM64 + GB10 上这一步的成熟度明显低于 x86**——过程中的坑与解法本身是最有价值的产出，全部记录。M0 已把此项列为未验证边界。 | 12 h |
| 3.3 | **Workload 建模与探针** | Deployment vs StatefulSet 的选择理由；requests/limits 与 QoS class；**`startupProbe` 针对 900 s 级模型加载的设计**（这是 LLM serving 的经典陷阱——用 liveness 兜加载会导致无限重启）；readiness 与 liveness 的职责分离 | 10 h |
| 3.4 | **优雅终止** | `terminationGracePeriodSeconds` + `preStop` hook，保证 Pod 删除时**进行中的流式请求不被截断**。用 M1 的 benchmark client 量化：删 Pod 时的请求失败数与截断数，以验证 K8s 生命周期与 LLM 流式响应的交互。 | 8 h |
| 3.5 | **模型缓存存储** | PVC 承载模型权重，冷启动 vs 热启动对比测量；init container 或 sidecar 的预热方案取舍 | 6 h |
| 3.6 | **打包与多 adapter 服务** | Kustomize overlay 或 Helm chart；加载 M2p 的 4–6 个 adapter 做 multi-LoRA 共池，单次请求可指定 adapter | 4 h |

### Exit Criteria

- [ ] 集群可由脚本 + 文档从零重建；Spark A control plane 与 Spark B Worker 都 Ready，且两节点均可运行显式申请的 GPU workload
- [ ] GPU 通过 extended resource 被调度，容器内可见；ARM64 上的坑与解法已记录
- [ ] Probe 能正确区分「加载中 / 可服务 / 异常」；模型加载期不触发重启
- [ ] Pod 删除时进行中的流式请求不被截断，有量化数据
- [ ] 模型缓存冷/热启动差异已测量
- [ ] 多 adapter 共池可服务，单请求可指定 adapter
- [ ] K8s 单副本结果与 M1 裸机基线的差异已记录（隔离 K8s 引入的开销）

---

## 6. M4 — 可观测性、SLO 与诊断闭环（16–20 h）

### 目标

固定已验证的 M3 单副本部署与一组代表性 workload，先覆盖实际 client → Kubernetes Service → vLLM 路径，形成压力出现 → 指标变化 → 告警 → 定位 → 恢复的闭环。M4 不以尚未建设的 gateway 为前置，不声明已观测 gateway/routing 延迟。
本阶段验证实验环境中的观测与诊断能力，不声称具备集中日志平台、单请求完整 tracing 或生产 SLA。

| 新任务 | 范围与来源 | 预算 |
|---|---|---:|
| 4.1 Metrics 栈与早期兼容性检查 | kube-prometheus-stack、vLLM ServiceMonitor、K8s/节点与实际可用 GPU/统一内存观测；附带一次限时 pinned-runtime Tracing smoke，不为齐全而新建 exporter | 6–8 h |
| 4.2 诊断 Dashboard | 原 4.2 四张独立页面收为一张分区页面：请求体验、queue/runtime、KV/资源、SLO/Goodput | 3–4 h |
| 4.3 轻量日志关联 | 原 4.3 先只用带时间戳的 server log、Pod events 与指标时间窗关联；不装 Loki/ELK | 1 h |
| 4.4 SLO 与告警 | 原 4.5：复用现有指标语义，在当前部署校准一个 workload 的目标与窗口，实测一条告警触发和恢复 | 4–5 h |
| 4.5 收尾 | 一份现有格式的 review，保留必要配置、时间线和证据链接；不建新展示框架 | 2 h |

### 早期 Tracing smoke 与 M5 交接

在 M4.1 早期对 pinned image/runtime 做一次限时检查：记录现有 trace 导出能力、可见字段/span 与缺失项；运行最小请求验证可行时保留输出，不凭 flag 存在就判链路可用。不能预设 queue/prefill/decode 三段都可见。
此项只为提前识别 M6.2 的兼容风险；不升级 runtime，不建设长期 collector/backend，不补自定义插桩。若需新增依赖或越过已有操作授权，停止并记录阻塞。未跑出的部分明确为未验证，不把检查完成写成 tracing 功能完成。
检查工时计入 4.1，原预算仍只是估计；时间箱在 M4 开工时明确，超时不挤占核心 metrics/SLO 实测，不因 smoke 失败自动扩大 M4。
M4 的 SLO 目标和 baseline 只适用于其声明路径、模型、负载和缓存条件。M5.1 建成 gateway 后补入口日志/已有指标与副本观测关联，重新确认请求计数与适用目标；完整端到端 trace 仍留 M6.2。

### Exit Criteria

- [ ] 当前部署的 serving、K8s/节点和实际可用资源观测可以按时间窗关联；GPU 遥测缺失明确列出，不冒充已采集。
- [ ] pinned-runtime Tracing 可行性检查的执行范围、输出和缺口有记录；未完成导出时不写 tracing pass；该检查不要求 M6.2 提前完成。
- [ ] 一张诊断页面能支持本次异常的定位；哪些阶段可以测量、哪些仍不可区分写清楚。
- [ ] server log 与 events 留存可支持本次定位；没有 request id 时只声明时间窗关联。
- [ ] SLO 写明 workload、窗口、纳入规则和失败口径；M1/M2 仅作初始参考，不直接承诺跨部署相同阈值。
- [ ] 至少一次受控压力实验真实触发并恢复告警；有请求结果、指标、日志与 timeline，不以规则文件代替实测。

### 不做与后移

集中日志移 M6.1，原 4.4 的完整 Tracing 建设与验收移 M6.2；仅早期可行性 smoke 留 M4.1。四张独立 Dashboard 的版式数量不再作为验收。
不把总体指标当作单请求 trace。原“完整三段分解”留在 M6.2；M4 只要求在实际遥测支持范围内诊断。
遥测适配卡住时记录缺口并限制结论，不自动增加 GPU 监控子项目；关键定位证据缺失则不判对应验收通过。

## 7. M5 — 服务生命周期与最小弹性闭环（22–28 h）

### 目标

复用 M3 的探针、终止与缓存配置和 M4 的观测入口，验证双副本入口、发布回滚、Pod 级恢复与 serving 指标驱动的扩缩容。
只选一个网关实现、一条基础路由、一种伸缩方案、一组代表性 workload；不做模型/adapter/策略交叉矩阵。

| 新任务 | 范围与来源 | 预算 |
|---|---|---:|
| 5.1 统一入口与观测接续 | 两副本与一种基础路由；确认实际请求能到达两副本，并将入口日志/已有指标接入 M4 观测，校准新增路径的 baseline；不比较智能路由 | 4–5 h |
| 5.2 Endpoint 与 Pod 级恢复 | 合并原 5.2 基础摘除测量与原 5.5 的 Pod 演练；固定一种停止方式，记录端点状态、实际路由和恢复 | 3–4 h |
| 5.3 Rolling 与 rollback | 原 5.3 保留一次真实版本变更和回退；持续请求下记录成功、失败、流式截断、延迟与副本变化 | 5–6 h |
| 5.4 Serving 指标伸缩 | 原 5.4 仅选 HPA+Prometheus Adapter 或 KEDA 之一；一个经验证可用的 waiting-request 信号，副本 1→2→1 | 7–9 h |
| 5.5 收尾 | 整合既有实验的 timeline、短 runbook、限制与证据入口；不另造故障平台 | 3–4 h |

### 执行顺序与测量边界

M4 现有 Service 路径的观测闭环 → M5.1 双副本/网关与观测接续 → M5.2 endpoint/Pod 恢复 → M5.3 rolling/rollback → M5.4 自动伸缩 → review。
M5.1 的观测接续属于本任务，不另开 M4 Full；只关联实际已有日志/指标，缺失的 gateway 内部分段留为缺口，不增建 tracing 系统。
开始生命周期实验前记录新入口与固定副本数下的 baseline、请求成功口径及适用 SLO；M4 的单副本数字不能直接当成网关/双副本基线。各次实验的目标预先声明，不为让结果通过而事后改阈值。

### Exit Criteria

- [ ] 两副本通过统一入口实际接到请求，路由行为有证据；不把连接级分配冒充请求级 round-robin。
- [ ] 网关后路径的 baseline、观测接续、实际可分辨阶段与 SLO 适用条件已记录，再开展发布/恢复/伸缩实验。
- [ ] 一次选定的 Pod/进程停止实验测得端点变化、路由停止送入新请求和恢复时间；说明停止方式，优雅删除不冒充 crash。
- [ ] 完成一次 rolling update 与回滚；回滚后恢复已验证功能基线，实际请求成功率、流式截断、样本量及适用负载有记录。
- [ ] 一个 serving 指标真实驱动 1→2→1；保留 desired/current/ready replicas、调度与加载时延、请求表现和一次恢复窗口。
- [ ] 结果说明冷启动和资源上限；没有观察到振荡只限于本轮条件，不外推为稳定性证明。
- [ ] 汇总 review 能指向上述证据；只有 YAML、手动扩容或 Pod 数量变化均不足以证明自动弹性闭环。

### 两节点资源与实验边界

先复核可调度 GPU 单位和每 Pod 申请量。若仅两个 GPU 单位且每副本独占一个，不假定有第三个单位支持 surge。
在这个前提下，rolling 先采用不依赖第三 GPU 的替换策略，并明确更新期间可能只有一个可用副本；不保证满容量或任意负载零错误。[Kubernetes Deployment 文档](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-update-deployment)。
PDB 不直接约束 Deployment 的 rolling update；本阶段不以配置 PDB 证明发布无中断。[Kubernetes Disruptions 文档](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/#pod-disruption-budgets)。
伸缩实验从单副本开始并保留第二个 GPU 的真实余量；预先校验待扩节点可读模型/缓存/adapter 资产，不在 M5 新建共享存储系统。
固定缓存条件并记录加载成本，不将 warm-cache 的结果写成 cold-download。独立 canary 和节点 drain 放在 M6。
各实验分开执行和恢复配置；压力 workload 可复用，但不将同一次 run 强行充当不同部署条件下的因果对照。
所有注入、停止与发布操作仍需在影响范围可审阅后授权；本计划不授权实际执行。

## 8. M6 — 深度观测、灰度与韧性扩展（后续）

仅接收本次从 M4/M5 移出的内容，不夹带 P/D、RL Infra、新 runtime、自定义 controller 或 scheduler。
不作为 M4/M5 Closeout 的前置；开工前按实际问题重估工时。

| 任务 | 原项 | 范围与后续验收 |
|---|---|---|
| 6.1 集中日志 | 4.3 | Loki 或 ELK 二选一，关联 server log、events 与 metrics |
| 6.2 单请求 Tracing | 4.4 | 从 M4.1 smoke 的已知能力/缺口继续；OpenTelemetry 与实际网关路径关联；一条真实请求的 queue/prefill/decode 分段，插桩缺失时明确未验证，不以聚合指标替代 |
| 6.3 智能路由对照 | 5.1 | 基础路由 vs adapter/prefix-aware；收益仅是待验证假设，固定 workload 与条件，以 Goodput 检验；允许无收益或负收益，记录缓存与负载取舍 |
| 6.4 Canary | 5.3 | 继承 M5 的 GPU 容量、版本共存和负载前提；真实小比例流量进入新 adapter/镜像，测实际比例与请求结果，再放量或回滚，不假定有额外 GPU |
| 6.5 韧性扩展 | 5.2 + 5.4 + 5.5 剩余部分 | readiness flap 与抑制；worker drain；KV 压力下 load shedding/timeout；伸缩振荡边界的追加实验 |

M6 的每项按对应证据独立验收；未完成不写已掌握/已验证。worker drain 不替代节点突然失联或控制平面 HA 证明。
实验矩阵上限在开工时确定，不为了补回旧 80 h 而重复测量；纯版式、重复仪表盘等已删除工作不强行搬入 M6。

## 9. M7 — 容量成本与最终收尾（原 M6，12 h）

| 新任务 | 原任务 | 保留范围 | 原预算 |
|---|---|---|---:|
| 7.1 容量与成本报告 | 6.1 | 每卡会话数、每百万 token 的 GPU-秒、声明需求模型下的活跃会话推算；前缀命中率与量化影响 | 5 h |
| 7.2 最终 showcase | 6.2 | 全链路呈现与一页架构图 | 5 h |
| 7.3 证据导航汇总 | 6.3 | 项目级问题到现有证据的导航 | 2 h |

成本推算明确测量值、假设和适用边界，不凭实验平台推算商业生产能力。
M7 只承担最终汇总。每个 milestone 的已有结果、短 review 和最小证据入口当期更新，不等 M6/M7。
证据入口只链接 owner，不复制实验结果；不新增 evidence platform 或第二套状态文件。

### Exit Criteria

- [ ] 容量成本报告给出每卡会话数、每百万 token 成本、活跃会话量推算。
- [ ] Showcase 覆盖全链路。
- [ ] 每项 §11 验收问题都能在 30 秒内定位到证据。

---

## 10. Stretch / Optional（默认关闭，另行定范围）

仅在核心工作与工时预算允许、用户明确要求并说明用途后启动；不因缓冲未用或新增 M6 自动开启。原范围保留，工时开工前重估。

| # | 项目 | 工时 | 说明 |
|---|---|---:|---|
| **S1** | **小型 K8s Controller** | 25 h | CRD + reconcile loop + status conditions，做一件小事（例如按 KV cache 压力调整副本的 annotation，或 adapter 版本的声明式管理）。用于验证声明式控制循环；风险高，核心验收与工时预算允许后才考虑 |
| **S2** | **分布式训练（optional）** | 30 h | 2 节点 DDP / FSDP，跑 0.5B / 1.5B 全参数，产出扩展效率表 + NCCL 通信开销分解（复用 M0 的 RoCE 基线与 NIC counter collector）。只验证小规模多节点执行与通信成本；明确不做 Megatron / DeepSpeed / TP / PP / 大规模 MoE 训练，两节点 128 GB 的结果不外推到大规模训练 |
| **S3** | **跨节点张量并行推理** | 10 h | `TP=2` over 2 nodes 对比 replica parallel，产出 ADR：什么时候该 TP、什么时候该加副本。前置证据见 [M0 review](reviews/m0-review.md)，增量成本开工前复核 |
| **S4** | **MoE 推理** | 8 h | Qwen3-30B-A3B 或 Qwen1.5-MoE-A2.7B 单节点跑通，记录 expert 激活与内存占用 |
| **S5** | **结构化输出可靠性** | 6 h | guided decoding 的 TTFT/TPOT 开销 + schema violation rate；面向需要状态机或工具调用的下游应用 |
| **S6** | **SGLang 单点对比** | 10 h | 在同一 workload contract 下选择一个 workload shape，与 vLLM 做受控对比 |
| **S7** | **上游 vLLM 贡献** | 不定 | 遇到可复现的 upstream 问题时贡献文档、测试或小修复；**不设时间预算，机会型推进** |

> **S1 与 S2 互斥选一。** 若优先研究 Kubernetes 控制循环，选 S1；若优先研究多节点训练的执行与通信边界，选 S2。

---

## 11. 项目级验收

本节用于把系统问题映射到证据。核心与后续深化分别验收，不以“8 周后全清”作统一闸门；当前完成情况只见 [current-status](context/current-status.md)。

### 核心验收（M0–M5）

下列问题须由对应实验回答，未满足的验收保留未完成状态。

**Kubernetes 与服务生命周期**

- [ ] 集群怎么从零重建？CNI 和节点标签为什么这么选？（M3.1）
- [ ] GPU 怎么被调度？ARM64 上遇到了什么，怎么解的？（M3.2）
- [ ] 模型要加载 15 分钟，探针怎么配才不会被无限重启？（M3.3）
- [ ] 删 Pod 的时候，正在流式返回的请求会不会被截断？（M3.4）
- [ ] 模型缓存冷/热启动有何差异、缓存位于哪个节点？（M3.5）
- [ ] 多个 adapter 能否共池服务，单请求能否指定 adapter？（M3.6）
- [ ] 网关是否把请求送到两副本，新增路径怎样接续观测与校准 baseline？（M5.1）
- [ ] 选定的 Pod 停止方式下，端点何时变化、新请求何时停止送入、多久恢复？（M5.2）
- [ ] 在声明负载下发布/回滚的失败率、截断、容量变化及限制是什么？（M5.3）
- [ ] 为什么用 serving waiting-request 而不是 CPU 伸缩，是否真实完成 1→2→1？（M5.4）

**推理优化与诊断**

- [ ] 量化带来多少吞吐收益，付出多少精度代价？（M2.2）
- [ ] 投机解码在什么 workload 下有效、什么 workload 下反而更慢？（M2.3）
- [ ] 前缀缓存命中率对 prefix-heavy 交互服务成本的影响有多大？（M2.1）
- [ ] 实际 client → Service → vLLM 路径中，哪些延迟/资源阶段能分辨，哪些有遥测缺口？（M4.1–4.3）
- [ ] 声明 workload 的 SLO 如何校准，是否实测告警触发、定位与恢复？（M4.4）
- [ ] 是否记录过一个已识别并修正的实验偏差？（[M1 review](reviews/m1-review.md)）

### 后续深化（M6–M7）

- [ ] 集中日志如何关联 server、events 与 metrics？（M6.1）
- [ ] 单请求从网关进入后的 queue/prefill/decode 能否直接分段，哪些插桩仍缺失？（M6.2）
- [ ] adapter/prefix-aware 路由相对基础路由的 Goodput 结果如何，何时无收益或负收益？（M6.3）
- [ ] 现有 GPU 容量下 canary 的实际流量比例、请求结果及放量/回滚行为是什么？（M6.4）
- [ ] worker drain 后容量怎样下降、服务怎样降级？readiness flap、KV 压力与追加伸缩实验暴露何种边界？（M6.5）
- [ ] 在声明的需求模型下，需要多少 GPU、可支持多少活跃会话？（M7.1）
- [ ] 全链路展示与证据导航是否能指回已有 owner？（M7.2–7.3）

---

## 附录 A — 相对 v1 的变更总结（历史 v2）

以下保留 v1 → v2 当时的编号与预算；不作为现行排程，现行范围以正文为准。

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
| **（v1 无）** | **新增 M1p 呈现修复，12 h** | showcase 在公开 repo 上打不开 |
| **（v1 无）** | **新增 M2 量化 / 投机解码 / 前缀缓存，30 h** | v1 列为 optional；现有 benchmark pipeline 可低边际成本复用 |
| **（v1 无）** | **新增 M2p 多 adapter 准备，12 h** | multi-LoRA 服务的前置；顺带给 optional 分布式训练留单节点基线 |
| **（v1 无）** | **分布式训练列为 S2 optional，30 h** | 硬件规模只支持有界的小规模实验，优先级低于推理主线 |

---

## 附录 B — 历史 Milestone 证据入口

| Milestone | 结论入口 |
|---|---|
| **M0** Platform Qualification | [`reviews/m0-review.md`](reviews/m0-review.md) — host CUDA、GPU container、200 Gb RoCE、NCCL 基线、兼容性边界 |
| **M1** Single-Node vLLM Baseline | [`reviews/m1-review.md`](reviews/m1-review.md) + [`showcase/m1/`](../showcase/m1/) — 四场景 operating references、最小 OVAT、bounded boundary、7B 兼容性 |

M0/M1 的范围与 Exit Criteria 原文见 [`Roadmap-v1-archive.md`](Roadmap-v1-archive.md) 的对应章节。
