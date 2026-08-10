# Current Status

## Milestone

M0 — Platform Qualification & Reproducible Environment is complete. 
M1 has started. Current minor step: M1.2a — Lightweight Experiment Convention

## Confirmed

- Both DGX Spark nodes completed host CUDA, digest-pinned GPU-container, and
  four-layer bootstrap qualification checks.
- Both bootstrap replay contexts record commit
  `784506a1b72727de0dcc774eabcbf9f623847438`, `git_dirty=false`, exit `0`.
- Both vLLM commands execute
  `nvcr.io/nvidia/vllm@sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2`;
  both logs return HTTP 200 and Spark A also retains response JSON.
- The canonical TCP capture passes ping, iperf client, and iperf server with
  exit `0`: four streams for 30 seconds, 96.7404 Gbit/s receiver throughput,
  43,506 retransmissions, and 0% ping loss (0.767 ms average RTT).
- NCCL `all_reduce` and `all_gather` both exit `0` with zero correctness and
  out-of-bounds errors.
- NCCL logs plus local and remote raw RDMA counter deltas prove built-in
  `NET/IB` over mlx5 RoCE carried collective traffic.
- GPUDirect RDMA was not active (`GDR 0`). The SPCX external NET data path did
  not initialize; built-in `NET/IB` carried payload. CollNet loaded but was not
  separately qualified, while the SPCX tuner remained active.
- All 13 private evidence manifests validate.

## Non-blocking Limitations

- Both vLLM outer wrappers exit `141` despite the functional HTTP 200 result;
  this is a lifecycle/pipe harness issue, not a runtime failure.
- The canonical TCP bundle predates the new independent `command.txt` and
  collector-checksum capture. This is provenance hardening for future runs.
- Existing remote NIC `nic-delta.tsv` files contain only headers because the
  collector omitted the parser marker. Raw before/after snapshots contain the
  counters, including TCP remote `rx_out_of_buffer` +43,504 and both-end NCCL
  RDMA byte deltas. The parser is now backward-compatible for future derivation.
- The Git-dirty probe displayed in the canonical node `repository.txt` files is
  malformed by an early command-substitution bug. Each bundle's `context.env`
  is authoritative, and the collector is fixed for future captures. This is a
  trivial evidence-display defect.
- Per-layer bootstrap outputs, clean-machine provisioning, and reboot recovery
  were not retained/proven. M0 makes none of those claims; `hello-world:latest`
  is also a lifecycle-only, trivial non-blocking identity issue.

## Publication Gate

- Tracked environment documentation now uses sanitized logical identities;
  sensitive inventory/topology companions are local ignored `*.private.md` files.
- The publication tool now stages exports, validates source manifests and paths,
  rejects unsafe file shapes/names, sanitizes and scans evidence, checks the
  tracked working tree plus Git index, seals SHA256, and verifies without
  mutating the public tree. Destructive copy/replace operations are confined to
  the two dedicated evidence roots.
- The sanitized public evidence tree, manual checklist, public-history squash,
  and new public remote remain the release steps. They do not invalidate the M0
  technical results.

The authoritative assessment is [`docs/reviews/m0-review.md`](../reviews/m0-review.md).
