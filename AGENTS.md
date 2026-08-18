# AGENTS.md

个人研究型项目：两台 DGX Spark 上的 LLM inference platform。目标是**可复现的流程与证据**，不是榨干性能，也不是建平台化基础设施。

> **本文件自身预算 ≤ 220 行。** 超出说明规则在累积而非收敛——删掉最少被触发的规则，不要追加。

---

## 0. 本项目最主要的失败模式

不是写错代码，是**范围失控**。历史记录：

| 事件 | 结果 |
|---|---|
| M0 建 evidence platform | `scripts/m0/m0-evidence.sh` 1137 行，M1 被迫写非目标清单叫停 |
| 为未建成的 M3 写规范 | `docs/SLO/inference-service-slo.md` 1336 行，Prometheus 尚未部署 |
| showcase 契约膨胀 | 2400 行 JS 承载 4 workload × 3 并发点 |
| 状态写进 4 个文件 | 全部漂移到过期值 |
| 描述性元数据被变成守卫 | hash / revision / `cache_salt` 反复被写成授权闸门 |

**每一次增量在局部都合理**——provenance 重要所以加 manifest，正确性重要所以加校验。没有单步是错的，聚合起来才是；能力越强的模型越容易这样，因为它能为每个增量找到理由。所以本文件的防线是**预算与结构**，不是"保持简洁"这类劝诫——该劝诫已在旧版存在，随后产生了 687 行的 `run-benchmark.sh`。

---

## 1. 开工前：声明预算

任何预计新增 **>50 行代码** 或 **>100 行文档** 的任务，动手前先输出四行：

```text
目标：     <一句话，可验收>
产出：     <文件路径清单>
预算：     <每个文件的预估行数>
本次不做： <三件具体的、有诱惑力的相邻工作>
```

"本次不做"必须是**真实想做的事**，不是稻草人。写不出三件说明范围还没想清楚。

**实际产出超预算 50% 时立即停手**，报告超出部分与原因，等指示。不要先写完再解释。

---

## 2. 行数预算

| 产物 | 预算 | 超出时 |
|---|---:|---|
| Shell 脚本 | 250 行 | 拆分或减少功能 |
| Python 模块 | 300 行 | 拆分 |
| 设计文档 | 200 行 | 砍内容，不拆文件 |
| Milestone 计划 | 150 行 | 同上 |
| Review / 结论 | 120 行 | 同上 |
| ADR | 80 行 | 同上 |

现存超标文件（`run-benchmark.sh` 687、`benchmark_utils.py` 705、`m0-evidence.sh` 1137、SLO 1336）是**待偿债务，不是先例**。不要援引它们为新增辩护。

Milestone 计划指单个 milestone 的具体落地计划，全局 roadmap 在该显式规则外，也是唯一例外的"超预算"——它是**全局视图**，不是单个任务的产出。

---

## 3. 单一来源表

每类事实**只有一个 owner 文件**。写入前查表；把同一事实写进第二个文件是缺陷，不是冗余保险。

| 事实 | Owner |
|---|---|
| 项目定位、成果速览 | `README.md` |
| 执行计划、里程碑、工时预算 | `docs/Roadmap.md` |
| 当前进度 | `docs/context/current-status.md` |
| 实验目录约定、脱敏流程 | `docs/experiments/README.md` |
| 证据留存、仓库卫生预算 | `docs/experiments/evidence-retention.md` |
| 实验结论、限制、unknowns | `docs/reviews/<milestone>.md` |
| 环境与硬件事实 | `docs/environment/*.md` |
| 技术决策与取舍 | `docs/adr/ADR-*.md` |
| 指标语义与 SLO | `docs/SLO/inference-service-slo.md` |
| Agent 行为规则 | `AGENTS.md` + 子目录 `AGENTS.md` |
| 历史全量计划（已归档） | `docs/Roadmap-v1-archive.md` |

需要在别处提及该事实时**只放链接**，不复制数值、不复制表格、不复制状态。

发现两处描述同一事实时：修 owner，把另一处改成链接。**不要"两边都更新"**——那是漂移的成因。

---

## 4. 常设非目标

以下永不建设，除非用户明确要求并说明用途。这不是"当前不做"，是**默认关闭**：

- Evidence platform、manifest lifecycle、SEAL、artifact signing、publication attestation
- 全局 schema 治理、schema 版本协商、全局 enum
- 针对单一调用点的 framework / adapter / plugin / registry 层
- 为尚未存在的组件写规范文档
- 把 revision / hash / fingerprint / `cache_salt` 变成授权、鉴权或 eligibility 闸门（它们是描述性元数据）
- 对可恢复的研究性错误加 refusal-style 拒绝执行门
- 在本 testbed 上追求性能最优或参数全局最优
- 任何事实的第二份拷贝

`scripts/experiments/sanitize-public.sh` 是 helper，**不是发布许可**。它返回 0 不等于批准公开。

---

## 5. 抽象的准入条件

**已存在两个真实调用点**才可以抽象。

- "将来会复用" ≠ 复用。
- 一个调用点 → 内联。
- 两个 → 可以提取。
- 三个以上且逻辑分叉 → 应该提取。

同样适用于：配置项（当前只有一个取值就写死）、schema（只有一个生产者就不要 schema）、抽象基类、通用工具函数。

---

## 6. 规范跟随系统

