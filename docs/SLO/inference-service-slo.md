# 推理服务 SLO 规范（第一版）

> 文件路径：`./docs/SLO/inference-service-slo.md`  
> 状态：Draft / Baseline  
> 适用阶段：单节点、小模型、推理运行时基线评测  
> 主要用途：
>
> 1. 作为 Benchmarking Plane 的实验设计与结果判定依据  
> 2. 作为 Monitoring Plane 的 Prometheus Recording Rules 与 Grafana Dashboard 输入参考  
> 3. 为后续 Autoscaling、Admission Control、KV Cache 保护和运行时横向对比提供统一服务质量边界

---

## 1. 文档目标

本文件定义 AI Inference Platform 第一版最小可落地 SLO。

当前阶段的目标不是对外承诺生产级 SLA，也不是直接声明平台已经达到某一行业标准，而是建立一套：

- 可测量
- 可复现
- 可比较
- 可校准
- 可映射到监控系统
- 可供控制面消费

的推理服务质量规范。

本版本优先覆盖四个最小目标：

1. 请求可用性
2. Time to First Token，TTFT
3. Decode 流畅度
4. OOM 与服务稳定性

并额外定义 Goodput，用于连接服务质量与系统吞吐。

---

## 2. SLO 基本模型

每一条 SLO 必须由以下元素共同构成：

```text
SLO =
Service
+ Workload Class
+ SLI
+ Objective
+ Statistical Window
+ Eligibility
+ Exclusions
+ Data Source
+ Minimum Sample Requirement
+ Violation Action
```

例如：

> 在滚动 30 分钟窗口内，对于 Interactive Small 负载，至少 95% 的 Eligible Requests 应在 2 秒内返回第一个输出 Token。

该定义中包含：

| 字段 | 值 |
|---|---|
| Service | Inference Service |
| Workload Class | Interactive Small |
| SLI | TTFT |
| Objective | ≤ 2 秒 |
| Compliance Target | ≥ 95% |
| Window | Rolling 30 Minutes |
| Eligibility | 符合输入输出范围且被服务接受的请求 |
| Data Source | Gateway / Benchmark Client |
| Violation Action | Dashboard 标记、告警、容量调查 |

任何脱离 Workload、统计窗口和样本范围的单独 P95 数字，都不能作为完整 SLO。

---

## 3. 当前适用范围

### 3.1 适用对象

本版本适用于：

- 单模型推理服务
- OpenAI-Compatible API
- Streaming Response
- 单节点或单副本 Baseline
- vLLM 作为第一阶段参考运行时
- 小模型实验环境
- Benchmark 与受控负载测试

### 3.2 暂不覆盖

本版本暂不覆盖：

- 多 Region 服务
- 多租户正式 SLA
- 训练任务
- Batch Job Deadline Guarantee
- 多模型路由
- 跨集群流量治理
- 用户身份与权限 SLO
- 商业赔偿条款
- 生产级 99.9% 以上长期可用性承诺

### 3.3 文档性质

当前所有阈值均属于：

```text
Initial Target / Benchmark Contract
```

而不是：

```text
Verified Production Capability
```

完成第一轮 Baseline Benchmark 后，必须根据实测结果进行修订。

---

## 4. 服务边界

### 4.1 请求路径

```text
Benchmark Client / User Client
              |
              v
     API Gateway or Direct API
              |
              v
       Inference Runtime
              |
              v
       Model Execution
              |
              v
          GPU / CPU
```

### 4.2 时间测量边界

第一版以客户端观测时间为主要依据。

```text
Request Start
    |
    |-- Client transport
    |-- Gateway processing
    |-- Queueing
    |-- Prefill
    |-- First token emitted
    |-- Decode
    |-- Last token received
    v
Request Complete
```

定义：

```text
Request Start:
客户端开始发送请求的时间

Request Accepted:
服务端完成基本请求校验并接受请求的时间

First Token:
客户端收到第一个有效输出 Token 的时间

Request Complete:
客户端收到完整响应或流结束标记的时间
```

第一版 TTFT 默认使用：

