# M3 Readiness Probe

**Observed Fact**：故障readiness阻止新Pod入池，观察期间容器未重启。

| 项目 | 结果 |
|---|---|
| 注入 Pod UID | `9ffaac44-edf4-47bf-abe8-8df7072adc09` |
| startup 成功（watch接收，UTC） | 20:16:31 |
| 故障probe失败次数 / 时间段（UTC） | 4 / 20:16:31–20:16:46 |
| 注入Pod restartCount | 0→0 |
| 注入Pod曾为ready endpoint | false |
| 恢复配置后的替换Pod Ready（UTC） | 2026-09-26T20:19:37Z |
| 后补HTTP/选模/完整结束 | 5/5 |

## 限制

- 故障Pod从未Ready，未测试同一健康Pod因readiness失败被摘除。
- 后补5个功能请求晚于观察窗口，缺同期Pod UID归属；不用于恢复时延。

## 复核

以下路径相对Tier B内同名run；按Pod UID过滤watch，用对象时间计算Ready，watch时间仅表示client接收。
- `raw/probe-inject.json`
- `raw/pod-watch/stdout.log`
- `raw/event-watch/stdout.log`
- `raw/endpoint-watch/stdout.log`
- `raw/pod-after/stdout.log`
- `raw/*-request/{stdout.log,exit-code.txt}`

在仓库根目录执行（复核同名run的完整raw）：

```bash
python3 scripts/experiments/summarize-m3-lifecycle.py <tier-b-root>/20260926-m3-probe-readiness-r01
```
