# M0 Platform Qualification Notes

This document records observed platform boundaries. It distinguishes qualified behavior from components deferred to later milestones.

## BND-001 — ARM64 Image Compatibility

Observed:

- The digest-pinned NGC PyTorch image is `arm64` and passed GPU/PyTorch CUDA smoke tests on both nodes.
- The NGC vLLM image loaded Qwen3-0.6B and served HTTP 200 responses on both nodes.
- Docker Buildx is available.

Not exercised:

- a repository-built ARM64 image;
- a multi-architecture manifest built and tested by CI;
- x86_64/ARM64 parity.

Status: official ARM64 images are qualified for the M0 smoke scope; custom image and multi-arch CI work is deferred.

## BND-002 — Grace Blackwell Unified Memory

Observed:

- Linux reports approximately 121 GiB of system-visible memory.
- `nvidia-smi` reports `[N/A]` for framebuffer memory total/used on GB10.
- Host and container CUDA execution succeeds despite the unavailable framebuffer telemetry.
- vLLM requires explicit memory controls; unrestricted KV-cache reservation can pressure the shared system memory pool.

Operational implication:

- future capacity experiments must correlate system memory, cgroup memory, runtime/KV-cache metrics, and failures;
- absence of `nvidia-smi` framebuffer values is not absence of memory usage;
- unified memory does not by itself prove that GPUDirect RDMA is unnecessary or that enabling it has no performance effect.

## BND-003 — Container-First Runtime Baseline

Host Python 3 is present, but host PyTorch and vLLM imports fail. This is an intentional container-first baseline and is a non-blocking warning in bootstrap verification.

Qualified:

- host CUDA compilation/execution;
- plain Docker lifecycle;
- GPU passthrough;
- PyTorch CUDA allocation and matrix multiplication in a digest-pinned container.

## BND-004 — MPI Runtime Selection

Observed:

- Ubuntu Open MPI 4.1.6 packages are installed.
- the active `mpirun` reports Open MPI `5.0.10rc2`.
- the intended distributed stack is HPC-X-aligned, but the final capture did not retain the exact executable or loaded-library paths needed to prove that provenance.

Implication: `PATH`, `LD_LIBRARY_PATH`, headers, libraries, and remote-shell environment must select one MPI stack consistently. Commands and APIs are version-sensitive.

## BND-005 — RDMA, Spectrum-X, and GDR

Qualified:

- mlx5 RoCE devices are present;
- NCCL channels use built-in `NET/IB`;
- RDMA unicast byte counters increase during collectives.

Not qualified:

- GPUDirect RDMA: NCCL reports `GDR 0`;
- Spectrum-X external NET data path: NET initialization rejects the detected devices and NCCL uses built-in `NET/IB` instead.
- Spectrum-X CollNet component: loaded, but not separately qualified in M0.

Nuance:

- the SPCX tuner is still used;
- `libmlx5.so.1` resolves to userspace `libmlx5.so.1.24.50.0`;
- NCCL fails to resolve two `MLX5_1.25` Data Direct/DMA-BUF-related symbols;
- the current evidence does not prove that this userspace mismatch is the sole cause of Spectrum-X device rejection or quantify any performance impact.

See [`nccl-baseline.md`](nccl-baseline.md).

## BND-006 — Kubernetes GPU Integration

GPU Operator, RuntimeClass, Device Plugin, extended-resource scheduling, and Kubernetes GPU workload behavior were not exercised in M0.

M0 proves host and Docker GPU functionality only. Kubernetes integration remains an explicit M2 compatibility boundary rather than an inferred pass.

## BND-007 — Bootstrap Replay Provenance

On 2026-08-05, both nodes replayed the host, container-runtime, GPU-container,
and network qualification scripts with exit code `0`. Both outer contexts record
commit `784506a1b72727de0dcc774eabcbf9f623847438` and `git_dirty=false`.

Limitations:

- the per-layer files written below `deployments/bootstrap/out/20260805-m0-recheck/` were not copied into the final bundle;
- the evidence does not record clean-machine provisioning or reboot recovery;
- `hello-world:latest` is a lifecycle-only probe and was not digest-pinned;
- the replay's iperf check is TCP and does not prove RDMA traffic.

Status: the revised M0 replay criterion passed from the captured commit with a
clean tracked worktree on both nodes. Per-layer archiving, a pinned lifecycle
probe, clean-machine provisioning, and reboot recovery are optional evidence
hardening; they are trivial/non-blocking because M0 makes no such recovery claim.

## Deferred Work

- Optional self-contained per-layer replay archive and lifecycle-probe pinning.
- Repository-built ARM64/multi-arch image test.
- GPU Operator and Device Plugin validation in M2.
- Controlled version-aligned comparison before making GDR or Spectrum-X performance claims.
- Controlled long-duration monitoring and TCP receive-buffer tuning.
