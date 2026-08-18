# M1 benchmark 产出与 public evidence 投影

> 本文只比较 producer 单次产出与发布目标。留存预算和采样原则的 owner 是
> [证据留存与仓库卫生标准](../experiments/evidence-retention.md)，执行状态只见
> [current-status](../context/current-status.md)。
> 预算 ≤ 150 行。

## 决策

`run-benchmark.sh` 继续把完整、未采样的 run 写入 gitignored staging/private：
它是分析与重算的事实源，不因公开仓库预算而改写。`sanitize-public.sh` 从该目录
新建一个 public destination，完成字段投影、成功请求采样、case lifecycle 合并和
server log 截断；source 保持不变。

现代 successful run 的 producer 通常写出约 `60–61 + 9 × completed cases` 个文件。
固定部分包含 server 生命周期、warmup、sampler 与 run-level telemetry；每个 case
再扇出 Prometheus snapshot、idle 记录、client log 和 exit code。public target
不是 producer 的镜像，而是五文件的审阅投影。

## 单次产出对比

| 阶段 | Private producer | Public success target | Sanitizer 动作 |
|---|---|---|---|
| Metadata/config | `run.yaml` + frozen config | `run.yaml` | configuration 已嵌入，不复制 config |
| Server lifecycle | start/ready/stop/inspect 小文件与 logs | `raw/server/server.log` | success 截断；failure 完整；run lifecycle 由 `run.yaml` 承载 |
| Warmup | requests/events/idle/stdout/stderr | — | success 不发布；failure 保留相关证据 |
| Requests | `raw/requests.jsonl` | `raw/requests.jsonl` | 全部失败 + 确定性成功采样；字段投影 |
| Case lifecycle | case events + idle wait + 已落盘 exit/outcome | `raw/case-lifecycle.jsonl` | 每 case 一行；不补造未落盘的 exit code |
| Telemetry | exposition、series、per-case Prom | `derived/summary.json` | 使用既有 per-case counter/runtime/system 聚合；完整 raw 只留 git 外 |
| Derived | summary + cases + concurrency summary | `derived/summary.json` | 两个 JSONL sidecar 与 summary 等价才省略，否则失败 |

```text
<run-id>/
├── run.yaml
├── derived/summary.json
└── raw/
    ├── requests.jsonl
    ├── case-lifecycle.jsonl
    └── server/server.log
```

失败 case 可以额外产生或保留 failure-bearing artifacts；五文件只描述 successful
run 的常态，不是删除失败证据的上限。

## Request 投影

发布副本逐条保留 `case_id` 作为 lifecycle/summary join key，以及：

- `request_index`、`start_wall_utc`；
- `start_monotonic_ns`、`first_content_monotonic_ns`、
  `last_content_monotonic_ns`、`end_monotonic_ns`；
- input/output token 与 token count source；
- HTTP、success/timeout、error、finish 与 stream/content count 状态；
- `request_id_verified` 结论。

四个 duration 可由 monotonic timestamps 复算；run/model/case 常量、重复 request ID、
`cache_salt` 和 `end_wall_utc` 不进入逐条 public record。Sanitizer 对每 case 使用
head 20 + tail 20 + fixed-stride interior，每 case 最多保留 60 条成功记录；
全部失败记录始终保留。实际 stride、字段表和计数写入
`summary.json.sampling`，并声明 public sample 不能重算权威 percentile。

## Lifecycle 与一致性边界

`case-lifecycle.jsonl` 合并 start/end event、outcome 和 producer 实际写出的
`client`、`idle-after`、`metrics-after` exit code。Successful `idle-before`
不会写 exit-code 文件，`metrics-before` 的 return code 也从未落盘，因此发布侧
不声称恢复“全部 exit code”。

若 run outcome、request、case outcome 或已落盘 exit code 显示失败，sanitizer
保留完整 failure tree 与完整 server log，再额外写出采样元数据和 lifecycle。
这类 run 可以超过 hygiene 预算；预算失败必须可见，不能靠删除失败来通过。

`derived/cases.jsonl` 和 `derived/concurrency-summary.jsonl` 只有在 canonical JSON
值分别等于 `summary.json.cases` 和 `summary.json.concurrency_summary` 时才不发布。
Telemetry 的公开 owner 是 summary；不再生成一份重复的 `runtime-deltas.jsonl`。

## 验收与非目标

- 同一 source 重复运行产生相同 public requests、lifecycle 与 summary。
- 五文件输出通过 JSON/YAML 解析、自动隐私扫描和 repository hygiene；之后仍需人工审计。
- Showcase manifest 只引用实际发布的 final-reference summaries。
- 完整 raw 保留在 gitignored staging/private；发布 Tier B 时，每 milestone 一个 Release
  archive；Release notes 记录 source commit、filename、SHA256 与 run count，不回填各 `run.yaml`。

本次不改 benchmark 测量路径、不建设 manifest/attestation 工具链、不重写 Git
history，也不把 sanitizer 的成功退出当成公开许可。
