# AGENTS.md — `docs/`

继承根 `AGENTS.md`。本文件只补充写文档时的额外约束。**预算 ≤ 80 行。**

---

## 写之前

先查根 §3 单一来源表，确认**这份事实的 owner 是不是当前文件**。不是就只放链接。

再问一句：**这段内容如果不写，谁会因此做错什么决定？** 答不上来就不写。文档的用途是支撑决策，不是记录努力。

---

## 长度

根 §2 的预算在 `docs/` 下是硬约束：设计文档 200 行、Milestone 计划 150 行、Review 120 行、ADR 80 行。

超预算时**砍内容，不要拆成多个文件**。拆文件不减少总量，只会制造新的漂移面。

一份文档只服务一个读者、一个问题。同时想服务"reviewer 快速了解"和"实现者查细节"的文档，两边都会做不好。

---

## 结论前置

Review 与结论类文档的顺序是：

```text
结论（1-3 句，先给答案）
    ↓
支撑证据（指向 raw / derived 文件）
    ↓
范围与限制
    ↓
unknowns
```

**不要**先铺 scope、evidence index、方法论，把结论放到第 40 行。读者只有几分钟，前置限定会被读成"没得出结论"。

限定要写，写在结论**之后**。

---

## 状态

进度状态**只写在 `docs/context/current-status.md`**。

README、Roadmap、milestone 计划、review 里出现"当前进行中""已完成 X%"一律是缺陷。它们要么链接到 current-status，要么不提。

历史上这个仓库的 milestone 状态同时存在于 4 个文件，全部漂移到过期值。

---

## 规范类文档

见根 §6。未实现组件的设计笔记 ≤ 1 页，标 `draft`，所有数值目标写 `TBD`。

不要提前定义：全局 enum、schema 版本策略、跨 milestone 的通用契约、还没有第二个消费者的接口。

---

## 归档

`docs/context/m0-*.md`、`docs/context/PUBLICATION-CHECKLIST.md`、`docs/Roadmap-v1-archive.md` 是历史归档。

- 不更新它们
- 不引用它们的流程作为当前标准
- 不把它们当新文档的模板

M0 的 evidence/publication 工作流是**一次性历史产物**，不是后续 milestone 的范式。
