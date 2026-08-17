# 证据留存与仓库卫生标准

> 实施边界与顺序见 §8。
> 目录约定与脱敏流程见 [Experiment Repository Convention](README.md)，本文只管**什么进 git、以什么形态进**。
> 预算 ≤ 200 行。

---

## 1. 问题定义

M1 结束时的实测（commit `d49fdfb`）：

| 指标 | 现状 | 判定 |
|---|---|---|
| clone 传输量 | **5.71 MiB** | 不是问题——git 对 JSONL 有 ~13:1 压缩 |
| checkout 后磁盘 | 84 MB | 轻微 |
| tracked 文件数 | **1,658**，其中 1,463（88%）是 raw results；项目代码与文档仅 148 | **核心问题** |
| 单个 run 文件数 | **122–141**，每个 case 扇出 9 个小文件 | **核心问题** |
| 最大单文件 | `20260812-m1.3-C16-128/raw/requests.jsonl` — 15.6 MB / 15,000 条 | **核心问题** |
| 单条 request 记录 | 1,088 B，其中字段名占 55%，可移除字段占 38% | 可优化 |

**这是信噪比问题，不是体积问题。** 88% 的文件属于一类没有人类读者的产物，它淹没了仓库浏览、语言统计、全局搜索和 diff 审阅。压缩解决不了这个问题——减少文件数和明确读者才能。

---

## 2. 原则

### 2.1 raw 数据的职责是可被验证，不是被阅读

三类读者，需求完全不同：

| 读者 | 时间 | 真正需要 |
|---|---|---|
| 人类 reviewer | 3 分钟 | README 的数字 + showcase 的图表 |
| 怀疑论技术 reviewer | 20 分钟 | 验证**某一个**具体声明，且确认完整数据真实存在 |
| 复现者 / 未来的自己 | — | config 与方法，**不需要旧字节** |

没有任何读者需要 15,000 条 JSONL 在 git 里。怀疑论 reviewer 需要的是"能查"，不是"已在本地"。

因此每个 artifact 类型必须能回答：**它支撑哪个声明？谁会读它？** 两问答不上，不进 git。

### 2.2 完整性在 git 之外，可验证性在 git 之内

git 内保留足以抽查、足以交叉验证、足以证明完整数据存在且未被挑选的部分；完整 raw 留在 git 外。

### 2.3 失败证据不采样

timeout、OOM、non-zero exit、restart、部分完成的请求——**全部逐条进 git**。

这是本项目的核心承诺，卫生标准不得侵蚀它。采样只作用于成功记录。反过来说：如果失败记录多到撑爆预算，那是实验结果，应当如实呈现，不是压缩对象。

---

## 3. 三层留存

| Tier | 位置 | 内容 | 是否采样 |
|---|---|---|---|
| **A** | git（`benchmarks/raw-results/`） | `run.yaml`、`derived/summary.json`、全部失败记录、成功记录的采样、per-run 聚合的 lifecycle 与 telemetry 摘要 | 成功记录采样 |
| **B** | GitHub Release attachment（每 milestone 一个 tarball） | 完整 raw，含全部 request 记录与时间序列采样 | 不采样 |
| **C** | `artifacts/private/`（gitignored） | 探索性 run、未脱敏捕获、被 Tier B 取代的中间产物 | 不发布 |

Tier B 的引用方式：`run.yaml` 记录 release tag 与文件名。**不建 index、不建下载器、不建校验工具链**——一个 tag 加一个文件名就够（见 §7 红线）。

---

## 4. 采样契约

对每个 case 的成功记录：

```text
保留 = 全部失败记录
     + 头 20 条
     + 尾 20 条
     + 其余成功记录按固定步长分层抽取，每 case 上限 60 条
排序 = 按 request_index 升序，确定性、可复算
```

不使用随机抽样。步长与上限写进 `derived/summary.json` 的 `sampling` 字段，任何人可复算出同一组记录。

### 必须写明的限制

**采样后的 git 副本无法重算分位数。** 60 条采样算出的 p95 不是 15,000 条的 p95。

因此：

- 分位数、吞吐、失败率的**权威来源是 `derived/summary.json`**，它由完整 raw 生成于 Tier B 之前；
- git 内采样的用途是**逐条抽查记录合理性**（时间戳单调、token 计数来源、状态字段自洽）与发布字段一致性检查；
- 需要独立重算分位数的 reviewer 走 Tier B。

`summary.json` 必须显式声明这一点，字段形如 `"percentiles_recomputable_from_public_raw": false`。**不允许让读者以为采样副本能重算 p95。**

---

## 5. 文件数收敛

当前每个 case 扇出 9 个小文件（两个 `*.prom`、两个 `idle-*.jsonl`、两个 client 日志、三个 `*-exit-code.txt`）。62 个 case × 9 ≈ 560 个文件。**标准：per-case 不产生 git 内文件，一律聚合到 per-run。**

| 现状（per case） | 目标（per run） |
|---|---|
| `metrics-before.prom` / `metrics-after.prom` | `derived/summary.json` 既有 `cases[].runtime_counters`；不再复制一份 delta |
| `idle-before.jsonl` / `idle-after.jsonl` | 成功等待由 case event 与可用 exit code 表示；详细记录只留 git 外 |
| `client-exit-code.txt` / `idle-after-exit-code.txt` / `metrics-after-exit-code.txt` | `raw/case-lifecycle.jsonl` — 每 case 一行，含已落盘 exit code 与 outcome |
| `client.stdout.log` / `client.stderr.log` | 仅在 case 失败时保留，命名 `raw/failures/<case_id>.log` |
| `runtime-samples.jsonl` / `system-samples.jsonl` | 不进 git（见 §6.2） |

目标：**单个 public run ≤ 12 个文件**（当前 122–141）。

