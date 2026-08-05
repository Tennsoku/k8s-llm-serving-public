# M0 Critical Evidence Collection

## Scope

This collection intentionally retains only evidence needed to support the M0 claims:

1. Node/OS/architecture and memory fingerprint.
2. NVIDIA driver, CUDA, Python/PyTorch/vLLM and container-runtime versions.
3. Pinned container-image identity and architecture.
4. Data-interface link/driver/firmware and RDMA userspace capability.
5. Host CUDA, GPU-container and minimal-runtime smoke-test outputs.
6. Two-node TCP latency/throughput with local and remote NIC deltas.
7. NCCL all-reduce/all-gather output with local and remote NIC deltas.
8. Exit code, timestamp, command, Git revision and checksums for every test.

It deliberately omits `dmidecode`, complete package inventories, full `nvidia-smi -q`, general journal logs, process lists, environment dumps and full NIC counters by default.

## Result Layout

```text
artifacts/m0-private/<run-id>/                 # never commit
├── spark-a/
│   ├── node/
│   └── tests/
├── spark-b/
│   ├── node/
│   └── tests/
└── distributed/
    ├── tcp-baseline/
    ├── nccl-all-reduce/
    └── nccl-all-gather/

benchmarks/raw-results/m0-platform-qualification/<run-id>/
└── sanitized copy with publication scan and checklist
```

## Preparation

Run from the repository root:

```bash
cp config/m0-evidence.env.example .env.m0.local
chmod 600 .env.m0.local
${EDITOR:-vi} .env.m0.local
set -a
source .env.m0.local
set +a
```

Sourcing the file makes values such as `GPU_TEST_IMAGE` available to wrapper commands. The collector does not dump the complete environment.

Add to `.gitignore`:

```gitignore
.env.m0.local
artifacts/m0-private/
```

Use the same explicit `RUN_ID` in `.env.m0.local` on both nodes when collecting one evidence set.
Each node/test/distributed capture writes only below the dedicated private run
root, rejects symlink indirection, and refuses to overwrite a non-empty capture
directory. Choose a new `RUN_ID` or test name instead of mutating raw evidence.

## Node A and Node B: one critical fingerprint each

```bash
./scripts/m0/m0-evidence.sh node
```

This is the only general inventory command required on each Spark.

## Host CUDA smoke test

Use the existing test source; keep compilation and execution in the same captured command:

```bash
./scripts/m0/m0-evidence.sh test cuda-host -- \
  bash -lc 'nvcc -O2 -std=c++17 vector_add.cu -o vector_add && ./vector_add'
```

Run it on both nodes only when claiming that both nodes passed host CUDA qualification. Otherwise run it on the designated baseline node and describe the scope accurately.

## GPU container/PyTorch smoke test

```bash
./scripts/m0/m0-evidence.sh test gpu-container -- \
  docker run --rm --gpus all "$GPU_TEST_IMAGE" \
  bash -lc 'nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,pci.bus_id --format=csv,noheader && python3 -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"'
```

Run on both nodes because M0 claims both Spark nodes can run GPU containers.

## Minimal vLLM/runtime smoke test

Wrap the exact command already used successfully. Examples should not replace the tested command:

```bash
./scripts/m0/m0-evidence.sh test vllm-smoke -- \
  bash -lc '<EXACT EXISTING VLLM LOAD/INFERENCE COMMAND>'
```

One successful node is sufficient for the M0 runtime-load criterion, provided the documentation states which node was tested.

## Two-node TCP baseline

Run once from Spark A. The script starts a one-shot `iperf3` server on Spark B through SSH, runs ping and parallel TCP streams, and captures both NICs before and after:

```bash
./scripts/m0/m0-evidence.sh tcp
```

This replaces separate manual `ping`, `iperf3`, `ip -s link`, and filtered `ethtool -S` collection.
Future captures require both remote snapshots to complete over SSH and expose at
least one filtered ethtool counter. The raw snapshot records SSH/counter status,
`result.env` records the before/after status, and the wrapper exits non-zero if
ping, either iperf endpoint, or either remote snapshot fails.

## NCCL all-reduce and all-gather

Run from the launcher node and wrap the exact previously validated commands:

```bash
./scripts/m0/m0-evidence.sh distributed nccl-all-reduce -- \
  <EXACT EXISTING MPI/NCCL ALL_REDUCE COMMAND>

./scripts/m0/m0-evidence.sh distributed nccl-all-gather -- \
  <EXACT EXISTING MPI/NCCL ALL_GATHER COMMAND>
```

The wrapper retains stdout/stderr, exit status, elapsed time, and local/remote NIC counter deltas. Remote SSH failure or a zero-counter snapshot is retained but makes the future wrapper exit non-zero. The delta parser remains backward-compatible with the canonical markerless remote snapshots. Use `NCCL_DEBUG=INFO` and the transport-related debug settings already selected for the experiment; do not insert credentials into the command line.

## Bootstrap qualification replay evidence

To prove that the verification sequence can be replayed on an already configured node, capture the four layers as one test:

Before running, add node-local values for `MGMT_IFACE` and `PEER_MGMT_IP` to
`.env.m0.local`. `RUNTIME_SMOKE_IMAGE=hello-world:latest` is acceptable for the
lifecycle-only M0 check; using an immutable reference is optional evidence
hardening, not a technical blocker. Do not place real addresses or credentials
in the tracked command list.

