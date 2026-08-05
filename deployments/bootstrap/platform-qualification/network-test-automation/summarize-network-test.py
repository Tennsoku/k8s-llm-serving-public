#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


IMPORTANT_COUNTERS = [
    "rx_packets",
    "rx_bytes",
    "tx_packets",
    "tx_bytes",
    "rx_out_of_buffer",
    "rx_buff_alloc_err",
    "rx_wqe_err",
    "rx_oversize_pkts_sw_drop",
    "tx_queue_dropped",
    "tx_cqe_err",
    "tx_recover",
    "rx_recover",
    "rx_crc_errors_phy",
    "rx_symbol_err_phy",
    "rx_pcs_symbol_err_phy",
    "rx_in_range_len_errors_phy",
    "rx_out_of_range_len_phy",
    "rx_discards_phy",
    "tx_discards_phy",
    "tx_errors_phy",
    "rx_undersize_pkts_phy",
    "rx_oversize_pkts_phy",
    "rx_fragments_phy",
    "rx_jabbers_phy",
    "link_down_events_phy",
    "rx_corrected_bits_phy",
    "rx_err_lane_0_phy",
    "rx_err_lane_1_phy",
    "rx_err_lane_2_phy",
    "rx_err_lane_3_phy",
    "total_success_recovery_phy",
    "rx_pause_ctrl_phy",
    "tx_pause_ctrl_phy",
    "rx_global_pause",
    "tx_global_pause",
    "rx_global_pause_duration",
    "tx_global_pause_duration",
]

NSTAT_COUNTERS = [
    "TcpRetransSegs",
    "TcpExtTCPLostRetransmit",
    "TcpExtTCPTimeouts",
    "TcpExtTCPSynRetrans",
    "TcpExtTCPFastRetrans",
    "TcpExtTCPSpuriousRTOs",
    "IpInDiscards",
    "IpOutDiscards",
]


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        result[key] = value
    return result