---

## 6. 各 artifact 的处置

### 6.1 `requests.jsonl` — 采样 + schema 瘦身

单条记录 1,088 B 中可移除 412 B（38%），且**无信息损失**：

| 类别 | 字段 | 处置 |
|---|---|---|
| run/case 级常量 | `run_id` `concurrency` `repetition` `model` `record_type` `schema_version` `measured` | 提升到 `run.yaml`、summary 或 lifecycle；`case_id` 逐条保留为 join key |
| 可由时间戳导出 | `e2e_seconds` `decode_seconds` `ttft_seconds` `tpot_seconds` | 移除；保留 4 个 `*_monotonic_ns` 即可完全复算 |
| 冗余 id | `response_request_id`（与 `request_id` 相同）、`request_id`（可由 case + `request_index` 拼出） | 移除；`request_id_verified` 保留结论 |
| wall clock | `start_wall_utc` `end_wall_utc` | 只保留 `start_wall_utc`，用于跨日志关联 |

保留：`case_id`、4 个 monotonic 时间戳、`input_tokens`、`output_tokens`、`token_count_source`、`http_status`、`success`、`timeout`、`error_type`、`error_message`、`finish_reason`、`stream_event_count`、`content_chunk_count`、`request_index`、`request_id_verified`。

**不改变任何指标的可计算性**——移除的都是常量、副本或纯导出量。

### 6.2 时间序列采样 — 不进 git

`runtime-samples.jsonl` + `system-samples.jsonl` 合计 29 MB，且项目已明确它们是 **supporting evidence，不是 pass gate**（GPU/system telemetry 不作饱和或容量判据）。

完整数据入 Tier B；git 内只保留 `derived/summary.json` 已有的 per-case 聚合（min / median / max、峰值等待队列、峰值 KV cache）。需要曲线时从 Tier B 取——**峰值与分布摘要足以支撑现有全部结论。**

### 6.3 `server.log` — 截断

5.0 MB。git 内保留启动段（至 ready）、停止段、全部 `WARNING` / `ERROR` / 异常行、尾部 200 行；完整日志入 Tier B。若 run 失败，**完整 server.log 进 git**（§2.3）。

### 6.4 `derived/summary.json` — 加预算

当前均值约 107 KB，而 showcase 每次打开就 fetch 它。标准：**≤ 256 KB**。超出时移除 `cases[]` 中已被 `concurrency_summary` 覆盖的重复字段，而不是提高预算。

### 6.5 M0 证据树 — 冻结

`m0-platform-qualification/` 122 个文件保持原样，不追溯改造。它已关闭且结构不复用（[AGENTS.md](../../AGENTS.md) §11 已列为归档）。新标准只对 M1 起的 run 生效。

---

## 7. 预算与强制

| 对象 | 上限 |
|---|---|
| 单个 public run 目录 | 12 个文件 / 1 MiB |
| git 内单个证据文件 | 512 KiB |
| `derived/summary.json` | 256 KiB |
| `benchmarks/raw-results/` 总计 | 60 个文件 / 8 MiB（M0 树除外） |
| tracked 文件总数中 raw results 占比 | ≤ 30%（M0 树从分子、分母均排除） |

**标准没有 CI 就只是愿望。** 落地时加 `scripts/check-repo-hygiene.sh`，在 CI 中对上述每一项做硬失败，并输出超限文件清单。

### 完整性链接的红线

`run.yaml` 为每个 Tier B 文件记录三个字段：`sha256`、`record_count`、`bytes`。加上 release tag 与文件名，共五个字段。

**这五个字段就是全部。** 一旦出现以下任何一项，说明 M0 的失败模式回来了，立即停止并回退：

- 独立的 manifest 文件或 manifest 版本
- 校验工具链、staging 流程、publish attestation
- 把 checksum 不匹配变成拒绝执行的闸门（它只应产生一条 comparison warning）

参见 [AGENTS.md](../../AGENTS.md) §4 常设非目标。M0 曾为此产出 1,137 行的 `scripts/m0/m0-evidence.sh`。

---

## 8. 落地路径

### 8.1 关键判断：不改测量路径

**benchmark 工具的测量与写入逻辑不需要大改。** 完整 raw 继续原样写入 `artifacts/private/`——那里没有体积压力，且完整保真对分析有价值。

需要改的是**发布路径**：`scripts/experiments/sanitize-public.sh` 增加字段投影、采样、lifecycle 聚合、截断。风险和工作量都远小于改测量路径。

### 8.2 顺序

| # | 动作 | 依赖 |
|---|---|---|
| 1 | 发布路径加字段投影 + 采样 + lifecycle 聚合 + 截断 + `sampling` 字段 | 无 |
| 2 | `check-repo-hygiene.sh` + CI 硬失败 | 无 |
| 3 | 现有 M1 public 树按新标准重新发布（M0 树不动） | 1、2 |
| 4 | 时间序列改为只入 Tier B；建首个 milestone Release | 1 |
| 5 | writer 侧 per-case 文件聚合（§5） | 需改 `run-benchmark.sh`，与其 250 行预算的偿债一并做 |
| 6 | writer 侧 request 记录 schema 瘦身（§6.1） | 需同步 `request-metrics.schema.jsonl` 与 `summarize_metrics.py` |

1–4 不触碰测量代码。5–6 是 writer 改动，可延后。

### 8.3 关于 git history

现有大 blob 已在 history 中，**删除工作区文件不会减小 clone 传输量**。

但 clone 传输量本来就只有 5.71 MiB，不是问题。因此：**不重写 history。** `git filter-repo` 或 squash 的收益（约 −4 MB 传输）不足以换取历史可追溯性的损失和 force push 的风险。

M0 保持冻结；M1 起的 public copy 按 §7 预算审计。
