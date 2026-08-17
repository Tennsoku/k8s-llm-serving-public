# 推理服务 SLO — 设计草案

> **状态：`draft` / proof-of-concept。** 落地在 [M4](../Roadmap.md)，届时用 M1/M2 实测数据校准。
>
> 本文只定义**结构**——SLI 是什么、哪些请求算数、workload 怎么分类。所有 objective 数值标 `TBD`，因为它们必须由实测校准，凭空写下的目标值没有意义。
>
> PromQL、recording rules、alert rules、error budget 计算、dashboard 规格**留到 Prometheus 实际部署后再写**。
>
> 预算 ≤ 200 行。

---

## 1. 为什么 SLO 必须绑定 workload class

LLM 推理的延迟由输入长度、输出长度和并发共同决定，三者的影响机制还不一样。M1 的实测（见 [README](../../README.md#三个值得看的结论)）显示：

- 输入 55 → 5,890 tokens，C1 TTFT 从 12.8 ms 涨到 133 ms（prefill 一次性代价）；
- decode-heavy 负载从 C1 到 C8 吞吐涨 9.8×，prefill-heavy 只涨 2.2×（扩展行为不同）。

**一个跨 workload 的统一 TTFT 目标必然是错的**：对 short-input 太松，对 long-input 太紧。这是本文档存在的根本原因。

---

## 2. SLO 的组成

一条可执行的 SLO 必须写全九项。缺任何一项都会在争议时失效：

```text
SLO = Service
    + Workload Class      # 适用范围
    + SLI                 # 测什么
    + Objective           # 目标值
    + Statistical Window  # 统计窗口
    + Eligibility         # 哪些请求算数
    + Exclusions          # 哪些不算
    + Data Source         # 从哪取数
    + Minimum Sample      # 样本量下限
```

示例形态（数值待定）：

> 滚动 30 分钟窗口内，Interactive Small 负载的 Eligible Requests 中，至少 `TBD%` 在 `TBD` 秒内返回第一个输出 token。

---

## 3. 测量边界

时间口径必须先定义，否则跨来源的数字不可比：

| 分段 | 起点 | 终点 |
|---|---|---|
| **TTFT** | 服务端收到请求 | 首个非空 generated content |
| **E2E** | 同上 | 流结束或响应返回 |
| **Decode 时长** | 首 token | 末 token |
| **TPOT** | decode 时长 ÷ 实际输出 token 数 | — |

约束：

- **HTTP streaming chunk 不等同于 model token。** chunk 间隔不得直接声称为 ITL；要声称 token 级 ITL，需要 runtime 侧证据支持。
- 客户端测量与服务端 histogram 必须能交叉验证，不一致时如实报告不一致。
- 服务启动延迟（模型加载 → ready）不计入 TTFT，单独记录。

---

## 4. Workload Class

```yaml
interactive-small:      # 实时小上下文交互
  input_tokens:  1..256
  output_tokens: 1..128
  streaming: true
  primary_sli: [availability, ttft, tpot, goodput]

interactive-medium:     # 中等上下文交互
  input_tokens:  1..2048
  output_tokens: 1..256
  streaming: true
  primary_sli: [availability, ttft, e2e, tpot, goodput]

long-context:           # 长上下文 / 非即时任务
  input_tokens:  2049..8192
  output_tokens: 1..512
  streaming: optional
  priority: batch
  primary_sli: [completion_rate, token_throughput, oom_rate, deadline]
```

`long-context` **不与 `interactive-small` 共用 TTFT 目标**——理由见 §1。

---

## 5. Eligible Request

### 计入 SLO

- 到达目标服务、格式合法、模型名合法
- 输入 token 数与 `max_tokens` 均在该 class 上限内
- 非客户端主动取消
- 非 warm-up、非故障注入

### 不计入

- HTTP 4xx 客户端输入错误、无效模型名、无效认证
- 超出公开 token limit 的请求
- 客户端主动断连
- benchmark 工具自身异常
- warm-up 与显式标记的 chaos / stress overflow case

### 必须计为服务失败

这一节是重点——**这些是最容易被静默吞掉的失败**：

- HTTP 5xx、请求超时、runtime 返回空响应
- **streaming 中途异常终止**（客户端已收到部分 token，仍算失败）
- response schema 非法
- OOM 导致的请求失败、server crash、runtime restart 导致的请求丢失
- admission control 错误拒绝了本应支持的请求

---

## 6. 五条 SLI

| ID | SLI | 定义 | Workload | Objective | Window |
|---|---|---|---|---|---|
| SLO-1 | Availability | 成功 Eligible Request / 全部 Eligible Request | interactive-small | `TBD` | Rolling 30 min |
| SLO-2 | TTFT Compliance | TTFT ≤ 阈值的请求占比 | interactive-small | `TBD` | Rolling 30 min |
| SLO-3 | Decode Compliance | request-level P95 TPOT ≤ 阈值的请求占比 | interactive-small | `TBD` | Rolling 30 min |
| SLO-4 | Stability | OOM 导致的失败数 | supported workload | `= 0` | Per run |
| SLO-5 | Goodput | 同时满足 SLO-1/2/3 的请求所贡献的 token 吞吐 | interactive-small | 先建 baseline | Per run |

只有 SLO-4 现在就能定值——OOM 导致的失败在 supported workload 下应为零，这不需要校准。

---

## 7. Goodput 与 raw throughput 的区别

raw throughput 会把**已经违反 SLO 的请求**也算进去。系统进入排队饱和后，raw throughput 往往还在涨，而用户体验已经崩了。

M1 的 boundary test 是直接证据：并发 16 → 64，输出吞吐 920 → 1,005 tok/s（+9%），但 TTFT p95 从 1.56 s 涨到 16.78 s。**如果只看吞吐，会得出"还能再加压"的错误结论。**

Goodput 只统计满足延迟目标的请求所贡献的 token，因此它在饱和点之后会下降。这是它比 raw throughput 更适合做容量判据的原因。

---

## 8. 不作为判据的信号

以下信号可作为**辅助上下文**，但不单独决定饱和、容量或 SLO 违约：

| 信号 | 不采用的原因 |
|---|---|
| GPU utilization | M1.3 实测中 C64/C96/C128 都稳定在 96%，不随服务状态变化 |
| KV cache 占用 | boundary test 中队列已达 56、TTFT 16.78 s 时，KV cache 峰值仅 28.9% |
| 显存 / 功耗 telemetry | 统一内存架构下 scope 不清晰，不同 scope 不可相加 |

判据必须是**服务侧信号**：延迟分布、等待队列深度、失败率、goodput。

---

## 9. 落地前的待办（M4）

- [ ] 用 M1/M2 实测分布校准 SLO-1/2/3/5 的 objective
- [ ] 确定各 workload class 的最小样本量
- [ ] 写 recording rules 与 alert rules
- [ ] 客户端测量与服务端 histogram 的一致性验证
- [ ] 至少一次受控实验触发告警并完成定位

**在完成校准之前，本文档不产生任何对外承诺。**