```text
Client-observed TTFT =
First Token Received Timestamp
- Request Start Timestamp
```

后续如 Gateway 与 Runtime 均暴露 Trace，可进一步拆分：

- Network Latency
- Gateway Latency
- Queue Latency
- Prefill Latency
- Runtime Emission Delay

---

## 5. Workload Class

LLM 推理延迟与输入长度、输出长度和并发高度相关，因此 SLO 必须绑定 Workload Class。

### 5.1 Interactive Small

用于实时、小上下文交互。

```yaml
workload_class: interactive-small
input_tokens:
  min: 1
  max: 256
output_tokens:
  min: 1
  max: 128
streaming: true
priority: normal
```

主要评价指标：

- Availability
- TTFT
- ITL / TPOT
- Goodput

### 5.2 Interactive Medium

用于中等上下文交互。

```yaml
workload_class: interactive-medium
input_tokens:
  min: 1
  max: 2048
output_tokens:
  min: 1
  max: 256
streaming: true
priority: normal
```

主要评价指标：

- Availability
- TTFT
- E2E Latency
- TPOT
- Goodput

### 5.3 Long Context / Batch

用于长上下文或非即时任务。

```yaml
workload_class: long-context
input_tokens:
  min: 2049
  max: 8192
output_tokens:
  min: 1
  max: 512
streaming: optional
priority: batch
```

主要评价指标：

- Completion Rate
- Input Token Throughput
- Output Token Throughput
- OOM Rate
- Deadline Compliance

该类别不与 Interactive Small 共用同一 TTFT 目标。

---

## 6. Eligible Request

### 6.1 纳入 SLO 的请求

满足以下条件的请求计为 Eligible Request：

- 请求到达目标推理服务
- 请求格式合法
- 模型名称合法
- 输入 Token 数未超过该 Workload Class 上限
- 请求的 `max_tokens` 未超过该 Workload Class 上限
- 请求未被客户端主动取消
- 请求未被测试框架标记为 Warm-up
- 请求未被明确标记为 Chaos / Stress Overflow Case

### 6.2 排除项

以下请求不计入 Availability 或 Latency SLO：

- HTTP 400 类客户端输入错误
- 无效模型名
- 无效认证信息
- 超过公开 Token Limit 的请求
- 客户端主动断开连接
- Benchmark 工具自身异常
- Warm-up 请求
- 明确标记的故障注入请求

### 6.3 仍视为服务失败的情况

以下情况必须计入服务失败：

- HTTP 500
- HTTP 502 / 503 / 504
- 请求超时
- Runtime 返回空响应
- Streaming 中途异常终止
- Response Schema 不合法
- OOM 导致请求失败
- Server Crash
- Runtime Restart 导致请求丢失
- Admission Control 错误拒绝本应支持的请求

---

## 7. 第一版 SLO 总览

| ID | SLO | Workload | Objective | Window |
|---|---|---|---:|---|
| SLO-1 | Availability | Interactive Small | ≥ 99.5% | Rolling 30 min |
| SLO-2 | TTFT Compliance | Interactive Small | ≥ 95% 请求 TTFT ≤ 2 s | Rolling 30 min |
| SLO-3 | Decode Compliance | Interactive Small | ≥ 95% 请求的 Request-Level P95 ITL ≤ 100 ms | Rolling 30 min |
| SLO-4 | Stability | Supported Workload | OOM-caused failure = 0 | Per Benchmark Run |
| SLO-5 | Goodput | Interactive Small | 建立 Baseline，后续定义 Target | Per Benchmark Run |

补充观测目标：

| ID | Metric | Initial Target |
|---|---|---:|
| OBS-1 | P99 TTFT | ≤ 4 s |
| OBS-2 | P99 ITL | ≤ 200 ms |
| OBS-3 | Timeout Rate | ≤ 0.5% |
| OBS-4 | Server-side Error Rate | ≤ 0.5% |
| OBS-5 | Unexpected Restart Count | 0 |
| OBS-6 | Malformed Response Rate | 0 |

---

## 8. SLO-1：请求可用性

### 8.1 定义

