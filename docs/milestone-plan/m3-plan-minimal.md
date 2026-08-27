# M3 Minimal — Kubernetes GPU Serving 最小闭环

> 本文只负责 M3 Minimal 的范围、执行顺序与 checkpoint。完整 M3 仍见
> [Roadmap M3](../Roadmap.md#5-m3--kubernetes-基础与-gpu-workloadw3w550-h)，
> 当前进度见 [current-status](../context/current-status.md)。预算 ≤ 150 行。

## 原则

M3 从这里建立一条新的 Kubernetes 执行路径。它不继承 M1/M2 的 Docker benchmark
lifecycle、`run.yaml`、raw/derived 目录或发布 contract。现有 benchmark client
只能作为四请求功能调用器复用，不能因此把整套 benchmark artifact 管线带入 M3。

创建任何产出前先回答“谁会实际读取它”。没有明确的人或程序消费者，就不创建。
私有信息只需在 ignored private operator note 中保留，不为未来可能的公开发布预建结构。

## 目标与边界

快速验证一条窄纵向闭环：沿用 [Roadmap M3](../Roadmap.md#5-m3--kubernetes-基础与-gpu-workloadw3w550-h)
的两节点拓扑，Spark A 承担 single control plane，Spark B 是 worker-only；两节点分别完成
GPU compute Pod，并让一个显式申请 GPU 的单副本 vLLM Deployment 进入 Ready、经历正确的
probe 状态转换并完成一次四请求功能实测。

该 checkpoint 只证明当前组合可用，不证明 clean-machine rebuild、长期稳定性、容量、
Kubernetes 性能开销或生产就绪。M0 的 Docker GPU smoke 仅作排障参考，不能替代
Kubernetes runtime、Device Plugin、extended resource 或 Pod 内 CUDA 的实测。

## 固定执行路径

- Spark A 执行 `kubeadm init`，仅 Spark B 执行 `kubeadm join`；single control plane，不做 HA。
- Spark A 保留默认 control-plane taint；只有显式指定到该节点的 GPU workload 添加 toleration。
- `kubeadm` + system `containerd` + 一种 CNI；不做发行版或 CNI 对比。
- NVIDIA runtime handler + `RuntimeClass` + static Device Plugin；不引入 GPU Operator。
- 单副本 Deployment 固定到 Spark B，配合 ClusterIP Service + `kubectl port-forward`；复用已有模型资产。

具体私有地址、实际版本、执行命令和当次结果只写入本地忽略的
`m3-step-minimal.private.md`。

## 执行顺序

1. **网络与集群**：固定 stable endpoint、API/node/CNI interface 与不重叠 CIDR，确认
   Spark A ↔ Spark B 必要双向路径；Spark A init、安装一种 CNI、Spark B join，两个 Node
   `Ready`，CoreDNS 和跨节点 Pod 网络正常。
2. **GPU 接入**：配置 NVIDIA runtime、RuntimeClass 和 Device Plugin；两个 GPU Node
   都发布非零 `nvidia.com/gpu`，并各运行一次真实 CUDA compute Pod。
3. **vLLM 与 probes**：apply 单副本 Deployment/Service；`startupProbe` 覆盖加载，
   readiness 控制流量资格，liveness 只处理启动后的异常；加载期不得发生 probe restart。
4. **功能实测**：port-forward Service，复用现有 client 发送四个 streaming requests，
   记录成功、失败和 timeout 数后结束 Minimal；不增加 replay run。

前一步不成立就停止后续执行，记录实际错误和阻塞点。修正后继续同一 operator note，
不为每次尝试创建新的 evidence package。

## 产出与消费者

| 产出 | 真实消费者 | 创建时机 |
|---|---|---|
| `m3-step-minimal.private.md` | 当前 operator | 执行前填写，执行中更新 |
| 最小 manifests + 部署 README | 重放部署的人 | 路径首次跑通后，经单独授权创建 |
| `docs/reviews/m3-minimal-review.md` | reviewer / 项目结论 | Minimal 结束后 |

默认不创建 `artifacts/private/m3/`、`run.yaml`、raw/derived 分层、manifest index、
sanitized public copy 或 release bundle。将来若出现真实发布需求，再按实际输出设计最小路径。

## Checkpoint

- Spark A control plane 与 Spark B Worker 都是 `Ready`，基础 Pod 网络和 DNS 正常。
- 两节点都发布 GPU extended resource，且各自的 CUDA compute Pod exit 0。
- vLLM Pod 因显式 GPU request 被调度并进入 Ready；加载期 restart count 不增加。
- startup/readiness/liveness 的职责能从 manifest 和实际状态转换解释。
- 四个 streaming requests 有明确 outcome；任一失败都如实记录，checkpoint 不判通过。
- 成功路径足以反写一份短部署 README；不要求本阶段实际 clean-machine rebuild。

## 不做

不做 HA control plane、第二发行版/CNI、GPU Operator、MIG/sharing、PVC、Ingress/TLS、
性能对照、优雅终止、multi-adapter、autoscaling、故障演练或 public evidence workflow。