**不为不存在的组件写规范。** 未实现组件的设计笔记 ≤ 1 页，且必须标 `draft`，数值目标一律写 `TBD`。

规范的正确时机是**系统已运行且有实测数据可校准**。反例见 `docs/SLO/inference-service-slo.md`：1336 行、5 条 SLO、完整告警规则，写在 Prometheus 部署之前，其中的目标值无任何数据支撑。

---

## 7. 错误处理边界

只在两处做校验：**外部输入穿过信任边界**（CLI 参数、配置文件、网络响应、解析外部格式），以及**实际观测到过的失败模式**（有 log、有复现步骤）。

不做：校验自己函数间的内部不变量、为"不可能"的分支写处理、多层 fallback 链、静默吞 warning 后继续。

**Fail fast, fail loud.** 出错带上下文退出，不降级成部分结果继续跑——部分结果比失败更难诊断。

不确定属不属于上述两类时：**不加**，在产出说明里列为"未防护的假设"。展开见 [`serving/AGENTS.md`](serving/AGENTS.md)。

---

## 8. 事实分级

所有结论必须归入四类之一；只有把核心结论写得比证据更强的混写才阻塞（如把性能归因写成 Observed Fact、把未执行写成 Unknown）：

| 级别 | 含义 |
|---|---|
| **Observed Fact** | 原始数据直接支持，可指向具体文件 |
| **Interpretation** | 对事实的解释，可能有其他解释 |
| **Hypothesis** | 待验证，必须写清验证方式 |
| **Unknown** | 已在声明范围内测试但无直接证据。**这是合格结论** |

`Unknown` ≠ 缺文件、未运行、telemetry 不支持、comparison 不匹配。后者是执行缺口，如实说执行缺口。

配套约束：

- 不虚构 benchmark 数据；不改写 `raw/`；`derived/` 必须可从 `raw/` 重算
- 失败、timeout、OOM、restart、non-zero exit 全部保留，不删不改
- 不因项目目标就假定某项工作已完成——**读仓库真实状态**
- 不把两台 DGX Spark 描述为等价于生产 DGX 集群
- 无直接证据不声称 RDMA / GPUDirect RDMA 生效
- GPU utilization 不作为 saturation 或 capacity 判据
- 版本敏感的命令与 API 要标注，先在 pinned runtime 上 smoke

---

## 9. 停手并询问

以下情况**停止执行、报告、等指示**，不要自行决定：

- 实际产出超预算 50%
- 需要新建目录，或新增第 4 个以上文件
- 需要引入新依赖、新服务、新框架
- 想加一个当前只有单一调用点的抽象
- 想为未建成的组件写规范
- 发现某事实存在两份拷贝，且不确定哪份是 owner
- 任务描述与 `docs/Roadmap.md` 的当前阶段范围不符
- 需要破坏性操作（删文件、改 `raw/`、rebase、force push、动硬件状态）
- 任何 commit、push、创建 PR、发布 Pages 的动作

**默认不 commit。** 产出留在工作区由用户审阅。

---

## 10. 收工前自检

逐条回答，有"是"就先修再交：

- [ ] 有没有把某个事实写进了第 2 个文件？
- [ ] 有没有加了只有 1 个调用点的抽象？
- [ ] 有没有为不存在的组件写规范？
- [ ] 有没有超预算 50% 而没报告？
- [ ] 有没有加了不属于 §7 两类的校验？
- [ ] 有没有把核心结论写得比证据更强？
- [ ] 有没有用"未来会用到"为当前增量辩护？
- [ ] `current-status.md` 是否需要同步更新？（这是唯一允许也必须更新的状态文件）

---

## 11. 阅读顺序

进入仓库先读，**不要读完全部文档**：

1. `AGENTS.md`（本文件）+ 工作目录下的 `AGENTS.md`
2. `docs/context/current-status.md` — 现在在哪
3. `docs/Roadmap.md` — 当前阶段的范围与 exit criteria
4. 任务直接相关的 owner 文件（查 §3）

以下文件已停用或属历史归档。**不读、不更新、不引用其流程为当前标准、不作为新文档模板**，除非任务明确涉及 M0：

```text
docs/Roadmap-v1-archive.md
```

M0 的 evidence / publication 工作流是**一次性历史产物**，不是后续 milestone 的范式。

---

## 12. 执行与表述

- 只运行非破坏性命令，除非明确授权
- 缺失证据与实现缺陷**分开报告**；无证据支撑的假设显式标出，不混进结论
- 审阅只因三类问题 `REJECT`：有具体证据且会改变结论、范围或执行决定的事实错误/内部矛盾；关键证据或限制缺失导致结论越界；产物无法执行、渲染或满足明确 exit criterion
- 同一 caveat 每个产物只报告一次；owner / `limitations` 已明示且正文未越界时，不得要求在 takeaway / claims / scope 重复
- 其余措辞、格式、命名与可选增强均为 non-blocking，每个产物最多列 3 项；不得据此拒绝 `PASS` / `final`、要求整体重写或新增防护
- 长时运行任务：状态轮询 ≥180 s（推荐 300 s）；外层 wrapper 超时要比最长内层等待多 30 s 以上。连续两次轮询无新输出说明**慢，不是卡**——退到 300 s 继续等，不提前返回、不重启任务
- 设计与展示型文档中文为主，保留必要英文术语；代码、文件名、API、metric 名、K8s 资源名用英文
- 避免"效果很好""性能明显提升"，用可量化表述