```text
Availability =
Successful Eligible Requests
/
Total Eligible Requests
```

成功请求必须同时满足：

- HTTP 状态码为 2xx
- 响应格式合法
- 至少返回一个有效输出 Token
- Streaming 正常结束
- 请求未发生超时

### 8.2 目标

```text
Workload: Interactive Small
Objective: Availability >= 99.5%
Window: Rolling 30 Minutes
Minimum Samples: 200
Preferred Samples: 1000+
```

### 8.3 Error Budget

```text
Allowed Failure Ratio =
1 - Availability Objective
= 0.5%
```

示例：

```text
Eligible Requests: 10,000
Allowed Failed Requests: 50
```

### 8.4 Prometheus 参考

候选原始指标：

```promql
inference_requests_total{
  service="inference-service",
  workload_class="interactive-small",
  outcome="success"
}

inference_requests_total{
  service="inference-service",
  workload_class="interactive-small"
}
```

Recording Rule：

```promql
sum(rate(inference_requests_total{
  workload_class="interactive-small",
  eligible="true",
  outcome="success"
}[30m]))
/
sum(rate(inference_requests_total{
  workload_class="interactive-small",
  eligible="true"
}[30m]))
```

建议记录为：

```text
slo:inference_availability:ratio_30m
```

---

## 9. SLO-2：TTFT

### 9.1 定义

```text
TTFT =
First Output Token Received Timestamp
- Request Start Timestamp
```

TTFT 包含：

- 客户端到服务端传输
- Gateway 处理
- 请求排队
- Runtime Scheduling
- Prefill
- 首 Token 返回

### 9.2 目标

```text
Workload: Interactive Small
Compliance Target: >= 95%
Threshold: TTFT <= 2 seconds
Window: Rolling 30 Minutes
Minimum Samples: 200
```

补充观察值：

```text
P99 TTFT <= 4 seconds
```

### 9.3 Benchmark 判定

单次 Benchmark Run 同时输出：

- Mean TTFT
- P50 TTFT
- P90 TTFT
- P95 TTFT
- P99 TTFT
- TTFT Compliance Ratio
- TTFT Violation Count

其中真正对应 SLO 的是：

```text
TTFT Compliance Ratio =
Requests with TTFT <= 2s
/
Eligible Requests
```

P95 TTFT 用于辅助阅读，但 Compliance Ratio 更适合直接计算 Error Budget。

### 9.4 Prometheus 参考

Histogram：

```text
inference_ttft_seconds_bucket
inference_ttft_seconds_sum
inference_ttft_seconds_count
```

