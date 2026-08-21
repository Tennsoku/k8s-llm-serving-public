# Current Status

> **本文件是项目进度的唯一 owner。** 其他任何文件出现"当前进行中 / 已完成"的状态描述都是缺陷——改成链接到这里。
>
> **更新契约**：每次收工时检查本文件是否需要同步（ `AGENTS.md` §10）。只写"现在在哪、下一步做什么、有什么在挡路"，**不写结论、不写数据、不写证据清单**——那些的 owner 为 `docs/reviews/`。
>
> **预算 ≤ 60 行。** 超出说明写进了不属于这里的内容。

---

**最后更新**：2026-08-19

---

## 当前进度

| Milestone | 状态 |
|---|---|
| M0 — Platform Qualification | ✅ [review](../reviews/m0-review.md) |
| M1 — Single-Node vLLM Baseline | ✅ [review](../reviews/m1.3-review.md) · [showcase](../../showcase/m1/) |
| M1.5 — Public Closeout / Repackage | ✅ [showcase](../../showcase/m1/) |
| M2 — Serving 优化（量化 / 投机解码 / 前缀缓存） | 🚧 |
| M3 — Kubernetes 与 GPU workload | ○ |
| M4 — 可观测性、SLO 与 Tracing | ○ |
| M5 — 路由 / 灰度 / 伸缩 / 故障 | ○ |
| M6 — 容量成本与收尾 | ○ |

范围与 exit criteria 见 [Roadmap](../Roadmap.md)。

## Next Steps

M1 / M1.5 已在 `m1-freeze-20260818` 冻结；M2 最小 pipeline / comparison 扩展已就绪。
下一步执行 M2.0 compatibility inventory，并落地 M2.1 prefix hit/miss configs 与 smoke。

## Blockers

| 项 | 说明 |
|---|---|
| 无 | — |
