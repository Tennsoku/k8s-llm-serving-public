# M3 流式请求终止：baseline / candidate

**Observed Fact**：baseline 唯一在途流被截断；candidate 唯一在途流在删除 Pod 后继续输出，以 `finish_reason=length` 完整结束并取得 2048 output tokens。
**Interpretation**：candidate 策略支持本次固定 workload 的在途流完成；每侧仅一次观察。

两侧为 worker 单副本 Qwen3-8B，选择 `lore-archivist`；image、vLLM args、资源和请求配置一致，均启用应用层 `--shutdown-timeout 120`。
请求为 C1、thinking=true、ignore_eos=true、temperature=0.6、seed=42、输出上限 2048、timeout=600s。
以下 `raw/...` 为 Release Tier B 归档中本 run 目录内的相对路径；时间为 2026-09-27 UTC。

| 项目 | baseline | candidate |
|---|---|---|
| Pod UID | `79e6c18d-575c-41be-82c6-69e9b3201336` | `fae7eebd-ee48-448e-b0ef-eb7f0c50b969` |
| grace / preStop | 30s / 无 | 120s / sleep 10s |
| 请求 / 成功 / 失败 / timeout / 传输截断 | 1 / 0 / 1 / 0 / 1 | 1 / 1 / 0 / 0 / 0 |
| HTTP / finish_reason | 200 / null | 200 / length |
| input / output tokens（server usage） | 未取得 / 未取得 | 2004 / 2048 |
| E2E / TTFT（s） | 126.534 / 0.556 | 159.675 / 0.596 |
| client / container exit | 1 / 137（Error） | 0 / 0（Completed） |
| 请求开始 | 17:11:45.409 | 17:19:16.892 |
| 删除命令前 UTC | 17:13:21.877 | 17:21:05.616 |
| client 结束 / 报错 | 17:13:51.943 | 17:21:56.568 |
| container finishedAt（秒级） | 17:13:52 | 17:21:59 |
| 请求开始 → 删除（s） | 96.469 | 108.724 |
| 删除 → client 结束（s） | 30.066 | 50.952 |

baseline 原始错误为 `ClientPayloadError: Response payload is not completed`；HTTP 200 不代表流完整。`length` 是达到预设输出上限，不是传输截断。
两侧日志均记录 `draining in-flight requests count=1 timeout=120s`；candidate preStop 17:21:05.715–17:21:15.716，随后 drain，17:21:56.564 处理完成。

原始依据与重算：

- `raw/termination-requests.jsonl` 两行按 `start_wall_utc` 排序对应两侧；case_id、request_id、cache_salt 重复，保留两行。成功/失败/timeout 取请求字段，截断由 transport_error 原文判定；`raw/termination-events.jsonl` 核对 case outcome。
- E2E、TTFT 分别为 `(end_monotonic_ns-start_monotonic_ns)/1e9`、`(first_content_monotonic_ns-start_monotonic_ns)/1e9`。删除时刻取 `raw/delete-baseline-pod/stdout.log` / `raw/delete-pod/stdout.log` 首行，与请求 start/end UTC 相减。
- 配置取 `raw/termination-baseline-target/stdout.log` / `raw/termination-target/stdout.log` 及 `raw/termination-baseline-config/stdout.log` / `raw/termination-config/stdout.log`；按表中 UID 关联 `raw/pod-watch/stdout.log` 的终止状态与 `raw/server-follow-01/stdout.log` / `raw/server-follow-02/stdout.log`。

限制与保留项：

- 实际删除时点不同，grace 与 preStop 同时改变，无法分别归因；未测试删除期新请求路由，不外推其他并发、请求长度或发布流量。
- watch 的 `observed_epoch` 是客户端接收时间；初始 deletionTimestamp 晚于删除命令且随后更新，不作删除开始。container finishedAt 仅秒级，跨主机时钟偏差未校准。
- 无删除 preflight 另有 1/1 成功，E2E 159.376s，不并入 A/B。`raw/pod-after/stdout.log` 显示恢复到 grace30、无 preStop、Ready、restart=0；`raw/restoration-*-request/` 的 5 个功能请求均 HTTP200/finish=stop，仅证明选模功能。
- 非零退出完整保留：baseline client=1；三项 watch=143、server-follow-03=1 均有 `stop-request.txt`，按采集停止解释，不计请求失败。
