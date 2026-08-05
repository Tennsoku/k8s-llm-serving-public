# ADR-0001: DGX Spark as the Primary GPU Testbed

- Status: Accepted
- Date: 2026-08-05
- Milestone: M0

## Context

The project needs a real GPU environment for LLM serving, unified-memory behavior, container compatibility, high-speed networking, NCCL, and later Kubernetes control-plane experiments. The available hardware is a pair of DGX Spark nodes based on AArch64 Grace Blackwell GB10 with ConnectX-7 networking.

These nodes are materially different from x86_64 data-center DGX systems. They expose unified-memory telemetry and ARM64 image boundaries, and a two-node direct-link setup does not reproduce the scale, topology, redundancy, or operational properties of a production DGX cluster.

## Decision

Use the two DGX Spark nodes as the primary GPU testbed while using ordinary x86_64/VM/WSL2 environments for development, CI, Kubernetes control-plane work, documentation, and lightweight load generation where appropriate.

All results must:

- identify the testbed as a two-node Grace Blackwell environment;
- record ARM64, driver, CUDA, container, MPI/NCCL, and network context;
- separate management, TCP data, RDMA, NCCL transport, and GDR claims;
- preserve raw evidence and failed runs;
- avoid extrapolating Spark results to production DGX clusters without separate evidence.

## Consequences

Positive:

- real CUDA, container, unified-memory, ConnectX-7, RoCE, and NCCL behavior can be observed;
- the same two nodes provide a stable hardware basis for later serving and Kubernetes experiments;
- ARM64 and unified-memory constraints become explicit engineering inputs rather than hidden assumptions.

Constraints:

- container and package availability must be verified for AArch64;
- `nvidia-smi` framebuffer-memory reporting is not a complete memory signal on GB10;
- two nodes cannot validate large-cluster topology, congestion, fault domains, or operational scale;
- Kubernetes GPU Operator/Device Plugin behavior requires separate M2 validation;
- GDR/Spectrum-X behavior and performance cannot be inferred from basic RDMA success.

## Alternatives Considered

1. Use only x86_64/VM environments: rejected for GPU, unified-memory, and real high-speed-network validation.
2. Describe the pair as a small production DGX cluster: rejected because it would overstate topology and operational equivalence.
3. Delay all work until larger data-center hardware is available: rejected because the current testbed is sufficient for controlled mechanism-level experiments when its scope is explicit.

## Validation

M0 evidence demonstrates host CUDA, GPU containers, minimal vLLM serving, TCP data-path baselines, NCCL collectives, and built-in `NET/IB` over mlx5 RoCE. The M0 review documents unqualified boundaries separately.
