# M1 Showcase

这个目录是 M1 closeout 的交互式报告入口。它把人工撰写的 analysis 放在最上层，
并将两种 evidence drill-down 分开：

- `index.html`：M1.4 workload conclusions与单run summary；
- `compare.html`：M1.5/M1.6中设计的 baseline/candidate comparison。

Single-run selector 使用四份 M1.4 canonical-config replay、一份 M1.3 historical
summary 与一份 M1.5 bounded-boundary summary；comparison selector 包含三个 M1.5 OVAT pair 与一个 M1.6 small/medium pair。
所有 selector 都从 `benchmarks/raw-results/m1-vllm-baseline/` 读取 published summary。
分析与 Pages 的执行状态只见 [current-status](../../docs/context/current-status.md)。

## 结构

```text
showcase/m1/
├── index.html
├── index.json
├── showcase.css
├── showcase.js
├── compare.html
├── compare.css
├── compare.js
├── comparisons.json
└── analysis/
    ├── milestone.json
    ├── short-short.json
    ├── short-long.json
    ├── long-short.json
    ├── long-long.json
    ├── m1.3-historical.json
    ├── bounded-boundary.json
    ├── medium-model.json
    └── comparisons/
        ├── max-model-len.json
        ├── max-num-seqs.json
        └── gpu-memory-utilization.json
```

`index.json` 是 single-run 的selected run展示清单。`comparisons.json` 维护稳定 run registry
和预先配对的 studies；浏览器不会枚举 repository，也不会允许审阅者任意选择两个
run。最终 summaries 仍保存在 canonical public run 的
`benchmarks/raw-results/<family>/<run-id>/derived/summary.json`，showcase 不维护第二份
summary 或手写 numeric delta。

Comparison selector 包含三个 M1.5 runtime OVAT，以及一个 M1.6 small/medium
model compatibility pair。页面从 captured summary 的 configuration、experiment、
environment、data completeness 与 case contract 计算 comparability，不把手写状态
当作判据。项目当前状态只见 [current-status](../../docs/context/current-status.md)。

## 本地预览

必须从 repository root 启动只绑定 loopback 的静态 server：

```bash
python3 -m http.server 8000 \
  --bind 127.0.0.1 \
  --directory "$(git rev-parse --show-toplevel)"
```

然后打开：

```text
http://127.0.0.1:8000/showcase/m1/
http://127.0.0.1:8000/showcase/m1/compare.html
```

不要把包含 `artifacts/private/` 的 repository root 绑定到 `0.0.0.0` 或暴露给
其他主机。不要使用 `file://`，因为 manifest、analysis 和 summaries 都通过
same-origin `fetch` 加载。

## Run analysis contract

Run analysis 使用 schema version 1，核心字段为：

- `takeaway`：人工策展的一句话结论；分析未完成时可以为 `null`；
- `operating_references`：`c1`、`c_eff`、`c_pressure` 和
  `highest_tested`，每项显式标记 `pending`、`observed`、`unknown` 或
  `not_applicable`；
- `claims`：`observed_fact`、`interpretation`、`hypothesis` 或 `unknown`；
- `limitations`：解读边界；
- `links`：config、public evidence、review 和 reproduction 入口。

## Comparison contract

Comparison analysis 同样使用 schema version 1，但 `kind` 是
`comparison_analysis`，以稳定 `comparison_id` 关联 `comparisons.json`。它只保存
`takeaway`、`claims`、`limitations` 和 `links`，不保存复制的指标值。

Study policy 同时绑定 metric set、candidate experiment kind 与允许的 axis。Runtime OVAT
axis 对应一个 runtime config path；`model_identity` 是一个逻辑变化轴，投影为 model
`id`、`path`、`artifact_revision` 与 `served_name` 四个字段。Axis panel 始终只显示一项，
并通过分页控件逐项检查这些字段变化。

页面从两份 summary 确定性投影 baseline、candidate、绝对 delta 和相对 delta，
并分别显示：

- `data_status`：`complete`、`partial` 或 `unavailable`；
- `comparability`：`controlled`、`descriptive_only` 或 `not_comparable`；
- `outcome`：实际 lifecycle outcome。

数值为 `null` 时保持 `n/a`；baseline 为 0 时不计算百分比；页面不做显著性检验，
也不自动生成“提升”“退化”“获胜”或推荐。没有完整 performance point 的 failure
仍展示 lifecycle/stop evidence，但不会伪造 performance delta。

当前三个 OVAT fixtures 都是 `descriptive_only`：M1.4 baseline 的 sampler interval
为 0.5 秒且有三次 repetition，candidate 为 1 秒且只有一次 repetition，因此
case contract fingerprint 不同。观测值仍可展示，但不能包装成严格 controlled
causal conclusion。`max_num_seqs` study 还必须同屏显示 actual output-shape drift；
`gpu_memory_utilization` study 必须把 NVML process、cgroup 与 host memory scope 分开。

`pending` 表示分析或实验尚未完成；`unknown` 表示已经完成预声明测试，但在范围内
没有直接证据支持更强结论。缺文件、未运行、comparison mismatch 或 unsupported
telemetry 都不等于 `Unknown`。

## 发布切换

Evidence 固定后，对每个 selected run 或 comparison：

1. 保留并审阅 private raw evidence；
2. 按 experiment convention 脱敏并发布 representative runs 到
   `benchmarks/raw-results/`；
3. 将 `index.json` / `comparisons.json` 的 summary paths 切换到 public canonical
   summaries，并把 `source_status` 设为 `published`；
4. 核对 expected run/config IDs、comparison axis、matched concurrency 和实际 token
   shape；
5. 将人工 analysis 更新到 `reviewed` 或 `final`；
6. 在实际 GitHub Pages publishing source/artifact 中验证所有 URL 同源可读。

GitHub Pages 发布的是 branch source 或 Actions artifact 的静态快照，不能在浏览器
端自动列举 `{run-id}`。页面、manifest、analysis、viewer 和被引用的 public
summaries 必须同时进入同一个 Pages origin。发布页面只接受 `source_status: published`；
evidence drill-down 必须指向具体文件或 public GitHub tree，不能指向无 `index.html` 的目录。
