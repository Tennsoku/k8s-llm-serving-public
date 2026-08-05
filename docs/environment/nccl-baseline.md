# M0 NCCL / RDMA Baseline

## Scope and Configuration

| Field | Value |
|---|---|
| Nodes / ranks | 2 nodes, 1 rank and 1 NVIDIA GB10 per node |
| nccl-tests | 2.19.6 |
| NCCL library | `2.28.9+cuda13.0`, locally built |
| Active MPI | Open MPI `5.0.10rc2` |
| Requested message range | 8 B to 512 MiB, factor 2 |
| Iterations | 5 warm-up, 20 measured, validation enabled |
| Collectives | `all_reduce` and `all_gather` |
| M0 intent | Functional, correctness, transport, and first-reference baseline; not performance tuning |

For `all_gather`, the requested 8 B and 16 B rows resolve to zero count because
of element/alignment constraints; 32 B is the first non-zero row. This is kept as
an observed nccl-tests behavior rather than described as measured payload work.

## Functional Results

| Collective | Exit | Correctness | 512 MiB out-of-place | 512 MiB in-place | Average bus bandwidth |
|---|---:|---|---|---|---:|
| `all_reduce` | 0 | `#wrong=0` / out-of-bounds 0 | algbw/busbw 21.62/21.62 GB/s | 21.66/21.66 GB/s | 5.97826 GB/s |
| `all_gather` | 0 | `#wrong=0` / out-of-bounds 0 | algbw/busbw 41.15/20.57 GB/s | 41.42/20.71 GB/s | 6.13466 GB/s |

These values are environment fingerprints, not optimized limits, and must not
be compared directly with production DGX clusters.

## RDMA Transport Proof

The final logs provide direct transport evidence:

1. mlx5 devices are enumerated as RoCE providers at 200000 Mb/s.
2. NCCL initializes and assigns the built-in `NET/IB` plugin.
3. Collective channels connect through `NET/IB/0` and `NET/IB/1`.
4. RDMA unicast byte counters increase at both ends during both collectives.

| Collective | Local RX delta | Local TX delta | Remote RX delta | Remote TX delta |
|---|---:|---:|---:|---:|
| `all_reduce` | 27,920,337,132 | 27,920,361,790 | 27,920,362,914 | 27,920,336,008 |
| `all_gather` | 13,953,923,086 | 13,953,931,042 | 13,953,932,092 | 13,953,921,962 |

The remote generated `nic-delta.tsv` files contain only their header because the
old remote snapshot omitted the parser section marker. The table above is
derived directly from the intact raw before/after snapshots. This parser-format
defect is not missing remote evidence and does not mean zero remote traffic. The
collector/parser has been corrected for future captures.

Conclusion: NCCL used active mlx5 RoCE/RDMA transport through built-in
`NET/IB`. This conclusion relies on provider/channel logs and both-end counter
deltas together, not on successful NCCL execution alone.

## Spectrum-X and GPUDirect RDMA Boundary

Observed facts:

- The external Spectrum-X `libnccl-net.so` loads and registers SPCX 1.4-0 NET
  and CollNet components.
- The NET component rejects the detected RoCE devices during initialization.
- The CollNet component loads, but M0 does not separately qualify its payload path.
- NCCL uses built-in `NET/IB` for collective data.
- The SPCX tuner is selected as `TUNER/Plugin: Using SPCX (v5)`.
- NCCL reports `GPU Direct RDMA Disabled` for both HCAs and `GDR 0`.
- Dynamic lookup fails for two `MLX5_1.25` Data Direct/DMA-BUF-related symbols;
  both nodes resolve `libmlx5.so.1` to `libmlx5.so.1.24.50.0`.

Therefore:

- RoCE / RDMA / built-in `NET/IB`: qualified and active;
- Spectrum-X external NET data path: loaded but not active for these devices;
- Spectrum-X CollNet: loaded but not separately qualified;
- SPCX tuner: active;
- GPUDirect RDMA / Data Direct: not enabled and not qualified.

The MLX5 userspace mismatch is a demonstrated compatibility boundary, but M0
does not prove it is the sole cause of plugin rejection or quantify the
performance impact of GDR/Spectrum-X.

## MPI and Reproducibility Notes

- Both node fingerprints report `mpirun (Open MPI) 5.0.10rc2`; Ubuntu Open MPI
  4.1.6 packages are also installed, so reproduction must control `PATH`,
  `LD_LIBRARY_PATH`, and header/library selection.
- Each distributed bundle has a valid SHA256 manifest and exit code 0.
- `command.txt` retains the fully expanded `mpirun` invocation, not only a
  wrapper path.
- The distributed capture context records `git_dirty=true`. This limits exact
  byte provenance for locally built binaries but does not invalidate the
  observed command, result, transport logs, or raw counters; it is non-blocking.

## Evidence

- Private sources: `artifacts/m0-private/20260805-m0-final/distributed/nccl-all-reduce/`
  and `artifacts/m0-private/20260805-m0-final/distributed/nccl-all-gather/`
- Node fingerprints: `artifacts/m0-private/20260805-m0-final/{spark-a,spark-b}/node/{network-rdma.txt,runtime-stack.txt}`
- Planned sanitized mapping: `benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/distributed/nccl-{all-reduce,all-gather}/`
- Launch helpers: `distributed/nccl-tests/scripts/`