def parse_key_value_stats(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    if not path.exists():
        return result

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = raw.split()
        if len(fields) < 2:
            continue
        try:
            result[fields[0]] = int(fields[1])
        except ValueError:
            continue
    return result


def delta(before: dict[str, int], after: dict[str, int], keys: list[str]) -> dict[str, int | None]:
    return {
        key: (after[key] - before[key]) if key in before and key in after else None
        for key in keys
    }


def parse_nstat(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    if not path.exists():
        return result

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = raw.split()
        if len(fields) < 2:
            continue
        try:
            result[fields[0]] = int(fields[1])
        except ValueError:
            continue
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def gbps(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return value / 1_000_000_000


def read_exit_code(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def extract_link_details(path: Path) -> dict[str, str | None]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

    def field(name: str) -> str | None:
        match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", text, re.MULTILINE)
        return match.group(1) if match else None

    return {
        "speed": field("Speed"),
        "duplex": field("Duplex"),
        "port": field("Port"),
        "link_detected": field("Link detected"),
    }


def status_from_deltas(local: dict[str, int | None], remote: dict[str, int | None],
                       retransmits: int | None, exit_code: int | None) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if exit_code not in (0, None):
        reasons.append(f"iperf3 exited with code {exit_code}")

    hard_error_keys = [
        "rx_crc_errors_phy",
        "rx_symbol_err_phy",
        "rx_pcs_symbol_err_phy",
        "rx_discards_phy",
        "tx_discards_phy",
        "tx_errors_phy",
        "link_down_events_phy",
    ]

    for side_name, counters in (("local", local), ("remote", remote)):
        for key in hard_error_keys:
            value = counters.get(key)
            if isinstance(value, int) and value > 0:
                reasons.append(f"{side_name} {key} increased by {value}")

        for key in ("rx_out_of_buffer", "rx_buff_alloc_err", "rx_wqe_err", "tx_queue_dropped"):
            value = counters.get(key)
            if isinstance(value, int) and value > 0:
                reasons.append(f"{side_name} {key} increased by {value}")

    if isinstance(retransmits, int) and retransmits > 0:
        reasons.append(f"TCP retransmissions: {retransmits}")

    if exit_code not in (0, None):
        return "FAIL", reasons

    if reasons:
        return "WARN", reasons

    return "PASS", ["No selected error counter increased during the measured run."]


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    metadata = parse_env(run_dir / "metadata.env")

    iperf = load_json(run_dir / "iperf3.json")
    exit_code = read_exit_code(run_dir / "iperf3.exit-code")

    local_before = parse_key_value_stats(run_dir / "local/before-ethtool.stats")
    local_after = parse_key_value_stats(run_dir / "local/after-ethtool.stats")
    remote_before = parse_key_value_stats(run_dir / "remote/before-ethtool.stats")
    remote_after = parse_key_value_stats(run_dir / "remote/after-ethtool.stats")

    local_delta = delta(local_before, local_after, IMPORTANT_COUNTERS)
    remote_delta = delta(remote_before, remote_after, IMPORTANT_COUNTERS)

    local_nstat_before = parse_nstat(run_dir / "local/before-nstat.txt")
    local_nstat_after = parse_nstat(run_dir / "local/after-nstat.txt")
    remote_nstat_before = parse_nstat(run_dir / "remote/before-nstat.txt")
    remote_nstat_after = parse_nstat(run_dir / "remote/after-nstat.txt")

    local_nstat_delta = delta(local_nstat_before, local_nstat_after, NSTAT_COUNTERS)
    remote_nstat_delta = delta(remote_nstat_before, remote_nstat_after, NSTAT_COUNTERS)

    sent = nested(iperf, "end", "sum_sent", default={}) or {}
    received = nested(iperf, "end", "sum_received", default={}) or {}
    cpu = nested(iperf, "end", "cpu_utilization_percent", default={}) or {}
    test_start = nested(iperf, "start", "test_start", default={}) or {}

    sender_gbps = gbps(sent.get("bits_per_second"))
    receiver_gbps = gbps(received.get("bits_per_second"))
    retransmits = sent.get("retransmits")
    if not isinstance(retransmits, int):
        retransmits = None

    local_link = extract_link_details(run_dir / "local/before-ethtool-link.txt")
    remote_link = extract_link_details(run_dir / "remote/before-ethtool-link.txt")

    status, reasons = status_from_deltas(
        local_delta,
        remote_delta,
        retransmits,
        exit_code,
    )

    summary = {
        "status": status,
        "reasons": reasons,
        "metadata": metadata,
        "iperf3": {
            "exit_code": exit_code,
            "protocol": test_start.get("protocol"),
            "streams": test_start.get("num_streams"),
            "duration_seconds": test_start.get("duration"),
            "reverse": metadata.get("REVERSE") == "1",
            "sender_gbps": sender_gbps,
            "receiver_gbps": receiver_gbps,
            "retransmits": retransmits,
            "local_cpu_percent": cpu.get("host_total"),
            "remote_cpu_percent": cpu.get("remote_total"),
        },
        "links": {
            "local": local_link,
            "remote": remote_link,
        },
        "nic_delta": {
            "local": local_delta,
            "remote": remote_delta,
        },
        "nstat_delta": {
            "local": local_nstat_delta,
            "remote": remote_nstat_delta,
        },
    }

    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    error_keys = [
        "rx_out_of_buffer",
        "rx_buff_alloc_err",
        "rx_wqe_err",
        "tx_queue_dropped",
        "tx_cqe_err",
        "rx_crc_errors_phy",
        "rx_symbol_err_phy",
        "rx_pcs_symbol_err_phy",
        "rx_discards_phy",
        "tx_discards_phy",
        "tx_errors_phy",
        "link_down_events_phy",
        "rx_corrected_bits_phy",
        "rx_err_lane_0_phy",
        "rx_err_lane_1_phy",
        "rx_pause_ctrl_phy",
        "tx_pause_ctrl_phy",
        "rx_global_pause",
        "tx_global_pause",
    ]

    rows = []
    for key in error_keys:
        rows.append(
            f"| `{key}` | {fmt(local_delta.get(key), 0)} | "
            f"{fmt(remote_delta.get(key), 0)} |"
        )

    nstat_rows = []
    for key in NSTAT_COUNTERS:
        nstat_rows.append(
            f"| `{key}` | {fmt(local_nstat_delta.get(key), 0)} | "
            f"{fmt(remote_nstat_delta.get(key), 0)} |"
        )

    reason_lines = "\n".join(f"- {reason}" for reason in reasons)

    markdown = f"""# Network Baseline Summary

## Result

**Status: {status}**

{reason_lines}

## Experiment

| Field | Value |
|---|---|
| Test ID | `{metadata.get('TEST_ID', 'N/A')}` |
| Timestamp UTC | `{metadata.get('TIMESTAMP_UTC', 'N/A')}` |
| Local | `{metadata.get('LOCAL_HOST', 'N/A')}` / `{metadata.get('LOCAL_IFACE', 'N/A')}` / `{metadata.get('LOCAL_IP', 'N/A')}` |
| Remote | `{metadata.get('REMOTE_HOST', 'N/A')}` / `{metadata.get('REMOTE_IFACE', 'N/A')}` / `{metadata.get('REMOTE_IP', 'N/A')}` |
| Direction | `{'reverse' if metadata.get('REVERSE') == '1' else 'forward'}` |
| Parallel streams | `{metadata.get('STREAMS', 'N/A')}` |
| Duration | `{metadata.get('DURATION_SECONDS', 'N/A')} s` |
| Omitted warm-up | `{metadata.get('OMIT_SECONDS', 'N/A')} s` |
| iperf3 exit code | `{fmt(exit_code, 0)}` |

## Link

| Side | Speed | Duplex | Port | Link detected |
|---|---|---|---|---|
| Local | {fmt(local_link.get('speed'))} | {fmt(local_link.get('duplex'))} | {fmt(local_link.get('port'))} | {fmt(local_link.get('link_detected'))} |
| Remote | {fmt(remote_link.get('speed'))} | {fmt(remote_link.get('duplex'))} | {fmt(remote_link.get('port'))} | {fmt(remote_link.get('link_detected'))} |

## TCP Throughput

| Metric | Value |
|---|---:|
| Sender throughput | {fmt(sender_gbps)} Gbit/s |
| Receiver throughput | {fmt(receiver_gbps)} Gbit/s |
| Retransmissions | {fmt(retransmits, 0)} |
| Local CPU | {fmt(cpu.get('host_total'))}% |
| Remote CPU | {fmt(cpu.get('remote_total'))}% |

## Selected NIC Counter Delta

| Counter | Local delta | Remote delta |
|---|---:|---:|
{chr(10).join(rows)}

## Selected Kernel Network Counter Delta

| Counter | Local delta | Remote delta |
|---|---:|---:|
{chr(10).join(nstat_rows)}

## Interpretation Rules

- `rx_crc_errors_phy`, symbol/PCS errors, physical discards and
  `link_down_events_phy` should normally remain at zero delta.
- `rx_out_of_buffer` indicates receive-path buffer pressure when it increases.
- `rx_corrected_bits_phy` is an FEC correction counter. A non-zero delta is not
  automatically packet loss, but should be compared across repeated runs.
- TCP retransmissions should be interpreted together with throughput stability,
  NIC drops, CPU usage and repeated-run variance.
- The primary throughput value is the receiver-side `iperf3` result.
- Raw files and failed runs are intentionally retained.

## Evidence

- `iperf3.json`
- `iperf3.stderr`
- `command.txt`
- `metadata.env`
- `local/before-*`, `local/after-*`
- `remote/before-*`, `remote/after-*`
- `summary.json`
- `SHA256SUMS`
"""

    (run_dir / "summary.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