P95 查询：

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(inference_ttft_seconds_bucket{
      workload_class="interactive-small"
    }[30m])
  )
)
```

Compliance Ratio：

```promql
sum(rate(inference_ttft_seconds_bucket{
  workload_class="interactive-small",
  le="2"
}[30m]))
/
sum(rate(inference_ttft_seconds_count{
  workload_class="interactive-small"
}[30m]))
```

建议记录为：

```text
slo:inference_ttft_compliance:ratio_30m
slo:inference_ttft:p95_30m
slo:inference_ttft:p99_30m
```

---

## 10. SLO-3：Decode 流畅度

### 10.1 指标选择

第一版使用 ITL：

```text
ITL_i =
Token Timestamp_i
- Token Timestamp_(i - 1)
```

对于单个请求：

```text
Request-Level P95 ITL =
该请求所有 Inter-Token Latency 的 P95
```

### 10.2 目标

```text
Workload: Interactive Small
Compliance Target: >= 95%
Request Condition: Request-Level P95 ITL <= 100 ms
Window: Rolling 30 Minutes
Minimum Samples: 200 Requests
```

补充观察值：

```text
P99 ITL <= 200 ms
```

### 10.3 注意事项

以下指标不可直接等价：

```text
P95 ITL <= 100 ms
```

与：

```text
Average Generation Speed >= 10 tokens/s
```

前者是 Token 间隔的尾延迟约束，后者是平均吞吐。两者必须分别统计。

### 10.4 TPOT 补充指标

当客户端无法可靠采集每个 Token Timestamp 时，可以使用：

```text
TPOT =
Request Decode Duration
/
Generated Output Tokens
```

第一版 Dashboard 同时展示：

- Request-Level P95 ITL
- Average TPOT
- Output Token Throughput

但 SLO 判定优先使用 ITL。

### 10.5 Prometheus 参考

Token-level Histogram：

```text
inference_inter_token_latency_seconds_bucket
```

Request-level Compliance Counter：

```text
inference_requests_total{
  workload_class="interactive-small",
  decode_slo="met"
}
```

Compliance Ratio：

```promql
sum(rate(inference_requests_total{
  workload_class="interactive-small",
  eligible="true",
  decode_slo="met"
}[30m]))
/
sum(rate(inference_requests_total{
  workload_class="interactive-small",
  eligible="true"
}[30m]))
```

建议记录为：

```text
slo:inference_decode_compliance:ratio_30m
slo:inference_itl:p95_30m
slo:inference_itl:p99_30m
```

---

## 11. SLO-4：OOM 与服务稳定性

### 11.1 定义

在 Supported Workload 范围内：

```text
OOM-caused Request Failure Rate = 0%
Unexpected Runtime Restart Count = 0
```

Supported Workload 指：

- 请求属于已定义 Workload Class
- 并发未超过当前公布的 Capacity Limit
- 输入输出长度未超过上限
- 未执行故障注入
- 未执行明确的 Saturation Stress Test

### 11.2 目标

```text
OOM-caused failed requests: 0
Unexpected process restarts: 0
CrashLoopBackOff events: 0
```

### 11.3 Stress Test 中的判定方式

在明确的压力实验中，OOM 不一定直接判为实验失败，但系统必须满足：

- 能够在资源耗尽前拒绝新请求
- 已运行请求尽量不被破坏
- Runtime 不进入永久 Crash Loop
- 服务能够自动恢复
- 失败原因能够被监控系统识别
- 控制面动作能够被记录

压力实验应优先观察：

```text
Controlled Rejection
>
Process OOM
>
Node-level Instability
```

### 11.4 Prometheus 参考

候选指标：

```text
inference_oom_failures_total
process_start_time_seconds
kube_pod_container_status_restarts_total
kube_pod_container_status_last_terminated_reason
```

示例：

```promql
increase(inference_oom_failures_total[30m]) > 0
```

```promql
increase(kube_pod_container_status_restarts_total{
  container="inference-runtime"
}[30m]) > 0
```

---

## 12. SLO-5：Goodput

### 12.1 定义

一个 Good Request 必须同时满足：

```text
Request Success
AND TTFT <= 2 seconds
AND Request-Level P95 ITL <= 100 ms
```

Goodput：

```text
Goodput =
Number of Good Requests
/
Benchmark Wall Time
```

单位：

```text
good requests / second
```

### 12.2 目的

Raw Throughput 只回答：

> 系统每秒完成了多少请求？

Goodput 回答：

> 系统每秒完成了多少满足用户体验目标的请求？

示例：

```text
Raw Throughput: 12 req/s
Goodput: 8 good req/s
```

表示每秒虽然完成 12 个请求，但只有 8 个同时满足 TTFT 与 Decode SLO。

### 12.3 第一版目标

第一阶段不预设绝对 Goodput Target。

流程：

1. 建立 Concurrency 1 / 2 / 4 / 8 / 16 Baseline
2. 找到 Goodput 峰值
3. 找到 Raw Throughput 与 Tail Latency 的拐点
4. 定义推荐 Operating Point
5. 再将 Goodput 目标写入下一版 SLO

### 12.4 Prometheus 参考

```promql
sum(rate(inference_requests_total{
  workload_class="interactive-small",
  eligible="true",
  good_request="true"
}[5m]))
```

建议记录为：

```text
slo:inference_goodput:rps_5m
```

---

## 13. Supporting SLI 与 Operational Guardrail

资源指标通常不直接作为用户体验 SLO，而作为解释信号、保护阈值和控制面输入。

### 13.1 Supporting SLI

- Running Requests
- Waiting Requests
- Queue Duration
- Batch Size
- GPU Utilization
- GPU Memory Usage
- KV Cache Utilization
- Prefix Cache Hit Rate
- Input Token Throughput
- Output Token Throughput
- CPU Utilization
- Host Memory Usage
- Pod Restart Count

### 13.2 第一版 Guardrail

| Metric | Warning | Critical | Recommended Action |
|---|---:|---:|---|
| KV Cache Utilization | > 80% for 2m | > 90% for 1m | 限流、扩容或降低并发 |
| Waiting Requests | > 8 for 30s | > 16 for 30s | 扩容评估 |
| GPU Memory Usage | > 90% | > 95% | Admission Control |
| GPU Utilization | > 90% for 5m | 与 SLO 违规共同出现 | 容量调查 |
| TTFT Compliance | < 97% | < 95% | 告警与容量分析 |
| Availability | < 99.7% | < 99.5% | 告警 |
| Runtime Restart | — | > 0 | 立即调查 |

这些阈值仅为第一版参考值，必须在 Baseline 后校准。

---

## 14. Benchmarking Plane 输入契约

每次 Benchmark 必须记录以下字段。

### 14.1 环境元数据

```yaml
experiment_id:
timestamp:
git_commit:
host_os:
kernel:
cpu:
system_memory_gb:
gpu:
gpu_vram_gb:
nvidia_driver:
cuda_runtime:
python_version:
pytorch_version:
runtime_name:
runtime_version:
runtime_arguments:
model_name:
model_revision:
model_precision:
tokenizer_revision:
```

### 14.2 Workload 配置

```yaml
workload_class:
streaming:
request_count:
concurrency:
arrival_pattern:
input_token_distribution:
output_token_limit:
temperature:
top_p:
seed:
timeout_seconds:
warmup_requests:
measured_runs:
```

### 14.3 必须输出的结果

```yaml
eligible_requests:
successful_requests:
failed_requests:
availability_ratio:
timeout_count:
server_error_count:
oom_failure_count:
unexpected_restart_count:

