# Current Status

> **本文件是项目进度的唯一 owner。** 其他任何文件出现"当前进行中 / 已完成"的状态描述都是缺陷——改成链接到这里。
>
> **更新契约**：每次收工时检查本文件是否需要同步（ `AGENTS.md` §10）。只写"现在在哪、下一步做什么、有什么在挡路"，**不写结论、不写数据、不写证据清单**——那些的 owner 为 `docs/reviews/`。
>
> **预算 ≤ 60 行。** 超出说明写进了不属于这里的内容。

---

**最后更新**：2026-08-16

---

## 当前进度

| Milestone | 状态 |
|---|---|
| M0 — Platform Qualification | ✅ [review](../reviews/m0-review.md) |
| M1 — Single-Node vLLM Baseline | ✅ [review](../reviews/m1.3-review.md) · [showcase](../../showcase/m1/) |
| M1.5 — Public Closeout / Repackage | 🚧 |
| M2 — Serving 优化（量化 / 投机解码 / 前缀缓存） | 🚧 |
| M3 — Kubernetes 与 GPU workload | ○ |
| M4 — 可观测性、SLO 与 Tracing | ○ |
| M5 — 路由 / 灰度 / 伸缩 / 故障 | ○ |

范围与 exit criteria 见 [Roadmap](../Roadmap.md)。

## Next Steps

收尾 [`Roadmap.md`](../Roadmap.md) 的 **M1.5 — Repackage & 呈现修复**：人工复审 
启动 M2 的准备工作，包括详细落地计划、workload contract 等。

## Blockers

| 项 | 说明 |
|---|---|
| showcase 修复待部署 | GitHub Pages 已启用；published-only 与 evidence 链接修复已在工作区验证，尚待推送后在 Pages origin 复验；`medium-model.json` 与 boundary analysis 仍为 `draft`，boundary representative summary 尚未发布或注册到 `index.json` |
| 三个 OVAT pair 仅 descriptive | baseline 与 candidate 的 sampler interval 和 repetition 数不同，case contract fingerprint 不匹配，不能包装成 controlled causal conclusion |
| K8s GPU 集成未验证 | M0 明确将其列为边界，M3 实测；ARM64 + GB10 上 device plugin 成熟度低于 x86 |

## 待优化项 - 非阻塞
| 项 | 说明 |
|---|---|
| Tier B 链接未完成 | 完整 raw 目前只在 gitignored staging；Release attachment 与 `run.yaml` 五字段链接尚未建立 |
