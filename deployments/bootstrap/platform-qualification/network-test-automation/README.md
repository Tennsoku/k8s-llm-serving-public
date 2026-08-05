# Network Test Automation

This package automates one two-node TCP network baseline run.

It:

1. Validates SSH and routing.
2. Captures local and remote NIC/kernel counters.
3. Starts a one-shot `iperf3` server remotely.
4. Runs a bound-interface TCP test.
5. Captures after-state counters.
6. Calculates counter deltas.
7. Generates `summary.json` and `summary.md`.
8. Generates SHA-256 hashes for the evidence directory.

## Install

```bash
chmod +x run-network-test.sh summarize-network-test.py
```

Required on both DGX Spark nodes:

```bash
sudo apt-get install -y iperf3 ethtool iproute2
```

`nstat` is normally provided by `iproute2`.

Configure SSH key authentication first:

```bash
ssh spark-b true
```

## Example

Forward, one stream:

```bash
./run-network-test.sh \
  --test-id tcp-p1-forward \
  --local-iface enp1s0f1np1 \
  --local-ip 192.0.2.1 \
  --remote-host spark-b \
  --remote-iface enp1s0f1np1 \
  --remote-ip 192.0.2.2 \
  --streams 1 \
  --duration 30 \
  --omit 5
```

Forward, four streams:

```bash
./run-network-test.sh \
  --test-id tcp-p4-forward \
  --local-iface enp1s0f1np1 \
  --local-ip 192.0.2.1 \
  --remote-host spark-b \
  --remote-iface enp1s0f1np1 \
  --remote-ip 192.0.2.2 \
  --streams 4 \
  --duration 30 \
  --omit 5
```

Reverse, four streams:

```bash
./run-network-test.sh \
  --test-id tcp-p4-reverse \
  --local-iface enp1s0f1np1 \
  --local-ip 192.0.2.1 \
  --remote-host spark-b \
  --remote-iface enp1s0f1np1 \
  --remote-ip 192.0.2.2 \
  --streams 4 \
  --duration 30 \
  --omit 5 \
  --reverse
```

## Result layout

```text
results/network/
└── 20260802T131500Z-tcp-p4-forward/
    ├── command.txt
    ├── metadata.env
    ├── iperf3.json
    ├── iperf3.stderr
    ├── iperf3.exit-code
    ├── summary.json
    ├── summary.md
    ├── SHA256SUMS
    ├── local/
    │   ├── before-ethtool.stats
    │   ├── after-ethtool.stats
    │   ├── before-nstat.txt
    │   └── ...
    └── remote/
        ├── before-ethtool.stats
        ├── after-ethtool.stats
        ├── before-nstat.txt
        └── ...
```

## Status logic

- `FAIL`: `iperf3` returned a non-zero exit code.
- `WARN`: test completed, but retransmissions or selected error/drop counters
  increased.
- `PASS`: test completed and no selected error/drop counter increased.

A `WARN` does not automatically mean hardware failure. For example,
`rx_corrected_bits_phy` is an FEC correction counter and must be interpreted
using repeated runs and related uncorrectable-error counters.
