# M3 集群重建与双节点 GPU 重放

**Observed Fact**：两节点完成 `kubeadm reset`，控制面 init、worker join、Flannel 安装后均 Ready；两侧显式申请 GPU 的 Pod 均完成 CUDA 矩阵运算并 exit 0。
**Interpretation**：结果支持在记录的主机前置条件下恢复集群及双节点 GPU 执行能力。

## 重建与 GPU 末态（Observed Fact）

| 步骤 | 直接观察 |
|---|---|
| Reset / init / join | 两侧 reset、控制面 init、worker join 的命令退出码均为 0 |
| 集群与 CNI | 两节点 Ready；Flannel rollout 完成，系统 Pod 快照均 1/1 Running |
| NVIDIA 接入 | nvidia RuntimeClass 与 Device Plugin DaemonSet 创建成功 |
| GPU 请求与实际分配 | 两侧 requests=limits=1，allocatedResources=1，设备 health=Healthy |
| 容器内运算 | 两侧 NVIDIA GB10，CUDA FP16 2048×2048 matmul，result_finite=true |
| GPU Pod 退出 | 两侧 Succeeded / Completed，exitCode=0，restartCount=0 |

GPU Pod 使用 `runtimeClassName: nvidia`、分别指向两节点的 nodeSelector、control-plane toleration 和 `restartPolicy: Never`；事件与实际 nodeName 对应。

## 原始依据与复核

以下为 Tier B archive 解压根目录内的相对路径；每个命令 capture 同时保留 command/stdout/stderr/exit-code。

- Reset：`20260915-m3-cluster-r01/raw/kubeadm-reset/` 与 `20260915-m3-cluster-r01/raw/spark-b/kubeadm-reset/`；init/join：`20260915-m3-cluster-r01/raw/kubeadm-init/` 与 `20260915-m3-cluster-r01/raw/spark-b/kubeadm-join/`。
- CNI / NVIDIA：`20260915-m3-cluster-r01/raw/apply-flannel/`、`20260915-m3-cluster-r01/raw/apply-rollout/`、`20260915-m3-cluster-r01/raw/apply-nv-runtimec/`、`20260915-m3-cluster-r01/raw/apply-nv-dev/`。
- 节点 / 系统 Pod：`20260915-m3-cluster-r01/raw/get-nodes/stdout.log`、`20260915-m3-cluster-r01/raw/get-pods-A/stdout.log`。
- GPU A / B：`20260915-m3-cluster-r01/raw/gpu-replay/gpu-matmul-test-spark-a-state/stdout.log`、`20260915-m3-cluster-r01/raw/gpu-replay/gpu-matmul-test-spark-b-state/stdout.log`；同目录树对应 `-input`、`-events`、`-log` capture。

从 input/state 的 spec 复核 GPU request 和 runtime；以 Pod UID 对齐 events，读取 state 的 allocation、退出码与重启数。去掉 log 每行时间戳后解析 JSON，核对 CUDA 运算结果。

## 范围与限制

- 复用既有 OS、驱动、containerd/NVIDIA runtime 与镜像；reset 不自动清空 CNI 配置、网络规则和 kubeconfig，未记录这些项目另行清空，不能表述为裸机安装。
- 未捕获 Node Capacity/Allocatable、Device Plugin Running 的专门快照及 bootstrap/CNI/plugin 输入内容；ARM64/GB10 兼容失败与解法没有独立记录，这些不影响实际GPU调度/运算结果；公开材料的用途是复核本次结果。
- 系统快照保留 etcd/apiserver restart=11、controller-manager/scheduler restart=3，缺少归因时间线；GPU Pod 的零重启不代表全组件零重启或长期稳定性。
- `worker-end` 早于后补 GPU replay，不据此计算总重建耗时；此 run 不覆盖应用网络请求、vLLM 生命周期、精度或性能评测。
