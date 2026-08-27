# WSL Control Plane Environment — Superseded Candidate

> **决策：未采用** · 环境快照日期：2026-08-26

本文保留曾评估的 WSL control-plane candidate 环境快照；它不再是 M3 当前执行路径。
当前拓扑与执行边界见 [Roadmap M3](../Roadmap.md#5-m3--kubernetes-基础与-gpu-workloadw3w550-h)
和 [M3 Minimal plan](../milestone-plan/m3-plan-minimal.md)。

## Required Parameters

| Parameter | Observed value | Candidate evaluation context |
|---|---|---|
| Windows build | `26100.1.amd64fre.ge_release.240331-1435` | WSL networking |
| WSL version | `2.7.3.0` | 固定 WSL runtime |
| Distribution | Ubuntu 24.04 | control-plane userspace |
| Architecture / kernel | `x86_64` / `6.6.114.1-1` | Kubernetes 与 CNI 兼容性 |
| Init system | systemd | kubelet、containerd service 管理 |
| Networking mode | mirrored | Worker 必须直接访问 API endpoint |
| Stable endpoint method | spark-cluster.internal:6443 | 内部公有 DNS |
| CPU / memory allocation | `processors=16 | memory_bytes=24752762880 | swap_bytes=6442450944` | control-plane 与 model-free system Pods 资源 |
| Swap state | Enabled, 6291456 kB | 满足选定 kubelet 配置的前置条件 |

这些参数不再构成 M3 init 前置条件；不要补写 WSL endpoint、firewall 或 CIDR。当前执行值
只记录在 `m3-step-minimal.private.md`。

本文不保存 credential、kubeconfig、证书、bootstrap token、MAC 或个人路径，也不预建
artifact/publication 路径。

## Mirrored localhost routing

Source Issue: [Mirrored mode: 127.0.0.1 policy-routing breaks DNS services and nftables compatibility](https://github.com/microsoft/WSL/issues/14063)

在 mirrored networking 下，WSL 会把 TCP/UDP loopback 流量优先送入专用的 policy-routing
table。`ignoredPorts` 虽允许 Linux 进程绑定被 Windows 保留的端口，但在当前实测版本中，
这些端口可能出现 `ss` 显示 `LISTEN`、同一 distro 内连接 `127.0.0.1` 却被拒绝的状态。
这会直接破坏 kubeadm/kubelet 及 control-plane static Pod 对以下本地端点的探测：

- `10248`：kubelet healthz
- `10249`、`10256`：kube-proxy metrics/healthz
- `10250`：kubelet API
- `10257`：kube-controller-manager
- `10259`：kube-scheduler

仓库提供一个限于上述六个 TCP 端口的 systemd workaround。它不会改变 `6443`、
`2379`、`2380` 或 VS Code 使用的随机 localhost 端口。

安装：

```bash
sudo install -Dm0755 \
  deployments/bootstrap/wsl/wsl-k8s-loopback-routes \
  /usr/local/sbin/wsl-k8s-loopback-routes

sudo install -Dm0644 \
  deployments/bootstrap/wsl/wsl-k8s-loopback-routes.service \
  /etc/systemd/system/wsl-k8s-loopback-routes.service

sudo install -Dm0644 \
  deployments/bootstrap/wsl/kubelet-wsl-loopback.conf \
  /etc/systemd/system/kubelet.service.d/20-wsl-k8s-loopback-routes.conf

sudo systemctl daemon-reload
sudo systemd-analyze verify \
  /etc/systemd/system/wsl-k8s-loopback-routes.service
sudo systemctl enable --now wsl-k8s-loopback-routes.service
sudo systemctl restart kubelet.service
```

该 service 会移除诊断期间使用的聚合临时规则，改为六条精确规则。kubelet drop-in
建立 `Requires` 和 `After` 关系，保证普通启动和手工重启 kubelet 时规则都已就绪。

验证：

```bash
systemctl is-active wsl-k8s-loopback-routes.service kubelet.service
systemctl show kubelet.service -p Requires -p After

for port in 10248 10249 10250 10256 10257 10259; do
  ip -4 route get 127.0.0.1 \
    ipproto tcp sport 40000 dport "$port"
done

curl -fsS http://127.0.0.1:10248/healthz
curl -kfsS https://127.0.0.1:10257/healthz
curl -kfsS https://127.0.0.1:10259/livez
kubectl get nodes
kubectl get pods -A
```

每条 `ip route get` 应显示 `dev lo table local`，三个健康端点应返回 `ok`。首次安装
验证完成后，还必须从 Windows 执行一次 `wsl --shutdown`，重新进入 Ubuntu 并重复上述
检查，确认启动顺序和持久化行为。

移除：

```bash
sudo systemctl disable --now wsl-k8s-loopback-routes.service
sudo rm -f \
  /etc/systemd/system/kubelet.service.d/20-wsl-k8s-loopback-routes.conf \
  /etc/systemd/system/wsl-k8s-loopback-routes.service \
  /usr/local/sbin/wsl-k8s-loopback-routes
sudo systemctl daemon-reload
```

这是针对当前 WSL mirrored policy-routing 行为的本地兼容层，不是 Kubernetes 的通用
要求。升级 WSL 后应重新测试；若上游修复，应移除此 workaround。
