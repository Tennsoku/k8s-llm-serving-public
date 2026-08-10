# M0 NCCL Network Qualification

The authoritative result and evidence map are in [`docs/environment/nccl-baseline.md`](../environment/nccl-baseline.md). This note keeps the short operational summary.

## Functional Result

- Two-node `all_reduce`: Pass, exit code 0.
- Two-node `all_gather`: Pass, exit code 0.
- Correctness errors: 0.
- NCCL communicator initialization: Pass.

## Network Transport

- NCCL library: locally built `2.28.9+cuda13.0`.
- Backend carrying collective payload: built-in `NET/IB`.
- Transport/provider: mlx5 RoCE.
- Reported HCA link speed: 200000 Mb/s.
- Active devices: `rocep1s0f1` and `roceP2p1s0f1`.
- Per-channel transport: `NET/IB/0` and `NET/IB/1`.

This log evidence plus RDMA counter deltas directly proves active RDMA transport; it is not inferred from NCCL success alone.

## Counter Evidence

| Collective | Local RX delta | Local TX delta | Remote RX delta | Remote TX delta |
|---|---:|---:|---:|---:|
| `all_reduce` | 27,920,337,132 | 27,920,361,790 | 27,920,362,914 | 27,920,336,008 |
| `all_gather` | 13,953,923,086 | 13,953,931,042 | 13,953,932,092 | 13,953,921,962 |

Remote delta TSV files contain only headers because the old collector omitted the
parser's section marker. The remote values above are derived from the intact raw
before/after snapshots. This is a parser-format defect, not missing evidence or
a zero-traffic result; the collector/parser is corrected for future captures.

## Advanced Capability Boundary

- GPUDirect RDMA: disabled; NCCL reports `GDR 0`.
- The SPCX external NET path loads but rejects the detected devices during NET initialization and does not carry payload.
- The CollNet component loads but is not separately qualified by M0.
- NCCL falls back to built-in `NET/IB`.
- The SPCX tuner is still selected, so Spectrum-X was not “entirely unused.”
- Userspace `libmlx5.so.1.24.50.0` lacks observed `MLX5_1.25` Data Direct/DMA-BUF-related symbols.
- No controlled comparison quantifies the impact of GDR or Spectrum-X on this testbed.

## M0 Status

- ConnectX-7 RoCE path: Pass.
- NCCL IB/RDMA transport: Pass.
- GDR / Data Direct: Not enabled; deferred.
- Spectrum-X external NET data path: Fallback to built-in `NET/IB`.
- Spectrum-X CollNet component: Loaded, not separately qualified.
- SPCX tuner: Active.
