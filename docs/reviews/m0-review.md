# M0 Final Review

## Review Disposition

Reviewed on 2026-08-05 against the revised M0 output, experiments, and exit
criteria in `docs/Roadmap.md`.

Decision:

> M0 technical qualification is complete. The repository is in publish
> preparation; sanitized evidence and public-history review are release gates,
> not blockers on the M0 technical result or M1 preparation.

No observed hardware, container, TCP-connectivity, NCCL-correctness, or
RDMA-transport failure blocks M1. M0 does not claim clean-machine provisioning,
reboot recovery, production equivalence, GDR, or Spectrum-X external NET.

Primary private evidence root: `artifacts/m0-private/20260805-m0-final/`.

## Evidence Integrity

- Raw evidence was reviewed without modification.
- All 13 `SHA256SUMS` manifests in the selected private tree validate.
- The pre-public private-history capture ID recorded in the selected evidence is
  `784506a1b72727de0dcc774eabcbf9f623847438`. It anchors the private capture,
  but may intentionally no longer resolve after the reviewed public-history
  squash.
- Both bootstrap replay contexts record `git_dirty=false` and exit `0`.
- Node-inventory, host-CUDA, GPU-container, vLLM, TCP, and NCCL contexts record
  `git_dirty=true` after generated outputs/build products existed. This limits
  exact byte provenance for locally built artifacts; it does not change the
  observed environment or benchmark output.
- The Git-dirty probe displayed in the canonical node `repository.txt` files is
  malformed by an early command-substitution bug. The corresponding
  `context.env` value is authoritative; the collector is fixed for future
  captures. This is a trivial evidence-display defect, not a qualification
  failure.
- Superseded test remnants were removed from the selected canonical tree. No
  retained failure is relabeled as a pass.

## Exit-Criteria Mapping

| Roadmap criterion | Status | Evidence-backed assessment |
|---|---|---|
| Both Spark nodes run GPU containers within M0 smoke scope | Pass | Digest-pinned PyTorch tests exit 0 on both nodes; bootstrap replay also passes GPU visibility and CUDA work. |
| Critical versions, image digests, and configuration are recorded | Pass | Ubuntu/kernel/driver/CUDA/runtime versions and both executed PyTorch/vLLM digests are recorded. Physical identity and a standalone DGX OS marker are intentionally outside the revised criterion. |
| A selected baseline runtime loads a minimal model | Functional pass | Both digest-pinned vLLM captures initialize the model and return HTTP 200; Spark A retains response JSON. Outer exit 141 is a harness caveat. |
| Network baseline distinguishes management and data paths | Pass | Topology separates `enP7s7` management from ConnectX data links; the canonical four-stream TCP wrapper passes all stages. |
| Bootstrap verification is reproducible from captured source state | Pass | Both nodes replay four layers at the captured commit with clean tracked worktrees and exit 0. No clean-machine/reboot claim is made. |
| ARM64, unified-memory, and Kubernetes GPU boundaries are documented | Pass | ARM64 official-image smokes pass; unified-memory telemetry constraints are recorded; Kubernetes GPU integration is explicitly deferred to M2. |
| Later benchmarks can record fixed context | Pass | The benchmark template covers command, provenance, variables, network/MPI context, hashes, interpretation, and limitations. |

## Experiment Assessment

| Experiment | Status | Important limitation |
|---|---|---|
| Host CUDA smoke | Pass on both nodes | Functional vector-add, not a performance result. |
| Container CUDA/PyTorch smoke | Pass on both nodes | Host PyTorch is intentionally absent in the container-first baseline. |
| vLLM Qwen3-0.6B smoke | Functional pass / harness partial | Both commands use the fixed digest and return HTTP 200; wrappers exit 141 and only Spark A retains response JSON. |
| ARM64 custom image / multi-arch CI | Deferred | Official ARM64 images are qualified; repository-built multi-arch validation is later work. |
| TCP baseline | Pass | Canonical A→B P4/30s receiver result is 96.7404 Gbit/s with 43,506 retransmissions; this is not a tuning limit. |
| NCCL `all_reduce` / `all_gather` | Pass | Both exit 0 with zero correctness errors; context dirty state is a non-blocking built-artifact provenance caveat. |
| Bootstrap qualification replay | Pass on both nodes | Clean tracked-worktree replay is proven; provisioning/reboot recovery is not claimed. |

## Facts, Interpretations, and Hypotheses

