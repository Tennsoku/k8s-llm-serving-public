# AGENTS.md

## Project

This repository implements a Kubernetes-native LLM inference platform using
two DGX Spark nodes as the primary GPU testbed.

Read these files before reviewing or modifying M0 work:

1. `README.md`
2. `docs/Roadmap.md`
3. `docs/context/project-context.md`
4. `docs/context/current-status.md`
5. `docs/context/m0-review-brief.md`

## Current Milestone

The current milestone is:

- M0 — Platform Qualification & Reproducible Environment

Do not treat M0 as a performance-optimization milestone.
Its purpose is to establish a reproducible and trustworthy hardware,
software, container, and network baseline.

## Review Principles

- Preserve raw evidence.
- Do not invent benchmark results.
- Distinguish observed facts, interpretations, and unresolved hypotheses.
- Treat ARM64, Grace Blackwell unified memory, container compatibility,
  ConnectX-7 networking, NCCL, and MPI as explicit compatibility boundaries.
- Do not describe two DGX Spark nodes as production-equivalent to a DGX cluster.
- Do not conclude that RDMA or GPUDirect RDMA is active without direct evidence.
- Flag commands or APIs that are version-sensitive.
- Prefer reproducible scripts over manually copied command sequences.

## Expected M0 Evidence

Review M0 against:

- Host and hardware inventory
- Software compatibility matrix
- Host CUDA smoke test
- Container GPU/PyTorch smoke test
- Container runtime validation
- Network topology
- TCP bandwidth and latency baseline
- NIC counter deltas
- NCCL collective baseline
- MPI/runtime configuration
- Reproduction and known-limitations documentation

## Commands

Before proposing changes:

1. Inspect the repository structure.
2. Read the relevant evidence and logs.
3. Run only non-destructive commands unless explicitly authorized.
4. Report missing evidence separately from implementation defects.
