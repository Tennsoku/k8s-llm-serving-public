# M3 Minimal Review — Kubernetes GPU Serving 最小闭环

## 结论

**Observed Fact**：Spark A Control Plane 和 Spark B Worker 均为 `Ready`；Pod→Pod、Pod→Service、DNS+Service 的双向 smoke 全部 exit 0。两个节点都发布了 1 个 `nvidia.com/gpu`，各自的 CUDA compute Pod 均以 exit 0 完成。显式申请 GPU 的单副本 vLLM 被调度到 Spark B，并从 `0/1` 进入 `1/1 Ready`，restart count 始终为 0。经 Service 发出的 4 个 streaming requests 均返回 HTTP 200，没有失败或超时。

**Interpretation**：这些结果说明当前 DGX Spark / ARM64 / Kubernetes / NVIDIA runtime / vLLM 组合已经跑通最小端到端功能路径，足以判定 M3 Minimal checkpoint 通过。完整 M3 待完成，也不证明 production readiness。

## 支撑证据

| Checkpoint | Observed Fact | 直接证据 |
|---|---|---|
| 集群与网络 | Spark A control plane、Spark B Worker 均 `Ready`；Pod→Pod、Pod→Service、DNS+Service 双向 exit 0 | `system capture(private)` · `connectivity capture(private)` |
| GPU 接入 | `RuntimeClass` 已创建，Device Plugin 2/2 Ready；两节点 Capacity/Allocatable 均为 1 GPU；两份 CUDA Pod 均 Succeeded、exit 0，矩阵结果均为有限值 | `GPU capture(private)` · [Spark A Pod](../../control-plane/gpu-test-pod-cp.yaml) · [Spark B Pod](../../control-plane/gpu-test-pod-worker.yaml) |
| vLLM 与 probes | Deployment 显式申请 1 GPU 并固定到 Worker；Pod 从 `0/1` 进入 `1/1`，restart 为 0，Ready 后 EndpointSlice 有 endpoint | `rollout capture(private)` · [Deployment / Service](../../control-plane/deploy-vllm.yaml) |
| 功能 smoke | case outcome 为 4/4 success；四条 request 均 `success=true`、HTTP 200、`timeout=false` | `case events(private)` · `requests(private)` |

## 范围、偏差与执行缺口

- 这组 4-request smoke 只证明 streaming API 功能路径完整，不用于 latency、throughput、capacity 或输出语义正确性结论。
- Probe 证据只覆盖正常加载路径中的 `0/1 → 1/1` 与 restart 0；未执行 readiness/liveness 异常注入，也未直接捕获 Ready 前的 EndpointSlice。
- Minimal plan 要求保留 control-plane taint，但 capture 显示两节点均为 `TAINTS <none>`。相关 workload 都通过 `nodeSelector` 明确指定了节点，因此这不影响其他检查项的结果；但本轮不能据此声称验证过 taint/toleration 调度隔离。
- Clean-machine rebuild、长期稳定性、Kubernetes 性能开销、优雅终止、PVC cold/warm、multi-adapter 与 M1 裸机对照均未执行；这些是完整 M3 的执行缺口，不是 Unknown。
- Command/status captures 是 gitignored private evidence；公开仓库不包含这些证据，外部读者无法只凭公开内容独立复核。这是 evidence publication gap，不改变本地 raw 对上述事实的支持。最终结论会在 M3 review 中给出，并提供一定范围的公开 workflow evidence。

范围见 [M3 Minimal plan](../milestone-plan/m3-plan-minimal.md)；完整 M3 Exit Criteria 见 [Roadmap](../Roadmap.md#5-m3--kubernetes-基础与-gpu-workloadw3w550-h)；进度只见 [current-status](../context/current-status.md)。
