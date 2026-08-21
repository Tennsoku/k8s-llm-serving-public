# AGENTS.md — `serving/`

继承根 `AGENTS.md`。本文件只补充写代码时的额外约束。**预算 ≤ 90 行。**

---

## 这里的代码是实验工具，不是产品

判断标准是**能不能重跑出同样的数**，不是能不能应对任意输入。

多写的每一层校验、每一个 fallback、每一个"以防万一"的分支，都要在往后每次改动里被重新理解一遍。这是这个目录已经付过的代价：`run-benchmark.sh` 687 行、`benchmark_utils.py` 705 行。

---

## 校验只在两处

1. **外部输入穿过信任边界**：CLI 参数、config 文件、HTTP 响应、解析外部格式
2. **实际观测到过的失败模式**：有 log、有复现步骤

其余一律不加。特别是：

- 不校验自己函数之间的内部不变量——上游刚构造的 dict，下游不用再检查字段存在
- 不为"不可能"的分支写处理
- 不写多层 fallback；第一层失败就带上下文退出
- 不静默吞 warning 后继续

不确定属不属于这两类：**不加**，在产出说明里列为"未防护的假设"。

---

## 描述性元数据不是闸门

`run_id`、`git.dirty`、`config_fingerprint`、`case_contract_fingerprint`、`model revision`、`cache_salt` 全部是**用于把 run 对齐到环境/配置/workload 的描述性字段**。

它们的用途上限是：mismatch 时产生一条 **comparison warning**。

它们**不是**授权、attestation、eligibility 或 audit 闸门。不要因为 fingerprint 不匹配就拒绝生成 summary、拒绝执行、或隐藏结果。研究型工作流里，可恢复的配置/元数据错误应当被保留、说明、修正、重跑——而不是被工具拒绝。

这条规则被反复违反过，是本目录最常见的偏移。

---

## 抽象

见根 §5：**两个真实调用点**才可以抽象。

在这个目录额外注意：

- 一次性脚本不要加 helper 函数、wrapper、抽象层
- 只有一个取值的配置项写死，不要做成参数
- 只有一个生产者的数据不要定 schema
- 不要为"下个 milestone 可能要用"预留扩展点

---

## 失败数据

timeout、OOM、non-zero exit、HTTP error、server restart、部分完成的请求——**全部保留**。

- 不删、不改写成成功、不从 summary 里过滤
- `raw/` 原则上不原地修改
- 解析或分析逻辑有缺陷时：修逻辑、重新生成 `derived/`，**不要改 `raw/` 去迎合结论**
- 重试用新 run ID，不覆盖失败的 run

---

## 测量语义

宁可少报一个数字，也不要报一个语义不清的数字。

- duration 用 monotonic clock；wall-clock 只用于跨日志关联
- HTTP streaming chunk **不默认等于** model token；chunk 间隔不直接声称为 ITL/TPOT
- 客户端测量与服务端指标要能交叉验证，不一致时如实报告不一致
- 版本敏感的 API 先在 pinned runtime 上做一次 smoke

---

## 行数例外与现存债务

`run-benchmark.sh` 是跨 milestone 递增的单一 lifecycle owner；本轮复核基线为 711 行，例外于根 §2 的 Shell 250 行硬上限。后续新增仍须先声明 scope / budget 并优先减法；不得为凑行数拆成只有单一调用点的 helper 或 phase script。

`benchmark_utils.py` 仍按根 §2 作为**待偿债务，不是先例**；不要援引其规模为新增辩护。
