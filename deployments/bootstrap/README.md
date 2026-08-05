# Bootstrap Verification Scripts

These scripts divide M0 qualification into four non-overlapping layers:

1. `verify-host.sh` — OS/architecture, CPU/memory/storage, time sync, NVIDIA driver/GPU, CUDA toolkit, optional host CUDA execution.
2. `verify-container-runtime.sh` — Docker daemon access, runtime configuration, plain container lifecycle, Buildx/toolkit inventory.
3. `verify-gpu-container.sh` — GPU passthrough plus a real PyTorch CUDA matrix multiplication in a pinned image.
4. `verify-network.sh` — management/data interface state, routes, peer reachability, NIC counters, RDMA mapping, optional iperf3.

All scripts are read-only except for pulling/running/removing test containers and writing evidence under `OUTPUT_ROOT`. Set one shared `RUN_ID` before invoking all four scripts to place their evidence under the same run identifier.
Warnings do not make a script fail; failed required checks produce exit code `1`.

## Examples

```bash
chmod +x deployments/bootstrap/*.sh
export RUN_ID=20260805-m0-recheck

nvcc -O2 -std=c++17 \
  deployments/bootstrap/platform-qualification/cuda-smoke/vector_add.cu \
  -o deployments/bootstrap/platform-qualification/cuda-smoke/vector_add

CUDA_SMOKE_BIN=./deployments/bootstrap/platform-qualification/cuda-smoke/vector_add \
  deployments/bootstrap/verify-host.sh

RUNTIME_SMOKE_IMAGE=hello-world:latest \
  deployments/bootstrap/verify-container-runtime.sh

GPU_IMAGE='nvcr.io/nvidia/pytorch@sha256:<digest>' \
  deployments/bootstrap/verify-gpu-container.sh

MGMT_IFACE=enP7s7 \
DATA_IFACE=enp1s0f1np1 \
PEER_MGMT_IP=192.0.2.11 \
PEER_DATA_IP=198.51.100.11 \
REQUIRE_RDMA=1 \
RUN_IPERF=0 \
  deployments/bootstrap/verify-network.sh
```

`hello-world` is only a container lifecycle probe in M0. Digest pinning is
optional evidence hardening and its mutable `latest` identity is non-blocking.

For a bandwidth run, start `iperf3 -s` on the peer and set `RUN_IPERF=1` on the client.
NCCL `all_reduce`/`all_gather` should remain a separate experiment because successful NCCL execution and confirmed RDMA transport are different claims.
