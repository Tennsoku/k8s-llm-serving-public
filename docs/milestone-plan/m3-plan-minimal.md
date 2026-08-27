# M3 Minimal — Kubernetes GPU Serving 最小闭环（执行计划）

> 本文负责 [Roadmap 临时执行拆分](../Roadmap.md#临时执行拆分)中 M3 Minimal 的执行顺序、证据要求和停手条件。完整 M3 的范围、工时与 Exit Criteria 仍见 [Roadmap M3](../Roadmap.md#5-m3--kubernetes-基础与-gpu-workloadw3w550-h)，当前进度见 [current-status](../context/current-status.md)。执行后的结论写入 `docs/reviews/m3-minimal-review.md`，不写回本计划。
> 预算 ≤ 150 行。

## 目标

在不完整完成 M3 的前提下，验证两台 Spark 能否作为 Kubernetes GPU Worker，把 GPU 暴露为 `nvidia.com/gpu`，并调度一个显式申请 GPU 的单副本 vLLM Deployment。

最小闭环还要观察模型加载期间的 probe 状态转换，并完成一次功能实测。它只证明当前冻结组合在一次受控运行中可用；不证明从零重建、长期稳定性、容量、Kubernetes 开销或生产就绪。

M0 的 Docker GPU smoke 只能作为排障基线，不能替代 Kubernetes runtime、Device Plugin、extended resource 或 Pod 内 CUDA 的实测；边界见 [qualification notes](../environment/qualification-notes.md#bnd-006--kubernetes-gpu-integration)。

## 临时切换与交接

```text
Roadmap 临时执行拆分中的 Minimal 入口
  → 冻结 M2 已有 raw、配置和待收尾清单
  → M3 Minimal
  → 形成可独立复查的 minimal checkpoint
  → 返回 Roadmap 临时执行序列
```

Checkpoint 后续顺序见 [Roadmap 临时执行拆分](../Roadmap.md#临时执行拆分)。M2 close 继续遵守 [m2-plan](m2-plan.md)，不能因 minimal 跑通而省略；本计划不复制其状态或 close criteria。

## 时间阶段参考

| 阶段 | 唯一目标 |
|---|---|
| 前段 | 固定一种集群路径；两台 Spark 加入；runtime 与 Device Plugin 可观测 |
| 中段 | 两节点 GPU resource/CUDA Pod 通过；单副本 vLLM 进入 probe 验证 |
| 收尾/缓冲 | 处理已出现的兼容性问题、重放部署、完成一次实测与说明 |

收尾缓冲不用于开启第二种发行版、GPU Operator 或存储方案。Roadmap timebox 结束仍未闭环时，保留失败证据并报告执行缺口；不要把未执行项写成 `Unknown`，也不要用临时绕过伪造 pass。

## 执行顺序

```text
M3m.0 冻结输入与证据目录
  → M3m.1 两台 GPU Worker Ready
  → M3m.2 runtime/plugin → resource → 每节点 CUDA Pod
  → M3m.3 vLLM Deployment/Service → 三类 probe
  → M3m.4 一次功能实测 → 同配置重放 → minimal checkpoint
```

后一步只在前一步的直接证据成立后开始。重试使用新 run ID，失败输出不覆盖。

## 所有步骤共同遵守的规则

1. 集群发行版、CNI、container runtime 接法和 Device Plugin 各选一种；记录选择理由，不做方案对比。
2. 固定实际使用的 Kubernetes、runtime、Toolkit、plugin、vLLM image digest、模型 revision 和完整命令；版本敏感命令先在冻结组合上 smoke。
3. 每次运行按 [实验目录约定](../experiments/README.md) 写入 `artifacts/private/m3/<run-id>/`；`kubectl` 输出、events、logs 和请求结果放 `raw/`，摘要由 raw 重算。
4. 使用逻辑节点名，不在公开候选中保留 hostname、IP、credential 或个人路径。描述性 revision/hash 只做对齐，不做运行许可。
5. 只校验外部边界和实际出现的失败。命令 non-zero、Pod `Failed`、restart、timeout、OOM 和部分请求全部保留并带上下文退出。
6. 不从 `nvidia-smi` framebuffer 的 `N/A` 推断无内存占用；不以 GPU utilization 声称 saturation 或 capacity。

## M3m.0 — 冻结输入

1. 由 M2 执行方确认已到 pre-close 交接点，并在 M2 自有产物中保留未完成的 close 清单；M3 文档不改写 M2 状态。
2. 选择本地 WSL2 部署 control plane 配置远端 worker 的设计固定整体集群拓扑结构。
3. 从 `templates/experiments/run.yaml` 建立 run，记录实际节点、版本、Git dirty 状态、预置模型路径和 outcome；不要先填计划值冒充实测。
4. 复用已在 Spark 上 smoke 的 digest-pinned vLLM image 与小模型配置。

## M3m.1 — 两台 Spark 作为 GPU Worker

1. 按选定路径加入两台 Spark；保留 join 前置检查、命令退出码、`kubectl get nodes -o wide`、node conditions 和相关 events。
2. 两节点都必须为 `Ready`，且 OS/arch、逻辑标签和 taint 与实际调度意图一致，才进入 GPU 接入。
3. Minimal 的复现范围是“已满足主机前置条件后可重复安装/apply”；不把本步写成完整 M3 的 clean-machine rebuild。

## M3m.2 — GPU Runtime、Device Plugin 与调度

1. 在每台 Worker 配置 NVIDIA Container Runtime 与 Kubernetes 使用的 container runtime；保留实际配置、重启结果和 runtime 状态。
2. 安装一个固定版本的 NVIDIA Device Plugin。只有 plugin Pod 在两节点运行、日志无阻塞错误，且每个节点的 Capacity/Allocatable 都出现非零 `nvidia.com/gpu`，才继续。
3. 在两台 Worker 上各顺序运行一次 CUDA smoke Pod；Pod spec 同时设置 `requests` 与 `limits` 的 `nvidia.com/gpu: 1`，保留 scheduling event、分配节点、容器内 GPU inventory 和真实 CUDA 运算结果。
  - 显式申明运行节点，e.g. `kubectl run --overrides='{"spec":{"nodeSelector":{"ai-infra/node-id": "spark-a"}}}' ...`，避免调度到非预期节点。
4. Docker smoke 通过但任一 Kubernetes GPU Pod 失败时，分类为 Kubernetes 接入缺口并停在本步；不回退成 host/Docker 结果继续。

## M3m.3 — vLLM Deployment 与 Probe 分责

1. 建立单副本 Deployment 和 ClusterIP Service。Pod 显式申请一张 GPU，使用冻结的 image/model/args；Minimal 复用已存在的模型资产，不在这里引入 PVC 或下载系统。
2. `startupProbe` 负责等待模型加载和 engine 初始化；成功前抑制 readiness/liveness。预算由实测冷启动时间加余量校准，不预写无数据支撑的秒数。
3. `readinessProbe` 只表示是否接收 Service 流量；失败应摘除 endpoint，不触发重启。先在 pinned vLLM runtime 上 smoke 实际 endpoint。
4. `livenessProbe` 只判断启动后的进程是否陷入不可恢复状态；不得承担慢加载计时，也不得执行生成请求。
5. 保留 Pod conditions、probe events、EndpointSlice、restart count 和 server log 的同一时间线。加载期必须看到 `startupProbe` 从失败到成功、Pod Ready/EndpointSlice 从未就绪到就绪，且 restart count 不增加。

## M3m.4 — 一次实测、重放与判定

1. 直接调用 `serving/vllm/benchmark/benchmark_client.py` 指向 `kubectl port-forward service/vllm ...`，沿用现有 C1、4-request streaming smoke；不调用 Docker lifecycle wrapper。保留 request JSONL、HTTP/finish outcome、Pod/Service snapshot 和 server log。
2. `derived/summary` 只报告本次 run 的 scheduling-to-Ready、成功/失败/timeout 请求数、Pod restart 数和实际调度节点。该结果是 functional smoke，不报告 p95、capacity 或性能收益。
3. 按部署说明从已满足前置条件的集群再次 apply，并重放 GPU resource 检查与一个 vLLM 请求；第二次重放使用独立 run ID。
4. Minimal 只有在以下事实同时有证据时结束：两台 Worker Ready 且发布 GPU resource；每节点 GPU Pod 通过；vLLM Pod 以 GPU request 被调度并进入 Ready；加载期无 probe restart；功能请求成功；说明可重放。
5. 部署说明保留 exact prerequisites、固定版本、安装/apply/验证/清理命令、预期观察点和已知限制；实测数字及事实分级只写入 M3 review。

## 不做

不做破坏性的从零重建、发行版/CNI 对比、HA control plane、GPU Operator、GPU sharing/MIG；不做流式优雅终止、PVC 冷热启动、Helm/Kustomize、多 adapter 或裸机性能对照；不做 Ingress/TLS、Prometheus/SLO、autoscaling、rolling update、故障演练、controller 或参数调优。这些要么属于 [M3 Complete](m3-plan-complete.md)，要么属于后续 Milestone。