Require an explicit shared `RUN_ID`, validate every network input, and place the scripts' `OUTPUT_ROOT` below the outer capture directory. This makes the per-layer files and invoked-script checksums exist before `m0-evidence.sh` generates its final manifest:

```bash
: "${RUN_ID:?set the same explicit RUN_ID on both nodes}"
: "${NODE_LABEL:?set NODE_LABEL}"
: "${DATA_IFACE:?set DATA_IFACE}"
: "${PEER_DATA_IP:?set PEER_DATA_IP}"
: "${MGMT_IFACE:?set MGMT_IFACE in .env.m0.local}"
: "${PEER_MGMT_IP:?set PEER_MGMT_IP in .env.m0.local}"
RUNTIME_SMOKE_IMAGE="${RUNTIME_SMOKE_IMAGE:-hello-world:latest}"

M0_REPLAY_OUTPUT="$PWD/${PRIVATE_EVIDENCE_ROOT:-artifacts/m0-private}/$RUN_ID/$NODE_LABEL/tests/bootstrap-replay/per-layer"
export OUTPUT_ROOT="$M0_REPLAY_OUTPUT"

./scripts/m0/m0-evidence.sh test bootstrap-replay -- \
  bash -lc 'mkdir -p "$OUTPUT_ROOT" &&
            sha256sum deployments/bootstrap/verify-host.sh \
              deployments/bootstrap/verify-container-runtime.sh \
              deployments/bootstrap/verify-gpu-container.sh \
              deployments/bootstrap/verify-network.sh \
              > "$OUTPUT_ROOT/invoked-scripts.sha256" &&
            CUDA_SMOKE_BIN=./deployments/bootstrap/platform-qualification/cuda-smoke/vector_add ./deployments/bootstrap/verify-host.sh &&
            RUNTIME_SMOKE_IMAGE="$RUNTIME_SMOKE_IMAGE" ./deployments/bootstrap/verify-container-runtime.sh &&
            GPU_IMAGE="$GPU_TEST_IMAGE" ./deployments/bootstrap/verify-gpu-container.sh &&
            REQUIRE_RDMA=1 RUN_IPERF=1 \
              MGMT_IFACE="$MGMT_IFACE" DATA_IFACE="$DATA_IFACE" \
              PEER_MGMT_IP="$PEER_MGMT_IP" PEER_DATA_IP="$PEER_DATA_IP" \
              ./deployments/bootstrap/verify-network.sh'
```

Start an `iperf3` server on the peer before this capture. The path above deliberately nests `OUTPUT_ROOT` under `tests/bootstrap-replay/`, so the outer wrapper's final `SHA256SUMS` covers the per-layer Docker, CUDA, RDMA, and iperf files. A wrapper stdout summary alone is not equivalent evidence.

If claiming reboot recovery or clean-checkout/clean-machine reproduction, also retain:

- boot ID, boot time, or another direct reboot marker;
- clean `git status` and the exact commit, or a diff/archive checksum;
- SHA256 of every invoked script and binary;
- provisioning inputs and package/image locks;
- complete per-layer outputs and a final SHA256 manifest.

Without those records, do not claim clean-machine provisioning or reboot
recovery. The revised M0 criterion requires the captured commit and clean tracked
worktree replay, which the final two-node evidence satisfies.

## Gather Spark B evidence on Spark A

After Spark B has completed its node-local captures, run on Spark A:

```bash
./scripts/m0/m0-evidence.sh pull-remote
```

`REMOTE_REPO_ROOT` and the SSH target stay in `.env.m0.local`. This step only pulls the `spark-b/` portion of the selected private run.

## Publish sanitized evidence

Run on Spark A or the workstation that now contains the complete private evidence tree:

```bash
./scripts/m0/m0-evidence.sh publish 20260805-m0-final
# Manually review the three reports and check all 14 generated checklist items.
./scripts/m0/m0-evidence.sh verify-public 20260805-m0-final
```

The two evidence roots are fixed safety boundaries: private input must remain
under `artifacts/m0-private/`, and output under
`benchmarks/raw-results/m0-platform-qualification/`. Before `publish`, make the
Git index represent the intended public source tree (for example, stage the
reviewed squash candidate); the gate scans both tracked working-tree files and
index blobs and deliberately rejects a stale sensitive index. Only the sanitized
tree under `benchmarks/raw-results/` is intended for Git.

## Minimum final evidence matrix

| Claim | Required captured evidence |
|---|---|
| Both nodes have a qualified base environment | `node/` on Spark A and Spark B |
| Host CUDA works | `tests/cuda-host/` for the claimed node scope |
| Both nodes run GPU containers | `tests/gpu-container/` on both nodes |
| A baseline runtime loads | `tests/vllm-smoke/` on at least one node |
| Data and management paths are distinguishable | sanitized `network-rdma.txt` plus topology document |
| Two-node TCP baseline exists | `distributed/tcp-baseline/` |
| NCCL collectives execute | all-reduce and all-gather distributed captures |
| RDMA is or is not proven | RDMA capability snapshot + NCCL log + NIC deltas; do not infer from success alone |
| Qualification scripts replay on configured nodes | `bootstrap-replay/` command, context, result, stdout/stderr and valid outer SHA256 manifest |
| Verification replays from the captured tracked source state | Commit, `git_dirty=false`, command/context/result, and valid manifest on both nodes |
| Clean-machine provisioning or reboot recovery, if claimed | Boot/clean-state marker, provisioning inputs, immutable locks, complete output and manifests |