ttft_mean_ms:
ttft_p50_ms:
ttft_p95_ms:
ttft_p99_ms:
ttft_compliance_ratio:

itl_mean_ms:
itl_p50_ms:
itl_p95_ms:
itl_p99_ms:
decode_compliance_ratio:

e2e_mean_ms:
e2e_p50_ms:
e2e_p95_ms:
e2e_p99_ms:

request_throughput_rps:
goodput_rps:
input_token_throughput_tps:
output_token_throughput_tps:

peak_gpu_memory_mb:
avg_gpu_utilization_percent:
peak_kv_cache_utilization_percent:
```

---

## 15. 推荐 Benchmark CSV Schema

```csv
experiment_id,timestamp,git_commit,runtime_name,runtime_version,model_name,model_revision,model_precision,workload_class,concurrency,request_count,eligible_requests,successful_requests,failed_requests,availability_ratio,timeout_count,server_error_count,oom_failure_count,unexpected_restart_count,input_tokens_mean,output_tokens_mean,wall_time_seconds,request_throughput_rps,goodput_rps,input_token_throughput_tps,output_token_throughput_tps,ttft_mean_ms,ttft_p50_ms,ttft_p95_ms,ttft_p99_ms,ttft_compliance_ratio,itl_mean_ms,itl_p50_ms,itl_p95_ms,itl_p99_ms,decode_compliance_ratio,e2e_mean_ms,e2e_p50_ms,e2e_p95_ms,e2e_p99_ms,peak_gpu_memory_mb,avg_gpu_utilization_percent,peak_kv_cache_utilization_percent,notes
```

---

## 16. Monitoring Plane Dashboard 输入

建议建立四类 Dashboard。

### 16.1 SLO Overview

核心面板：

- Availability Ratio
- TTFT Compliance Ratio
- Decode Compliance Ratio
- Goodput
- Error Budget Remaining
- Error Budget Burn Rate
- Current SLO Status

建议状态：

```text
Healthy:
所有核心 SLO 均满足

At Risk:
任一 SLO 接近阈值或 Burn Rate > 1

