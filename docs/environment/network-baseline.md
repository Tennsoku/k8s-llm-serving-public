# M0 TCP Network Baseline

## Scope

This baseline qualifies reachability and records an initial TCP reference for
the direct ConnectX-7 data path. It is not a link-tuning or maximum-throughput
result.

| Field | Value |
|---|---|
| Nodes | Spark A and Spark B |
| Data interface | `enp1s0f1np1` on each node |
| Link | 200 Gb/s reported, full duplex, direct attach |
| MTU | 1500 |
| Protocol | iperf3 TCP |
| Direction | Spark A → Spark B |
| Streams / duration | 4 / 30 seconds |
| Management path | Separate `enP7s7` LAN; Realtek `10ec:8127`, carrier/up, negotiated speed not retained; reachability checked, no management throughput run retained |

## Canonical Result

The canonical final capture completed successfully:

| Metric | Result |
|---|---:|
| Ping exit code | 0 |
| iperf client exit code | 0 |
| iperf server / SSH exit code | 0 |
| Sender throughput | 96.7470 Gbit/s |
| Receiver throughput | 96.7404 Gbit/s |
| Sender retransmissions | 43,506 |
| Ping packets | 20 transmitted / 20 received / 0% loss |
| RTT min / avg / max / mdev | 0.173 / 0.767 / 1.056 / 0.250 ms |

The result is a single canonical four-stream forward fingerprint. Previously
retained single-stream, reverse, and superseded automated outputs were removed
from the selected M0 bundle and are not used by the final conclusion.

## NIC Counter Context

The remote raw snapshots record:

- `rx_out_of_buffer`: 12,398 → 55,902, delta +43,504;
- the corresponding IP receive-missed counter also increases by 43,504.

The local and remote generated `nic-delta.tsv` files contain only their header.
For the remote side, this is caused by the old collector omitting the section
marker expected by the parser; it is not a zero-counter result. The raw snapshots
are intact and covered by the valid bundle manifest. The parser now accepts the
legacy no-marker format and future remote snapshots record their SSH exit code.
The selected local ethtool counter set showed no non-zero parsed delta.

## Interpretation

Observed facts:

- management and high-speed data paths are distinct and independently reachable;
- the data path sustained 96.7404 Gbit/s receiver throughput in this run;
- retransmissions and remote receive-buffer pressure are visible and should be
  retained as part of the environment fingerprint.

This is sufficient for the M0 functional baseline. It does not demonstrate 200
Gb/s saturation, optimal tuning, reverse-direction symmetry, long-duration
stability, or production equivalence. TCP success also does not prove RDMA;
RDMA qualification is documented in [`nccl-baseline.md`](nccl-baseline.md).

The bundle did not independently retain `command.txt` or a collector checksum.
That provenance hardening is implemented for future TCP captures and is a
non-blocking issue for the existing functional result.

## Evidence

- Private source: `artifacts/m0-private/20260805-m0-final/distributed/tcp-baseline/`
- Bootstrap context: `artifacts/m0-private/20260805-m0-final/{spark-a,spark-b}/tests/bootstrap-replay/`
- Planned sanitized mapping: `benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/distributed/tcp-baseline/`