| Claim | Type | Evidence | Confidence | Conclusion |
|---|---|---|---|---|
| Host CUDA kernels execute on both nodes | Observed fact | Both host test results exit 0 and vector-add passes | High | Qualified |
| GPU containers execute real PyTorch CUDA work | Observed fact | Both digest-pinned container captures exit 0 | High | Qualified |
| vLLM loaded the model and served a request | Observed fact | Both logs show HTTP 200; Spark A response JSON | High | Functional criterion met |
| The vLLM outer wrapper passed | Contradicted claim | Both outer results report 141 | High | Do not claim; harness issue only |
| Four-stream TCP reaches 96.7404 Gbit/s receiver throughput | Observed fact | Canonical final iperf JSON and exit codes | High | Initial baseline |
| TCP receive tuning may be incomplete | Interpretation | 43,506 retransmissions and remote `rx_out_of_buffer` +43,504 | Medium | Plausible; later controlled tuning |
| NCCL used active RDMA | Observed fact | mlx5 RoCE provider, `NET/IB` channels, both-end RDMA byte deltas | High | Qualified |
| GPUDirect RDMA was active | Contradicted claim | `GPU Direct RDMA Disabled` and `GDR 0` | High | Not active |
| Spectrum-X was entirely unused | Overbroad claim | External NET fails, CollNet loads, SPCX tuner is selected | High | Use component-specific wording |
| Missing `MLX5_1.25` userspace symbols are a compatibility boundary | Observed fact | `dlvsym` failures and `libmlx5.so.1.24.50.0` | High | Qualified boundary |
| The MLX5 mismatch is the sole plugin-rejection cause | Hypothesis | No version-aligned A/B test | Low | Unresolved |
| GDR/Spectrum-X has negligible performance impact | Hypothesis | No controlled comparison | Low | Do not claim |
| Clean-machine provisioning or reboot recovery is reproducible | Not claimed | No provisioning/boot marker evidence | High | Outside revised M0 scope |

## Output Review

| Output | Status | Notes |
|---|---|---|
| Environment inventory and compatibility matrix | Complete | Public tracked files use logical identities; physical/private details are isolated in ignored companions. |
| Network topology and TCP baseline | Complete | Canonical final capture passes; old single-stream/reverse references were removed. |
| NCCL/RDMA baseline | Complete | Comparable remote deltas exist in raw snapshots; header-only TSV is the fixed parser-format defect. |
| Benchmark environment template | Complete for future use | Existing runs are not retroactively required to contain every optional field. |
| Bootstrap verification scripts | Present and replayed | Both clean tracked-worktree replay contexts pass. |
| NCCL wrappers and MPI verifier | Present | Duplicated/hard-coded all-gather material is removed; final `command.txt` files retain expanded `mpirun`. |
| ADR-0001 | Complete | Testbed scope and non-production equivalence are explicit. |
| Public sanitized evidence | Pending release gate | Generated only through the reviewed fail-closed publisher. |

## Non-blocking Evidence-Harness Follow-ups

- Fix vLLM lifecycle/pipe handling so an HTTP-success capture also exits 0 and
  retain structured response JSON on every claimed node.
- Future TCP captures now retain `command.txt`, collector checksum, remote SSH
  status, and parser-compatible counter sections; the canonical existing bundle
  is not rewritten retroactively.
- Optionally pin `hello-world` even though it is only a lifecycle probe.
- Optionally archive bootstrap per-layer outputs and exact MPI executable/library
  paths for stronger self-contained provenance.
- Clean-machine provisioning and reboot recovery may be added if a later
  milestone chooses to make those claims.

## Public-Release Gate

1. Stage the intended public source tree (or prepare the squash candidate) so
   both working-tree and index scans represent the intended result.
2. Generate `benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/`
   with `scripts/m0/m0-evidence.sh publish 20260805-m0-final`.
3. Review the generated privacy, secret, and tracked-repository reports; complete
   the manual checklist; run read-only `verify-public 20260805-m0-final`.
4. Ensure ignored `*.private.md`, `artifacts/m0-private/`, and
   `deployments/bootstrap/out/` content, plus the local `helper/` kit, is absent
   from tracked public history.
5. Add the reviewed sanitized export, squash/amend into the reviewed public
   commit, and create/push only the new public
   history. Review author/committer metadata and the destination URL; push one
   explicit tip, never `--mirror`, and do not push legacy refs or tags that
   retain deleted private evidence. Scan a fresh clone before announcement.

This gate protects publication security; it does not invalidate the private M0
technical result.

## Entry to M1

M1 design and workload preparation may proceed. Repository status is
`M0 Complete / Publish Done` and `M1 Started`.
