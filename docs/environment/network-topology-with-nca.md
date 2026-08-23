# M0 Network Topology

## Observed Topology

```text
Management / LAN

                    Router / switch
                     /           \
             Spark A enP7s7   Spark B enP7s7
               carrier/up       carrier/up

High-speed direct data fabric

Spark A enp1s0f1np1  <------ 200 Gb/s ------>  Spark B enp1s0f1np1
  IPv4 link-local; TCP, NCCL bootstrap/OOB, RoCE HCA

Spark A enP2p1s0f1np1 <------ 200 Gb/s ------> Spark B enP2p1s0f1np1
  no host IP; second RoCE HCA used by NCCL
```

Both high-speed ports report carrier and 200 Gb/s link speed with MTU 1500.
The two-node NCCL logs enumerate both RoCE devices and assign channels to
`NET/IB/0` and `NET/IB/1`.

The canonical node captures identify each management controller as Realtek
`10ec:8127` and retain carrier/up state. They do not retain the management NIC
driver or negotiated speed.

## Sanitized Interface Map

| Node | Interface | Public address description | Link | MTU | Purpose |
|---|---|---|---:|---:|---|
| Spark A | `enP7s7` | private management IPv4 (redacted) | Carrier/up; speed not retained | 1500 | Management / LAN |
| Spark B | `enP7s7` | private management IPv4 (redacted) | Carrier/up; speed not retained | 1500 | Management / LAN |
| Spark A | `enp1s0f1np1` | IPv4 link-local (redacted) | 200 Gb/s | 1500 | IP-configured data/OOB path and RoCE HCA, under same subnet as Spark B |
| Spark B | `enp1s0f1np1` | IPv4 link-local (redacted) | 200 Gb/s | 1500 | IP-configured data/OOB path and RoCE HCA, under same subnet as Spark A |
| Spark A | `enP2p1s0f1np1` | no host IP | 200 Gb/s | 1500 | Second RoCE HCA used by NCCL |
| Spark B | `enP2p1s0f1np1` | no host IP | 200 Gb/s | 1500 | Second RoCE HCA used by NCCL |

Exact addresses and MACs are deliberately absent from this public document.

## Transport Mapping

| Traffic | Observed path | Evidence-backed conclusion |
|---|---|---|
| Management access | `enP7s7` on both nodes | Reachability passed in bootstrap replay; no management-link throughput baseline was retained |
| TCP data baseline | IP-configured `enp1s0f1np1` pair | Canonical four-stream A→B run passed at 110.705 Gbit/s receiver throughput |
| NCCL bootstrap/OOB | `enp1s0f1np1` IPv4 pair | NCCL logs explicitly select this interface |
| NCCL collective payload | mlx5 RoCE through built-in `NET/IB` across two HCAs | Per-channel `NET/IB` lines and both-end RDMA counter deltas prove active RDMA transport |
| GPUDirect RDMA | Disabled | NCCL reports `GPU Direct RDMA Disabled` and `GDR 0` |

The SPCX external NET path loads but rejects the detected devices during NET
initialization and does not carry the collective payload. The CollNet component
loads but is not separately qualified by M0. NCCL uses built-in `NET/IB`, while
the SPCX tuner remains active; therefore “Spectrum-X was entirely unused” would
be inaccurate.

## Public Evidence

After the publication gate is completed:

- `benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/{spark-a,spark-b}/node/network-rdma.txt`
- `benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/{spark-a,spark-b}/tests/bootstrap-replay/stdout.log`
- `benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/distributed/nccl-{all-reduce,all-gather}/stdout.log`
- [`network-baseline.md`](network-baseline.md)
- [`nccl-baseline.md`](nccl-baseline.md)
