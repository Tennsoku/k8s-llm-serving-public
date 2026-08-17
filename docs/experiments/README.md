# Experiment Repository Convention

从 M1 起，实验使用一套轻量、项目级目录约定。目标是保留可复现性、原始数据和隐私卫生，而不是为每个 Milestone 建立一套 evidence framework。

M0 的 historical evidence tree、review 文档和 publication tooling 保持原样，不迁移，也不要求改成此结构。

## Run directory

每次实验使用独立目录：

```text
artifacts/private/<milestone>/<run-id>/
├── run.yaml
├── raw/
└── derived/
```

例如：

```text
artifacts/private/m1/20260807-m1-concurrency-c08-r01/
```

`artifacts/private/` 默认由 Git 忽略。`run-id` 应能区分实验、关键变量和 repeat；不要求全项目使用复杂的编号系统。

## `run.yaml`

`run.yaml` 记录理解和重放该次实验所需的最小 metadata：时间、Milestone、Git 状态、逻辑节点、Runtime、Workload、repeat 和 outcome。

从 [`templates/experiments/run.yaml`](../../templates/experiments/run.yaml) 复制起步，并按 Milestone 增加必要字段。它是模板，不是严格的 global schema；不需要为了新增字段建立 schema version governance。

建议记录实际运行值，而不是计划值：

- `timestamp_utc` 使用 run start 的 UTC 时间；
- `git.dirty` 说明运行开始时工作区是否有改动，它是 provenance 信息，不是 canonical hard gate；
- `environment.node` 使用 `spark-a` 这类逻辑标签，不记录物理 hostname；
- `repeat` 表示当前 run 在同一实验点中的 1-based repetition index；
- `outcome` 可按需要使用 `success`、`failed`、`timeout`、`oom`、`aborted` 或 `invalid`，但这些不是 global enum。

## Raw 与 derived

| 目录 | 内容 | 处理原则 |
|---|---|---|
| `raw/` | request-level data、server log、metrics snapshot、命令直接输出 | 原则上不原地修改；失败输出同样保留 |
| `derived/` | summary、table、percentile、plot | 必须能由 `raw/` 和已记录配置重新生成，可以重建 |
| `run.yaml` | 本次运行的 metadata 和实际 outcome | 可在运行结束后补全实际结果 |

如果 parser 或分析逻辑有缺陷，应修复逻辑并重新生成 `derived/`，不要改写 `raw/` 来配合结论。

## Exploratory 与 canonical

Exploratory run 用于学习、调试、参数探索和形成 hypothesis。它可以来自 dirty tree，可以失败，也可以只有部分 telemetry，但仍应清楚标记 outcome。

Canonical run 用于支撑 Benchmark Report 或 Milestone conclusion。它至少应固定并记录：

- Runtime、model/revision 与关键参数；
- workload、受控变量和唯一改变的变量；
- warm-up 与 measured run 的边界；
- raw output、失败和已知限制；
- 结论到 run directory 的可追溯关系。

这两个词是 run 的用途标签，不是额外目录层级。Canonical 不代表 audit package；本约定不要求 sealing、manifest lifecycle、clean-tree hard gate 或 Milestone-specific adapter。

这是研究型 workflow。可恢复的 run、配置、metadata 或分析错误应被保留、
说明、修正并重跑，而不是由工具拒绝执行或隐藏 summary。Revision、
ownership label、hash 和 fingerprint 只用于把 run 与环境、配置、workload
及指标对齐；mismatch 是 comparison warning，不是授权、attestation 或
eligibility gate。Request `cache_salt` 是控制 prefix-cache identity 的
workload 参数，但它同样不承担 evidence authenticity 审查。

## Failure preservation

失败也是容量和可靠性证据。Timeout、OOM、non-zero exit、HTTP error、server restart 和部分完成的请求都不应被删除或改写成成功。将失败的原始输出保存在 `raw/`，并在 `run.yaml` 的 `outcome` 或实验说明中记录恢复行为。重试使用新的 run ID，不覆盖失败 run。

可用轻量 helper 捕获单条命令：

```bash
run_id=20260807-m1-concurrency-c08-r01
scripts/experiments/capture-command.sh \
  "artifacts/private/m1/$run_id/raw" \
  environment -- nvidia-smi
```

它会创建 `raw/environment/`，保存 `command.txt`、`stdout.log`、`stderr.log` 和 `exit-code.txt`。已有同名 capture 不会被覆盖。

## Publication workflow

只有准备提交公开结果时才创建 public copy：

```text
private run
  -> copy and sanitize
  -> basic secret scan
  -> manual review
  -> commit selected public result
```

公开、脱敏后的 representative run 放在：

```text
benchmarks/raw-results/<experiment-family>/<run-id>/
```

**哪些 artifact 以什么形态进入公开树，见 [证据留存与仓库卫生标准](evidence-retention.md)**——三层留存、采样契约、文件数与体积预算由该文档规定；本文只管目录结构与脱敏。

通用 sanitizer 的最小用法：

```bash
run_id=20260807-m1-concurrency-c08-r01
private_node_name=example-private-host
scripts/experiments/sanitize-public.sh \
  "artifacts/private/m1/$run_id" \
  "benchmarks/raw-results/vllm-single-node/$run_id" \
  --literal "$private_node_name"
```

脚本只修改新建的 public destination，不修改 private source。成功且无 request failure
的 run 按 [证据留存标准](evidence-retention.md) 生成 Tier A 白名单副本；run、
request、case outcome 或已落盘 exit code 显示失败时保留 failure-bearing tree 与全部失败记录，
并明确提示 hygiene 可能失败，避免为满足预算丢弃失败证据。

进入 public copy 的非 NUL regular file 会处理当前 hostname、IP、MAC、home/user path
和重复的 `--literal` 值，并在复制前后扫描常见 credential/token pattern。目标目录必须
尚不存在；含疑似 secret 或 configured literal 的内部路径会被拒绝，而不是自动重命名。
进入副本的 NUL-containing artifact 原样复制，但仍接受基础 secret byte scan；文件名、
binary 内容和未配置的私有标识仍需人工检查。任何 non-zero 都是 review gate；自动检查
通过也不等于批准公开。不要把 inline credential 放入被捕获的命令。

## Manual privacy checklist

- [ ] 无 credential、token、private key 或认证配置。
- [ ] 无 private hostname、IP、MAC 或未配置到 sanitizer 的私有标识。
- [ ] 无个人绝对路径或不应公开的基础设施细节。
- [ ] 无不应公开的 prompt、dataset 或用户数据。
- [ ] 公开的 config、raw result、derived result 与报告结论一致。

公开前还应查看 `git diff` 和待提交文件列表。Sanitizer 是降低常见泄漏风险的 helper，不是 publication attestation。
