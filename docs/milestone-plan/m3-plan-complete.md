# M3 Complete — Kubernetes GPU Workload 生命周期（执行计划）

> 本文从 [M3 Minimal](m3-plan-minimal.md) 的实测产物继续，负责完整 M3 的执行顺序、实验约束和停手条件。范围、工时与 Exit Criteria 见 [Roadmap](../Roadmap.md#5-m3--kubernetes-基础与-gpu-workloadw3w550-h)，当前进度见 [current-status](../context/current-status.md)，实验结论写入 `docs/reviews/m3-review.md`。
> 预算 ≤ 150 行。

## 研究

完整 M3 要回答：已经跑通一次的 Kubernetes GPU serving，能否从记录的前置条件重建，并在模型慢加载、Pod 删除、模型缓存和 multi-adapter 场景下留下可复查的生命周期证据？

Minimal 是起点，不是完整验收。Complete 不重写一套集群或 Deployment；先基于实际产物做 gap analysis，再补齐 Roadmap 3.1–3.6 和最终对照。

## 进入条件与交接

1. Minimal checkpoint 必须能定位到 manifests、部署说明、private run 和 review 中的实测结果；失败的 minimal 先在原路径收敛，不复制一套替代实现。
2. Complete 的进入位置见 [Roadmap 临时执行拆分](../Roadmap.md#临时执行拆分)；M2 close 依照 [m2-plan](m2-plan.md)，两边 raw、配置、review 和状态不得混写。
3. Multi-adapter 步骤开始前检查 Roadmap M2.5 的 adapter 产物。没有真实可加载资产时，可继续 M3.1–M3.5，但 M3.6 和完整 M3 不能判定完成。
4. 逐项列出 Minimal 已证明、尚未执行和证据不足的内容。只有 direct evidence 可标为已证明；未执行是执行缺口，不是 `Unknown`。

## 执行顺序

```text
Minimal checkpoint → gap analysis
  → M3.1 从零重建与拓扑说明
  → M3.2 GPU 接入重放
  → M3.3 workload/probe 异常路径
  → M3.4 流式请求优雅终止
  → M3.5 模型缓存冷/热启动
  → M3.6 单一打包路径与 multi-adapter
  → K8s 单副本 / M1 裸机受控对照 → review
```

不得为了后续步骤掩盖前一步失败。若需要 reset/rejoin、reboot、清空缓存或改动硬件状态，先停止并取得明确授权。

## 所有步骤共同遵守的规则

1. 沿用 Minimal 已工作的集群、runtime、plugin、image 和 model；只有直接兼容性证据支持时才替换，替换前后不得组成因果对照。
2. 每个生命周期结论都要指向 `artifacts/private/m3/<run-id>/raw/` 中的命令、events、conditions、logs 或 request-level 记录；`derived/` 必须可重算。
3. 对照只改变预先声明的一个因素。条件无法对齐时并列报告，不计算“开销”“收益”或归因。
4. 失败、timeout、OOM、restart、被截断的 stream 和 non-zero exit 全部保留；重试使用新 run ID。
5. exact probe、grace period 和 cache timing 由实测校准；本计划不预写 SLO，也不把单次观察写成 tail latency。
6. 只保留一条集群搭建路径、一种打包方式和一种缓存预热方案；不为两个节点建设通用平台层。

## M3.1 — 可复现集群

1. 把 Minimal 中实际成功的主机前置、控制面、CNI、join、label/taint 和验证步骤收敛为小型脚本加说明；记录 exact versions、输入、命令、预期观察和失败恢复点。
2. 给出 CNI、控制面位置及 label/taint 的最小选择理由，理由只服务两 Spark testbed，不外推生产集群。
3. 经授权后执行一次受控的从零重建；分层保留 control plane、CNI、每个 Worker join 和重建后 node conditions。脚本和说明必须来自被重放的版本。
4. 若控制面与 workload 共用 Spark，采集 control-plane 活动并把潜在干扰列为限制；不把两台 Spark 描述成生产 DGX 集群。

## M3.2 — GPU 接入重放

1. 固定 Kubernetes container runtime 与 NVIDIA runtime 的接法、Device Plugin 版本及必要的 RuntimeClass；若默认 runtime 已满足，不并行维护第二条接法。
2. 在重建后的两节点重新证明 plugin Running、Capacity/Allocatable `nvidia.com/gpu`、显式 GPU request 的 scheduling event、容器内 GPU 可见和 CUDA 运算。
3. 记录 ARM64/GB10 上实际出现的兼容性问题、最小复现和解法。没有直接证据时写执行缺口，不从 Docker pass 推断 Kubernetes pass。

## M3.3 — Workload 与 Probe 异常路径

1. 基于实际状态需求记录 Deployment 而非 StatefulSet 的选择理由，并冻结 CPU/memory/GPU requests/limits、QoS class、模型 mount 和 Service 行为。
2. 用冷启动时间校准 `startupProbe`，证明模型加载期不被 liveness 重启；用 EndpointSlice 与请求结果证明 readiness 只控制流量资格。
3. 各做一次小型受控异常：readiness 失败时 endpoint 被摘除但容器不重启；启动完成后让容器保持运行但 liveness 持续失败，捕获 kubelet `Unhealthy` event 后再观察重启。直接 kill 主进程不能作为 liveness 证据；不新增故障注入框架。
4. 若 pinned runtime 不能提供语义可区分的健康端点，记录限制并用最小 exec probe 补足；不要用生成请求作 liveness。

## M3.4 — 流式请求优雅终止

1. 固定一个足够跨越删除时刻的 streaming workload，记录请求开始、首 token、Pod 删除、末 token、finish reason 和 client outcome 的统一时间线。
2. 对比未配置与配置 `preStop` + `terminationGracePeriodSeconds` 的两个小型 run；除终止策略外保持 image、model、prompt、sampling 和删除时点一致。
3. 报告总请求、失败、timeout、完成和截断数，以及 Pod 从 deletion timestamp 到退出的时长。只有 client 收到完整结束语义才算未截断。
4. 找到能让本次固定 workload 完成的有界配置即可；不搜索全局最优 grace period。PDB、rolling update 和 canary 留给 M5。

## M3.5 — 模型缓存冷/热启动

1. 使用 PVC 承载模型权重或下载缓存；先固定 StorageClass、access mode、mount、image、model 和 probe，再定义空缓存 cold 与已填充缓存 warm。
2. 两侧记录 Pod scheduled、容器启动、模型加载开始、Ready、读取字节/日志、失败和统一内存观测。若只有单次 run，只报告 single-run observation。
3. 根据实际瓶颈在 init container 与 sidecar 中选择一种预热方式并记录取舍，不同时实现两套。
4. 清空或替换缓存前取得授权；使用新 PVC 能形成 cold 条件时，不删除已有研究数据。

## M3.6 — 打包与 Multi-adapter

1. Helm 与 Kustomize 只选一种；复用现有 manifests，参数只覆盖 Minimal 与 Complete 已有的真实差异，不建立全局 values/schema。
2. 加载 M2.5 提供的 adapter set，使单次请求能显式指定 adapter；保留 Pod args、加载日志、每个 adapter 的最小请求及 outcome。
3. 若 runtime 无法同时加载该集合，保留 compatibility failure；不要用不同 system prompt 冒充 multi-LoRA pass。
4. 从记录的前置条件重放打包入口。成功标准是同一入口能重建已验证行为，不是发布 chart 或建设 registry。

## 单副本对照与收尾

1. 选择 M1 已有且 K8s 可重放的同一 model/workload，在单副本下重跑裸机与 K8s。重新运行两侧，不把历史 M1 数字直接与本次 K8s candidate 组成因果比较。
2. 对齐 image、model、args、requests、prompt、sampling 和请求顺序；无法对齐的 runtime/container 差异明确列出，只报告整套路径差异。
3. 报告 client 侧 TTFT/TPOT/E2E、吞吐、失败数和 startup-to-Ready；单次或样本不足时不写 tail/capacity 结论。
4. 在 M3 review 中把核心结论分为 Observed Fact、Interpretation、Hypothesis、Unknown，并逐条映射到 Roadmap Exit Criteria；缺失证据与实现缺陷分开列。
5. 收工时按唯一状态 owner 更新 [current-status](../context/current-status.md)；其他文档只链接，不复制完成状态或实测数字。

## 不做

不做 HA/生产集群外推、自定义 CRD/controller/scheduler、GPU sharing/MIG、集群发行版矩阵、全局 schema、自动参数搜索或性能最优；不提前建设 M4 的 Prometheus/SLO/Tracing，也不提前建设 M5 的 gateway、rolling/canary、autoscaling 和故障演练。
