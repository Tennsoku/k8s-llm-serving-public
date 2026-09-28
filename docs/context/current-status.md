# Current Status

> **本文件是项目进度的唯一 owner。** 其他任何文件出现"当前进行中 / 已完成"的状态描述都是缺陷——改成链接到这里。
>
> **更新契约**：每次收工时检查本文件是否需要同步（ `AGENTS.md` §10）。只写"现在在哪、下一步做什么、有什么在挡路"，**不写结论、不写数据、不写证据清单**——那些的 owner 为 `docs/reviews/`。
>
> **预算 ≤ 60 行。** 超出说明写进了不属于这里的内容。

---

**最后更新**：2026-09-27

---

## 当前进度

| Milestone | 状态 |
|---|---|
| M0 — Platform Qualification | ✅ [review](../reviews/m0-review.md) |
| M1 — Single-Node vLLM Baseline | ✅ [review](../reviews/m1-review.md) · [showcase](../../showcase/m1/) |
| M1p — Public Closeout / Repackage | ✅ [showcase](../../showcase/m1/) |
| M2 — Serving 优化（量化 / 投机解码 / 前缀缓存） | ✅ [review](../reviews/m2-review.md) · [showcase](../../showcase/m2/) |
| M2p — 多 adapter 准备 | ✅ [review](../reviews/m2p-review.md) |
| M3 — Kubernetes 与 GPU workload | 🚧 |
| M4 — 可观测性、SLO 与诊断闭环 | 🚧 |
| M5 — 服务生命周期与最小弹性闭环 | ○ |
| M6 — 深度观测、灰度与韧性扩展 | ○ |
| M7 — 容量成本与最终收尾 | ○ |

范围与 exit criteria 见 [Roadmap](../Roadmap.md)。

## Next Steps

M3 Complete Pre-close: 证据整理与验证完成，待最终核对，文档补完。

M4.3 完成。下一步是 M4.4 SLO 与告警。

## Blockers

无遗留执行阻塞。
