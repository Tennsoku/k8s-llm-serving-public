# DGX Spark Inventory

## Qualification Scope

This is the sanitized M0 inventory for the two-node Grace Blackwell testbed.
Only stable logical labels are public. Physical identity, ownership, site,
hostnames, serial numbers, MAC addresses, and exact IP addresses are outside the
public M0 scope.

| Field | Spark A | Spark B |
|---|---|---|
| Logical label | `spark-a` | `spark-b` |
| Architecture | AArch64 | AArch64 |
| CPU | 20 cores: Cortex-X925 + Cortex-A725 | 20 cores: Cortex-X925 + Cortex-A725 |
| GPU | NVIDIA GB10 | NVIDIA GB10 |
| OS | Ubuntu 24.04.4 LTS | Ubuntu 24.04.4 LTS |
| Kernel | `6.17.0-1029-nvidia` | `6.17.0-1029-nvidia` |
| OS-visible unified memory | approximately 121 GiB | approximately 121 GiB |
| NVIDIA driver | `580.173.02` | `580.173.02` |
| Host CUDA toolkit | 13.0 / NVCC 13.0.88 | 13.0 / NVCC 13.0.88 |
| Docker | 29.2.1 | 29.2.1 |
| NVIDIA Container Toolkit | 1.19.1 | 1.19.1 |
| M0 host CUDA smoke | Pass | Pass |
| M0 GPU-container smoke | Pass | Pass |
| M0 bootstrap qualification replay | Pass from captured commit with clean tracked worktree | Pass from captured commit with clean tracked worktree |

Both bootstrap replay contexts record commit
`784506a1b72727de0dcc774eabcbf9f623847438`, `git_dirty=false`, and exit `0`.
The node-inventory, host-CUDA, GPU-container, vLLM, TCP, and NCCL contexts record
`git_dirty=true` after generated outputs or build products existed. That does
not change the observed platform configuration and is not a clean-machine
provisioning claim. The commit above is a pre-public private-history capture ID;
after the reviewed public-history squash, it may intentionally no longer resolve
in the public repository.

## Hardware Summary

| Field | Observed value |
|---|---|
| Architecture | AArch64 |
| CPU | 20-core Arm CPU: 10× Cortex-X925 + 10× Cortex-A725 |
| GPU / Superchip | NVIDIA GB10 Grace Blackwell Superchip / NVIDIA Blackwell GPU |
| OS-visible unified memory | approximately 121 GiB |

Physical serials and a standalone DGX OS marker are intentionally not M0 exit
criteria. The public qualification identity consists of the logical node label
and the observed Ubuntu, kernel, driver, CUDA, runtime, and hardware profile.

## Network Interface Summary

| Interface | PCI address | Canonical device / driver evidence | Firmware | Observed state | Public role |
|---|---|---|---|---|---|
| `enP7s7` | `0007:01:00.0` | Realtek Ethernet controller, `10ec:8127`; driver not retained | not retained | Carrier/up; speed not retained | Management / LAN |
| `enp1s0f0np0` | `0000:01:00.0` | `mlx5_core` | `28.45.4028` | Down, no cable | Unused ConnectX-7 port |
| `enp1s0f1np1` | `0000:01:00.1` | `mlx5_core` | `28.45.4028` | Up, 200 Gb/s, IPv4 link-local | Data/OOB path and RoCE HCA |
| `enP2p1s0f0np0` | `0002:01:00.0` | `mlx5_core` | `28.45.4028` | Down, no cable | Unused ConnectX-7 port |
| `enP2p1s0f1np1` | `0002:01:00.1` | `mlx5_core` | `28.45.4028` | Up, 200 Gb/s, no host IP | Second RoCE HCA used by NCCL |

Both nodes expose the same interface roles. Exact addresses, MACs, and RDMA GUIDs are kept
only in the ignored private companion and private evidence bundle.

## CUDA / GPU

| Field | Value |
|---|---|
| NVIDIA driver | `580.173.02` |
| Driver-supported CUDA API | `13.0` |
| CUDA Toolkit | 13.0 |
| NVCC build | 13.0.88 |
| CUDA installation | `/usr/local/cuda` |
| CUDA target | `sbsa-linux` |
| Host architecture | AArch64 |
| CUDA Runtime libraries | CUDA 13 primary; CUDA 12 runtime also present |
| cuDNN | Not installed as a host baseline; container PyTorch smoke passed |
| NCCL | Locally built NCCL `2.28.9+cuda13.0` used for the distributed M0 baseline |

## Current Qualification Notes

- Both logical nodes completed the M0 functional qualification checks.
- `enP7s7` is the management/LAN interface on each node.
- `enp1s0f1np1` is the IP-configured high-speed data/OOB interface on each node.
- `enP2p1s0f1np1` is link-up without a host IP on each node. NCCL enumerated
  both RoCE HCAs and used `NET/IB/0` and `NET/IB/1`.
- The high-speed links negotiated at 200 Gb/s with MTU 1500. TCP and NCCL
  baselines are documented separately.

## Known Platform Limitations

- `nvidia-smi` does not provide supported framebuffer-memory telemetry on the
  GB10 unified-memory architecture.
- GPU PCIe bandwidth reporting may not represent the internal GB10 topology.
- Host Python intentionally does not provide PyTorch/vLLM in the container-first baseline.
- GPU Operator and Kubernetes Device Plugin behavior was not exercised in M0;
  that compatibility boundary is deferred to M2.

## Public Evidence

After the publication gate is completed, the sanitized bundle is located at:

- `benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/`
- [`network-topology.md`](network-topology.md)
- [`qualification-notes.md`](qualification-notes.md)
