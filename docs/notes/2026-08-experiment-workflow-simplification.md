# 2026-08 实验工作流简化

状态：Accepted

## 背景

M0 需要处理两台实体设备的 inventory、SSH/remote execution、IP、MAC、hostname、网络拓扑、NIC counter 和本机路径。为了安全关闭这一阶段，仓库采用了更严格的 private/public evidence tree、manifest、SHA256、staging、sanitization、secret scan 和 publication verification。

这些措施服务于 M0 当时真实存在的基础设施隐私与发布风险，M0 的技术结论不因此改变。

## 发现

实践中，这套 audit-style packaging 对个人 AI Infra showcase 项目的后续普通 benchmark 带来了过高的实现和维护成本，也挤占了 Runtime、GPU、Kubernetes、Observability 和 Control Loop 实验的时间。

## 决定

从 M1 起采用 [Experiment Repository Convention](../experiments/README.md)：

- 每个 run 记录最小 metadata 和可复现配置；
- `raw/` 原则上不原地修改，`derived/` 可以重新生成；
- warm-up 与 measured run 分开，失败结果保留；
- 结论继续区分 Observed Fact、Interpretation 和 Hypothesis；
- 公开前仍执行 copy、基础 sanitization、secret scan 和 manual privacy review。

后续 Milestone 不再强制 audit-style canonical packaging，也不默认要求 staging lifecycle、cryptographic sealing、global schema、Git index gate、per-Milestone adapter 或 artifact attestation。若某次实验出现新的特殊风险，再针对该风险增加局部规则。

同样地，revision、ownership label、hash 和 fingerprint 在普通 benchmark
中只作 evidence matching 与 comparison metadata。非安全 mismatch 应进入
warning 并由研究者决定是否重跑，不得成为执行、summary 生成或 report
展示的 eligibility gate。自动停止仅服务于请求/服务生命周期故障及真实的
硬件、操作安全边界，不以性能指标阈值驱动。

## M0 legacy handling

M0 historical documentation、raw evidence path 和 tooling 全部保留，不迁移、不删除、不按新约定重写。它们记录 M0 的 closeout 方法和深入审阅依据，但不作为 M1–M10 的标准模板。

这次调整降低的是 packaging 复杂度，不降低 raw evidence、可复现性、privacy hygiene 或 Fact / Interpretation / Hypothesis 分离要求。
