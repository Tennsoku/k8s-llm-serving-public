# M3 Review — Kubernetes GPU Workload 生命周期

## 结论

**Observed Fact**：两节点GPU workload、四个LoRA共池、probe异常、PVC冷/热启动与在途流终止均有直接证据；单副本Docker/K8s请求指标可复算。
**Interpretation**：证据支持本次集群重建、GPU serving、probe职责、缓存启动与固定负载下的流式终止行为；Docker/K8s结果按两套部署路径比较解释。验收范围见 [Roadmap M3](../Roadmap.md#5-m3--kubernetes-基础与-gpu-workload原预算-50-h)，进度只见 [current-status](../context/current-status.md)。

## 关键结果与证据

下表结果为 **Observed Fact**；每份derived仅保留关键数字、必要限制和Tier B原始路径。

| 验收问题 | 结果 | derived |
|---|---|---|
| 集群能否重建、两节点能否运行GPU workload | 既有主机前置下reset/init/join后Ready；两个显式GPU Pod完成CUDA运算、exit=0 | [cluster][cluster] |
| Readiness与liveness是否区分职责 | 故障readiness阻止新Pod入池、restart=0；6次liveness失败后同UID重启并重新Ready | [readiness][readiness] · [liveness][liveness] |
| PVC缓存冷/热有何差异 | 创建→Ready为cold 221s、warm 170s；cold复制加校验，warm跳过 | [cold][cold] · [warm][warm] |
| 删除Pod时在途流是否完整 | baseline 1/1截断；candidate 1/1完整结束、2048 output tokens、container exit=0 | [termination][termination] |
| 多adapter能否共池并逐请求选模 | 4个真实LoRA；32/32 HTTP与选模通过，角色正确30/32 | [adapters][adapters] |
| 单副本相对裸机路径有何差异 | 两侧各64/64 measured成功；Docker/K8s分别122.773/123.614 output tok/s | [comparison][comparison] · [Docker summary][docker] |

## 必要边界

- 重建过程复用了既有OS/驱动/runtime/镜像，并不是裸机安装或HA证明；快照有系统组件因资源占用等待超时重启，但未有证据明确记录各次原因。
- Probe以故障HTTP path验证机制；readiness 404时新Pod保持NotReady、restart=0是预期结果，证明未通过readiness时不入池。未测试同一健康Pod转为NotReady；在采集时缺少正式请求验证，后在同一pod补请求时仍缺同期Pod UID。仅作为对 readiness 行为的间接验证，不作为强证据。
- Cold是空目标PVC，不含下载；page cache未控制，51s是本次观测差。缺cgroup曲线、HTTP400客户端capture及watch退出码归属问题见 [warm metadata][warm-run]。
- 终止每侧仅1请求，grace/preStop共同改变、删除时点不同；未测删除期间新请求。成功 [patch](../../kubernetes/m3-patch/grace-termination-patch.json) 未接入 [默认Deployment](../../kubernetes/deploy-vllm.yaml)，结果适用于该实验配置，不声明默认Deployment具有相同行为。
- Kustomization 实操中 Adapter 容器因等待 GPU Resource 释放，重启计数为3，最近一次退出码为1；在手动关闭资源占用后恢复正常。不构成阻塞项。HTTP/选模成功不代表角色语义全通过。
- Docker本机loopback与K8s跨节点ClusterIP的client位置、网络/runtime/IPC/probes不同；K8s数据是由 control plane 遥测采集。在本地 CX7 接口单线缆互联的情况下，我认为开销可以近似忽略，因此不作阻塞项处理。但是因此在本实验中，单次C8只支持整套路径比较，不隔离K8s开销或证明稳定容量。

## 证据读取

Git内保留metadata与derived；完整raw（含失败、timeout、restart和非零退出）按 [M3留存约定](../experiments/evidence-retention.md#23-失败证据不采样) 位于单一Tier B archive。
Derived中的 `raw/...` 均指归档内同名run，不能从Git副本独立重算。Release发布进度见 [current-status](../context/current-status.md)，不把本地候选目录当成已发布asset。

Probe/PVC可用 [summarize-m3-lifecycle.py](../../scripts/experiments/summarize-m3-lifecycle.py) 从解压目录重算；warm需同时解压配对cold。其余复核入口写在对应derived中。

```bash
python3 scripts/experiments/summarize-m3-lifecycle.py <tier-b-root>/20260926-m3-probe-readiness-r01
```

## 验收与公开缺口

技术结果及可重算性有直接依据；上述观察范围不作为新增实验门槛。

[cluster]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260915-m3-cluster-r01/derived/cluster-replay-review.md
[readiness]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260926-m3-probe-readiness-r01/derived/probe-review.md
[liveness]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260926-m3-probe-liveness-r01/derived/probe-review.md
[cold]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260926-m3-pvc-cold-r01/derived/startup-summary.md
[warm]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260926-m3-pvc-warm-r02/derived/startup-comparison.md
[warm-run]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260926-m3-pvc-warm-r02/run.yaml
[termination]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260927-m3-graceful-termination-r02/derived/termination-review.md
[adapters]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260920-m3-kustomization-r01/derived/adapter-summary.md
[comparison]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260927-m3-k8s-comp-r01/derived/comparison-summary.md
[docker]: ../../benchmarks/raw-results/m3-k8s-gpu-workload/20260927-m3-docker-comp-r01/derived/summary.json
