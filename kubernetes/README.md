# Kubernetes

本目录保存 M3 的 Kubernetes 核心部署输入，以及不进入默认重放路径的探索性
manifest。M3 范围与验收项见 [Roadmap](../docs/Roadmap.md#5-m3--kubernetes-基础与-gpu-workloadw3w550-h)，
当前进度见 [current status](../docs/context/current-status.md)，实验结论与限制见
[M3 reviews](../docs/reviews/)。

## 核心路径

这些文件按职责形成一条路径：

1. `kubeadm-init-spark.yaml`：初始化两节点拓扑中的 control plane。
2. `kube-flannel-spark.yaml`：安装当前固定的 CNI。
3. `nvidia-runtime-class.yaml` 与 `nvidia-device-plugin-v0.20.0.yaml`：接入 GPU extended resource。
4. `gpu-test-pod-cp.yaml` 与 `gpu-test-pod-worker.yaml`：分别验证两节点 Pod 内 CUDA compute。
5. `deploy-vllm.yaml`：部署单副本 vLLM Deployment 与 ClusterIP Service。

这些 manifest 含 testbed-specific 的节点、网络和模型路径输入，执行前必须按目标环境核对。
本目录不是可直接递归 apply 的 bundle：`kubeadm` 配置不是 Kubernetes API object，且
`experiments/` 明确不属于默认路径；从零重建的范围与验收以 Roadmap M3.1 为准。

## 探索性 manifest

[`experiments/`](experiments/) 中的文件不属于 M3 Exit Criteria，也不进入上述默认路径：

- `gpu-time-slicing-config.yaml` 是尚未接入主 Device Plugin 的配置输入。
- `rdma-shared-device-plugin.yaml` 与 `rdma-debug-pods.yaml` 用于手工检查 RDMA resource 暴露与 Pod 调试；debug Pod 本身不验证 RDMA data path。

实验数据不写入本目录；private run 的目录约定见
[Experiment Repository Convention](../docs/experiments/README.md)。
