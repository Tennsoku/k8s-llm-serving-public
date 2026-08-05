# M0 Software Compatibility Matrix

Status is scoped to M0 qualification. “Pass” means the stated smoke test or distributed test passed; it does not imply production support or performance qualification.

| Component | Qualified version / image | Scope | M0 status | Evidence | Compatibility boundary |
|---|---|---|---|---|---|
| Ubuntu / kernel | Ubuntu 24.04.4 LTS / `6.17.0-1029-nvidia` | Both nodes, AArch64 | Pass | Node `platform.txt` | DGX Spark-specific observed baseline; a standalone DGX OS marker is intentionally not an M0 criterion |
| Host Python | 3.12.3 | Both nodes | Pass for inventory | Node `runtime-stack.txt` | Host PyTorch/vLLM are intentionally absent in the container-first baseline |
| NVIDIA driver | `580.173.02` | Both nodes, NVIDIA GB10 | Pass | Node `gpu-cuda.txt` | `nvidia-smi` framebuffer-memory fields are unavailable on GB10 unified memory |
| Docker Engine | 29.2.1 | Both nodes | Pass | Node `runtime-stack.txt`; bootstrap replay | Plain-container lifecycle passed |
| NVIDIA Container Toolkit | 1.19.1 | Both nodes | Pass | Node `runtime-stack.txt`; bootstrap replay | GPU passthrough validated with Docker, not Kubernetes |
| Host CUDA Toolkit | 13.0 / NVCC 13.0.88 | Both nodes | Pass | `tests/cuda-host/` | Vector-add compile and execution passed |
| NGC PyTorch | `26.07-py3`, PyTorch `2.13.0a0+9186a08b2c.nv26.07`, CUDA 13.3 | Digest-pinned ARM64 container on both nodes | Pass | `tests/gpu-container/` | Uses CUDA forward compatibility over kernel driver 580.173.02 |
| cuDNN | Bundled in NGC PyTorch image | Container | Not independently versioned | NGC image identity | Exact cuDNN version was not retained in the final outer capture |
| vLLM | NGC digest `sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2`; runtime reports `vllm-0.24.0+092c4842.dev-8f72c57e` | Qwen3-0.6B functional smoke | Functional pass / harness partial | `tests/vllm-smoke/` | Both commands use the digest and both logs show HTTP 200; Spark A has response JSON; outer wrappers exited 141 |
| NCCL | Locally built `2.28.9+cuda13.0` | Two nodes, one GB10 per rank | Pass | Distributed NCCL `stdout.log` | Distinct from the container-bundled NCCL; the bundled version was not re-captured in the final critical bundle |
| nccl-tests | 2.19.6 | `all_reduce` and `all_gather`, 8 B–512 MiB | Pass | Distributed NCCL `stdout.log` | M0 is a functional baseline, not a tuning result |
| Active MPI | `mpirun` reports Open MPI `5.0.10rc2` | Two-node NCCL launcher | Pass with provenance caveat | Both node `runtime-stack.txt` | The intended stack is HPC-X-aligned, but exact executable/library paths were not retained; distro Open MPI 4.1.6 packages are also installed |
| RDMA userspace | rdma-core 50.0; `libmlx5.so.1.24.50.0` | mlx5 RoCE | Basic RDMA pass / advanced features partial | Node `network-rdma.txt` and NCCL logs | Userspace `libmlx5` lacks the `MLX5_1.25` symbols queried by NCCL |
| Spectrum-X plugin | SPCX 1.4-0 | External NET, CollNet component, and tuner | NET data-path fallback | NCCL logs | External NET initialization rejects detected devices, so built-in `NET/IB` carries traffic; CollNet loads but is not separately qualified; SPCX tuner remains active |
| GPUDirect RDMA | NCCL reports `GDR 0` | Two-node collectives | Not enabled | NCCL logs | No GDR qualification claim |
| ARM64 custom image / multi-arch CI | Buildx available | Repository-built images | Deferred | Bootstrap runtime output | No custom multi-arch build/test was executed in M0 |
| GPU Operator / Device Plugin | Not exercised | Kubernetes GPU integration | Deferred to M2 | [`qualification-notes.md`](qualification-notes.md) | Container GPU success does not prove Kubernetes integration |
| Prometheus | Not selected in M0 | Observability | Deferred to M3 | Roadmap | Outside M0 qualification |

Canonical private evidence root: `artifacts/m0-private/20260805-m0-final/`.
Planned sanitized mapping:
`benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/`.
