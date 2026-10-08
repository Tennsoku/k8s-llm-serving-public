# M3 PVC Warm Startup

**Observed Fact**：Warm PVC启动创建→Ready为170s，init/main均无重启。

| 项目 | 结果 |
|---|---|
| Pod UID | `48a2a50f-5605-4cfd-9635-bfd1e7e11432` |
| Pod创建 / 首次Ready（UTC） | 2026-09-26T15:13:12Z / 2026-09-26T15:16:02Z |
| 创建→Ready / main启动→Ready | 170s / 169s |
| init state耗时（秒级记录） | 同秒 |
| init/main restartCount / init exit | 0 / 0 / 0 |
| 缓存分支 | 完成标记命中，跳过复制与逐字节比较 |
| non-thinking HTTP/选模/完整结束 | 5/5 |
| 配对cold创建→Ready / 本轮差值 | 221s / 51s |

## 限制

- cold仅指目标PVC为空，源资产已在节点；不含下载，page cache未控制。
- 无init/main cgroup内存曲线；节点内存不能归属为容器/GPU内存。
- HTTP400缺对应客户端capture；watch路径曾复用，非零退出码无法唯一归属。

## 复核

以下路径相对Tier B内同名run；按Pod UID过滤watch，用对象时间计算Ready，watch时间仅表示client接收。
- `raw/pod-watch/stdout.log`
- `raw/pod-after/stdout.log`
- `raw/init-follow-01/stdout.log`
- `raw/workload-before/stdout.log`
- `raw/*-request*/{stdout.log,exit-code.txt}`
- `20260926-m3-pvc-cold-r01/raw/pod-{watch,after}/stdout.log（同级配对cold run）`

在仓库根目录执行（复核同名run的完整raw）：

```bash
python3 scripts/experiments/summarize-m3-lifecycle.py <tier-b-root>/20260926-m3-pvc-warm-r02
```