Violated:
任一核心 SLO 低于目标

Insufficient Data:
样本数低于 Minimum Sample Requirement
```

### 16.2 Latency Breakdown

- Queue Latency
- TTFT P50 / P95 / P99
- ITL P50 / P95 / P99
- TPOT
- E2E P50 / P95 / P99
- Input Token Length Distribution
- Output Token Length Distribution

### 16.3 Capacity & Saturation

- Running Requests
- Waiting Requests
- Request Rate
- Request Throughput
- Goodput
- Input Token Throughput
- Output Token Throughput
- KV Cache Utilization
- GPU Memory
- GPU Utilization
- Batch Size

### 16.4 Stability

- HTTP Error Rate
- Timeout Rate
- OOM Failure Count
- Pod Restart Count
- Runtime Restart Count
- Admission Rejection Rate
- Recovery Time
- CrashLoopBackOff Event

---

## 17. Error Budget

### 17.1 Availability Error Budget

```text
Availability Objective = 99.5%
Allowed Failure Ratio = 0.5%
```

```text
Availability Error Budget Remaining =
Allowed Failures
- Actual Failures
```

### 17.2 TTFT Violation Budget

```text
TTFT Compliance Objective = 95%
Allowed Violation Ratio = 5%
```

### 17.3 Decode Violation Budget

```text
Decode Compliance Objective = 95%
Allowed Violation Ratio = 5%
```

### 17.4 Burn Rate

```text
Burn Rate =
Actual Violation Ratio
/
Allowed Violation Ratio
```

示例：

```text
Allowed TTFT Violation Ratio: 5%
Actual TTFT Violation Ratio: 10%
Burn Rate: 2.0
```

含义：

> 当前 TTFT 错误预算消耗速度为预期的两倍。

---

## 18. 告警建议

第一版建议仅建立少量可执行告警，避免告警噪声。

### 18.1 AvailabilityViolation

触发条件：

```promql
slo:inference_availability:ratio_30m < 0.995
```

严重度：

```text
critical
```

### 18.2 TTFTViolation

触发条件：

```promql
slo:inference_ttft_compliance:ratio_30m < 0.95
```

严重度：

```text
warning
```

若同时满足以下条件，则升级：

```text
TTFT Compliance < 90%
OR P99 TTFT > 4s
```

### 18.3 DecodeViolation

触发条件：

```promql
slo:inference_decode_compliance:ratio_30m < 0.95
```

严重度：

```text
warning
```

### 18.4 OOMFailure

触发条件：

```promql
increase(inference_oom_failures_total[5m]) > 0
```

严重度：

```text
critical
```

### 18.5 RuntimeRestart

触发条件：

```promql
increase(kube_pod_container_status_restarts_total{
  container="inference-runtime"
}[15m]) > 0
```

严重度：

```text
critical
```

---

## 19. SLO 校准流程

第一版阈值不得直接视为最终结论。

### 19.1 Baseline

固定：

- Model
- Runtime Version
- Model Precision
- Input Distribution
- Output Limit
- Hardware
- Runtime Arguments

测试：

```text
Concurrency: 1, 2, 4, 8, 16
Warm-up: 3 requests
Measured Requests: >= 200 per case
Measured Runs: 3-5
```

### 19.2 寻找性能拐点

重点观察：

- Raw Throughput 是否仍增长
- Goodput 是否开始下降
- P95 TTFT 是否急剧上升
- P95 ITL 是否超过目标
- Waiting Requests 是否持续积压
- KV Cache 是否接近饱和
- GPU Utilization 是否已无明显吞吐收益
- 是否出现 Timeout、OOM 或 Restart

### 19.3 定义 Operating Point

推荐工作点应满足：

- 核心 SLO 合规
- Goodput 接近峰值
- 资源仍保留安全裕度
- 没有 OOM
- Queue 不持续增长

### 19.4 更新目标

完成 Baseline 后，将当前字段拆分为：

```text
Measured Baseline
Target SLO
Critical Threshold
```

例如：

```text
Measured P95 TTFT: 1.6s
Warning Threshold: 1.8s
SLO Threshold: 2.0s
Critical Threshold: 4.0s
```

---

## 20. 与 Control Plane 的关系

本 SLO 后续可作为控制面输入。

### 20.1 Autoscaling

候选触发信号：

- TTFT Compliance 下降
- Waiting Requests 增长
- Goodput 下降
- Queue Latency 上升
- KV Cache Utilization 上升

### 20.2 Admission Control

候选触发信号：

- KV Cache > 90%
- GPU Memory > 95%
- Waiting Requests 超过上限
- 预计新请求将导致 SLO 违规

### 20.3 Scheduler

候选调度信号：

- 节点可用 GPU Memory
- 模型是否已加载
- 当前 KV Cache Pressure
- 当前 Goodput
- 节点 TTFT Compliance
- 节点 Waiting Queue

### 20.4 Memory Supervisor

候选保护目标：

- OOM Failure = 0
- Runtime Restart = 0
- Supported Workload 下避免 Node-level Memory Pressure
- 优先执行可控限流而非进程 OOM

---

## 21. Definition of Done

本文件第一版视为落地完成，需要满足：

- [ ] Benchmark Client 能采集 TTFT
- [ ] Benchmark Client 能采集 Token Timestamp 或 TPOT
- [ ] Benchmark Client 能输出 Eligible / Success / Failure
- [ ] Benchmark 结果包含 SLO Compliance Ratio
- [ ] Benchmark 结果包含 Goodput
- [ ] Prometheus 能采集请求总数与失败数
- [ ] Prometheus 能采集 TTFT Histogram
- [ ] Prometheus 能采集 ITL 或 TPOT
- [ ] Grafana 存在 SLO Overview Dashboard
- [ ] OOM 与 Runtime Restart 可被监控
- [ ] 至少执行一轮 Concurrency Baseline
- [ ] 根据实测结果完成一次 SLO 校准
- [ ] 文档中记录当前 Capacity Limit

---

## 22. 已知限制

第一版存在以下限制：

- 客户端 TTFT 包含网络开销
- ITL 采集依赖 Streaming Client 精度
- Histogram Bucket 设计可能影响 P95 / P99 精度
- 单节点结果不能代表多副本生产平台
- 小模型结果不能直接外推至大模型
- 8 GB VRAM 环境主要用于机制验证
- Workload Distribution 仍为合成负载
- 尚未覆盖多租户优先级与隔离
- 尚未覆盖 Rolling Update 与 Node Failure
- 尚未定义长期 7 天或 30 天 SLO

---

## 23. 后续版本规划

### v0.2

- 增加 Interactive Medium SLO
- 增加 E2E Latency SLO
- 增加 Multi-window Burn Rate Alert
- 增加 Capacity Limit
- 增加 Admission Rejection SLI

### v0.3

- 增加多副本 SLO
- 增加 Autoscaling Effectiveness
- 增加 Cold Start SLO
- 增加 Rolling Update 可用性
- 增加 Recovery Time Objective

### v1.0

- 基于稳定实验数据固化正式目标
- 形成 Runtime 统一对比标准
- 与 Runbook、Alert、Dashboard、ADR 完整关联
- 支持 Control Plane 自动消费 SLO 信号

---

## 24. 当前第一版结论

第一版最小落地目标：

```text
SLO-1 Availability:
>= 99.5% of eligible Interactive Small requests succeed

SLO-2 TTFT:
>= 95% of eligible Interactive Small requests receive the first token within 2 seconds

SLO-3 Decode:
>= 95% of eligible Interactive Small requests have request-level P95 ITL <= 100 ms

SLO-4 Stability:
0 OOM-caused failures under supported workload

SLO-5 Goodput:
Establish baseline first, then define target operating capacity
```

这些目标共同构成 Benchmarking Plane、Monitoring Plane 和后续 Control Plane 的统一服务质量接口。

核心原则：

> SLO 必须绑定明确的 Workload、统计窗口、样本范围和测量边界。  
> Benchmark 的目标不是只追求最大吞吐，而是寻找满足服务质量约束时的最大 Goodput。
