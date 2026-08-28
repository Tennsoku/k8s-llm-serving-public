# M1 Showcase

这个目录是 M1 closeout 的交互式展示入口：

- `index.html`：milestone 总结、selected run 结论与单-run summary drill-down；
- `compare.html`：selected runtime OVAT 与 model comparison。

项目执行状态只见 [current-status](../../docs/context/current-status.md)。

## 单一来源

人工结论、限制与 Unknown 的唯一 owner 是
[m1-review.md](../../docs/reviews/m1-review.md)。两个 manifest 的
`analysis_path` 都指向该文件内的 raw-HTML `section` fragment；浏览器只投影匹配
anchor，不维护 fallback 文案或第二份 analysis JSON。旧
[m1.3-review.md](../../docs/reviews/m1.3-review.md) 只保留历史 URL 的兼容入口。

指标的 owner 是各 public run 的 `derived/summary.json`。共享 viewer 从 manifest
选择的 summary 动态加载 run tables、context diagnostics、token shape 和 neutral
baseline-relative delta；showcase 不复制 summary，也不手写 numeric delta。

## 结构

```text
showcase/
├── shared/
│   ├── review-fragment.{js,css}
│   ├── run-{model,app}.js
│   ├── compare-{data,model,view,app}.js
│   ├── showcase.css
│   └── compare.css
└── m1/
    ├── index.html
    ├── index.json
    ├── showcase.js
    ├── compare.html
    ├── compare.js
    └── comparisons.json
```

`index.json` 是 selected-run 清单；`comparisons.json` 持有稳定 run registry 与
预先配对的 studies。浏览器不枚举 repository，也不允许任意选择两个 runs。

## Review fragment contract

每个 active `analysis_path` 使用仓库相对 URL 加 fragment：

```json
{"analysis_path": "../../docs/reviews/m1-review.md#m1-short-long"}
```

目标节点必须是完整 raw HTML：

```html
<section id="m1-short-long"
         class="review-fragment"
         data-analysis-status="final">
  ...
</section>
```

共享 loader 将 fragment 内相对链接按 review 文件位置解析后投影到页面。Markdown
加载失败、anchor 缺失或节点不符合 contract 时直接显示错误；不会降级到内置结论。

## URL 兼容性

既有页面与 query deep links 保留：

```text
showcase/m1/index.html?run=short-long
showcase/m1/compare.html?study=m1.5-max-num-seqs&c=8
```

Run selector、comparison selector、summary iframe、computed metric table 和 evidence
links 的行为不变；只有人工 analysis 的 source 从 JSON 收敛为 review fragment。

## 本地预览

从 repository root 启动只绑定 loopback 的静态 server：

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory .
```

打开 `http://127.0.0.1:8000/showcase/m1/` 与
`http://127.0.0.1:8000/showcase/m1/compare.html`。不要使用 `file://`，因为
manifest、review 和 summaries 都通过 same-origin `fetch` 加载；也不要把包含
`artifacts/private/` 的 repository root 暴露给其他主机。
