# M3 Liveness Probe

**Observed Fact**：6次liveness失败后，同UID容器重启并重新Ready。

| 项目 | 结果 |
|---|---|
| 注入 Pod UID | `4e27d4d4-76b3-4585-81dd-365d77875169` |
| startup 成功（watch接收，UTC） | 20:37:30 |
| 故障probe失败次数 / 时间段（UTC） | 6 / 20:37:40–20:40:10 |
| 注入Pod restartCount | 0→1 |
| kubelet重启事件 / 同UID重新Ready（UTC） | 20:40:10 / 20:43:00 |
| 注入Pod曾为ready endpoint | true |
| 恢复配置后的替换Pod Ready（UTC） | 2026-09-26T20:46:08Z |
| 后补HTTP/选模/完整结束 | 5/5 |

## 限制

- 仅一次故障重启，不推算长期可靠性。
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
python3 scripts/experiments/summarize-m3-lifecycle.py <tier-b-root>/20260926-m3-probe-liveness-r01
```
