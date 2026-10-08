# M3 PVC Cold Startup

**Observed Fact**：Cold PVC启动创建→Ready为221s，init/main均无重启。

| 项目 | 结果 |
|---|---|
| Pod UID | `33bb6f61-2e30-4b9a-ac3e-bc081e9cdf7e` |
| Pod创建 / 首次Ready（UTC） | 2026-09-26T12:59:58Z / 2026-09-26T13:03:39Z |
| 创建→Ready / main启动→Ready | 221s / 182s |
| init state耗时（秒级记录） | 35s |
| init/main restartCount / init exit | 0 / 0 / 0 |
| 缓存分支 | 复制并校验，日志耗时35.406s |
| non-thinking HTTP/选模/完整结束 | 5/5 |

## 限制

- cold仅指目标PVC为空，源资产已在节点；不含下载，page cache未控制。
- 无init/main cgroup内存曲线；节点内存不能归属为容器/GPU内存。
- 初始5请求均触及32-token上限；后补non-thinking成功晚于启动窗口。

## 复核

以下路径相对Tier B内同名run；按Pod UID过滤watch，用对象时间计算Ready，watch时间仅表示client接收。
- `raw/pod-watch/stdout.log`
- `raw/pod-after/stdout.log`
- `raw/init-log/stdout.log`
- `raw/workload-before/stdout.log`
- `raw/*-request*/{stdout.log,exit-code.txt}`

在仓库根目录执行（复核同名run的完整raw）：

```bash
python3 scripts/experiments/summarize-m3-lifecycle.py <tier-b-root>/20260926-m3-pvc-cold-r01
```
