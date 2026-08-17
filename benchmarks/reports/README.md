# Benchmark 报告与查看器

## Summary 查看器

[`benchmark-summary-viewer.html`](benchmark-summary-viewer.html) 用于在浏览器中快速阅读一次 vLLM benchmark 的 `derived/summary.json`。

最简单的使用方式：

1. 保持 `benchmark-summary-viewer.html` 与 `benchmark-summary-viewer.js` 在同一目录；
2. 用 Firefox 或 Chrome 打开 HTML；
3. 拖入或选择目标 run 的 `derived/summary.json`。

文件只在当前浏览器页面内解析；查看器不会上传数据，也不依赖 CDN 或前端构建工具。

页面当前支持 summary schema v1 / v2，主要展示：

- TTFT、TPOT、E2E 与 request/token throughput；
- repetition median 和 min–max range；
- 按真实 `ΔConcurrency` 归一化的边际吞吐收益；
- running/waiting requests、KV Cache、preemption 与 GPU utilization；
- container NVML allocation、cgroup memory、Host MemAvailable、swap/reclaim/OOM；
- raw validation、case 完整性、失败/timeout 与 per-repeat 明细。

如果需要通过 URL 自动加载同源 summary，可只在本机 loopback 启动静态 server：

```bash
python3 -m http.server 8000 \
  --bind 127.0.0.1 \
  --directory "$(git rev-parse --show-toplevel)"
```

然后打开：

```text
http://127.0.0.1:8000/benchmarks/reports/benchmark-summary-viewer.html?src=/artifacts/private/m1/<run-id>/derived/summary.json
```

作为其他静态页面的子组件时，使用精确的 `mode=embedded`：

```text
benchmark-summary-viewer.html?mode=embedded&src=<same-origin-summary-url>
```

Embedded 模式隐藏 standalone topbar、上传入口、footer 和通用 knee heuristic，
保留 context、数据质量、KPI、曲线、case/repetition 和 evidence 区域。缺少或无法
读取 `src` 时会在 iframe 内显示错误，不会伪装成已加载结果。Showcase 必须先把
summary path 相对自己的 manifest URL 解析为完整同源 URL，再写入 viewer query；
不能把未经解析的 `../../...` 直接传给 iframe。

Host 可附加 opaque `host_token` 防止快速切换时旧 iframe 响应覆盖新状态。Viewer
会向同源 parent 发送：

```text
{ source: "benchmark-summary-viewer", version: 1, hostToken,
  type: "loaded" | "error", detail }
```

通知是可选旁路；viewer 自身的 loaded/error 状态不依赖 parent。完整的实际集成见
[`showcase/m1/`](../../showcase/m1/)。

不要把包含 `artifacts/private/` 的 repository root 绑定到 `0.0.0.0` 或对外暴露。

## 解读边界

- 页面当前仍只展示同一个 run 内的 concurrency 对比。viewer 已读取
  schema v2 的 `context`、selection criteria 和 post-run indicator
  annotations；model/runtime/workload/experiment 字段和 fingerprint 为后续
  跨 run 匹配与差异提示提供输入，但当前页面不自动判定两个 run 是否“可比”。
- 自动 knee 分析只是趋势提示。最高成功 concurrency 不是 performance knee 或 capacity boundary。
- TPOT 是请求级平均 decode 间隔的分位，不是 token-level ITL。
- 图中的 min–max 是 repetition range，不是置信区间。
- DGX Spark 上 aggregate framebuffer memory 可能为 unsupported；null 不会被显示为 0。
- container NVML allocation、cgroup memory、Host memory 与 KV Cache 属于不同作用域，不能相加。
- Raw evidence 仍是 benchmark 结论的最终依据。
