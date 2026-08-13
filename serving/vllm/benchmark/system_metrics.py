#!/usr/bin/env python3
"""Sample container cgroup, host memory/reclaim, and NVIDIA telemetry."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import json
import math
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from benchmark_utils import append_jsonl, utc_now

STOP = threading.Event()
PROC_ROOT = Path("/proc")
MIB_BYTES = 1024 * 1024
UNSUPPORTED_VALUES = {"N/A", "[N/A]", "Not Supported", "[Not Supported]"}
CGROUP_ROOT = Path("/sys/fs/cgroup")


def read_int(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not value or value == "max":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def key_values(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        parts = line.split()
        if len(parts) == 2:
            try:
                values[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return values


def resolve_container_cgroup(container_name: str) -> tuple[str, Path]:
    process = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Pid}} {{.Id}}", container_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"docker inspect failed: {process.stderr.strip() or process.stdout.strip()}"
        )
    parts = process.stdout.strip().split()
    if len(parts) != 2 or not parts[0].isdigit() or int(parts[0]) <= 0:
        raise RuntimeError(f"unexpected docker inspect output: {process.stdout.strip()}")
    pid, container_id = parts
    cgroup_file = PROC_ROOT / pid / "cgroup"
    for line in cgroup_file.read_text(encoding="utf-8").splitlines():
        hierarchy, _controllers, relative = line.split(":", 2)
        if hierarchy == "0":
            path = CGROUP_ROOT / relative.lstrip("/")
            if not path.is_dir():
                raise RuntimeError(f"resolved cgroup directory does not exist: {path}")
            return container_id, path
    raise RuntimeError(f"cgroup v2 path not found for container PID {pid}")


def meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        parts = raw.split()
        if parts and parts[0].isdigit():
            multiplier = 1024 if len(parts) > 1 and parts[1] == "kB" else 1
            values[key] = int(parts[0]) * multiplier
    return values


def vmstat() -> dict[str, int]:
    return key_values(Path("/proc/vmstat"))


def optional_float(value: str) -> float | None:
    normalized = value.strip()
    if not normalized or normalized in UNSUPPORTED_VALUES:
        return None
    try:
        parsed = float(normalized)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _device_gpu_sample(
    gpu_index: int,
) -> tuple[dict[str, float | str | None], str | None]:
    empty = {
        "gpu_utilization_percent": None,
        "gpu_fb_memory_status": "error",
        "gpu_memory_used_mib": None,
        "gpu_temperature_c": None,
        "gpu_power_watts": None,
    }
    if shutil.which("nvidia-smi") is None:
        return empty, "nvidia-smi is unavailable"
    process = subprocess.run(
        [
            "nvidia-smi",
            f"--id={gpu_index}",
            "--query-gpu=utilization.gpu,memory.used,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if process.returncode != 0:
        return empty, f"nvidia-smi device query failed: {process.stderr.strip()}"
    rows = list(csv.reader(process.stdout.splitlines()))
    if not rows or len(rows[0]) < 4:
        return empty, f"unexpected nvidia-smi output: {process.stdout.strip()}"
    values = [optional_float(value) for value in rows[0][:4]]
    raw_memory = rows[0][1].strip()
    if raw_memory in UNSUPPORTED_VALUES:
        memory_status = "unsupported"
        memory_error = None
    elif values[1] is not None and values[1] >= 0:
        memory_status = "ok"
        memory_error = None
    else:
        memory_status = "error"
        memory_error = f"invalid framebuffer memory value: {raw_memory!r}"
    return {
        "gpu_utilization_percent": values[0],
        "gpu_fb_memory_status": memory_status,
        "gpu_memory_used_mib": values[1] if memory_status == "ok" else None,
        "gpu_temperature_c": values[2],
        "gpu_power_watts": values[3],
    }, memory_error


def _pid_cgroup_relative(pid: int, proc_root: Path) -> Path:
    lines = (proc_root / str(pid) / "cgroup").read_text(
        encoding="utf-8"
    ).splitlines()
    for line in lines:
        hierarchy, _controllers, relative = line.split(":", 2)
        if hierarchy == "0":
            return Path(relative.lstrip("/"))
    raise OSError(f"cgroup v2 path not found for PID {pid}")


def _parse_process_memory_bytes(value: str) -> tuple[int | None, str | None]:
    normalized = value.strip()
    if normalized in UNSUPPORTED_VALUES:
        return None, f"process memory is unsupported: {normalized}"
    try:
        memory_bytes = Decimal(normalized) * MIB_BYTES
    except InvalidOperation:
        return None, f"invalid process memory value: {normalized!r}"
    if not memory_bytes.is_finite() or memory_bytes < 0:
        return None, f"invalid process memory value: {normalized!r}"
    integral_bytes = memory_bytes.to_integral_value()
    if memory_bytes != integral_bytes:
        return None, f"process memory is not an integral byte count: {normalized!r}"
    return int(integral_bytes), None


def _query_compute_process_rows(
    gpu_index: int,
) -> tuple[list[tuple[int, str]] | None, str | None]:
    try:
        process = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu_index}",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"nvidia-smi process query failed: {exc}"
    if process.returncode != 0:
        return None, f"nvidia-smi process query failed: {process.stderr.strip()}"
    rows: list[tuple[int, str]] = []
    for row in csv.reader(process.stdout.splitlines()):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) < 2:
            return None, f"unexpected nvidia-smi process output: {process.stdout.strip()}"
        raw_pid = row[0].strip()
        if not raw_pid.isdigit() or int(raw_pid) <= 0:
            return None, f"invalid NVIDIA process PID: {raw_pid!r}"
        rows.append((int(raw_pid), row[1].strip()))
    return rows, None


def container_nvml_process_memory_used_bytes(
    *,
    gpu_index: int,
    cgroup_path: Path,
    proc_root: Path = PROC_ROOT,
) -> tuple[int | None, str | None]:
    try:
        target_relative = cgroup_path.relative_to(CGROUP_ROOT)
    except ValueError:
        return None, f"container cgroup is outside {CGROUP_ROOT}: {cgroup_path}"
    if target_relative == Path("."):
        return None, "refusing to attribute all host GPU processes to root cgroup"

    for attempt in range(2):
        rows, query_error = _query_compute_process_rows(gpu_index)
        if query_error:
            return None, query_error
        total = 0
        race = False
        observed: dict[int, str] = {}
        for pid, raw_memory in rows or []:
            previous = observed.get(pid)
            if previous is not None:
                if previous != raw_memory:
                    return None, f"conflicting NVIDIA memory values for PID {pid}"
                continue
            observed[pid] = raw_memory
            try:
                relative = _pid_cgroup_relative(pid, proc_root)
            except FileNotFoundError:
                race = True
                break
            except (OSError, ValueError) as exc:
                return None, f"cannot resolve cgroup for GPU PID {pid}: {exc}"
            if relative != target_relative and target_relative not in relative.parents:
                continue
            memory_bytes, parse_error = _parse_process_memory_bytes(raw_memory)
            if parse_error:
                return None, f"GPU PID {pid}: {parse_error}"
            total += memory_bytes or 0
        if not race:
            return total, None
        if attempt == 1:
            return None, "GPU process exited while resolving its container cgroup"
    raise AssertionError("unreachable")


def gpu_sample(
    gpu_index: int,
    cgroup_path: Path,
    *,
    proc_root: Path = PROC_ROOT,
) -> tuple[dict[str, float | int | str | None], list[str]]:
    try:
        device, device_error = _device_gpu_sample(gpu_index)
    except (OSError, subprocess.SubprocessError) as exc:
        device = {
            "gpu_utilization_percent": None,
            "gpu_fb_memory_status": "error",
            "gpu_memory_used_mib": None,
            "gpu_temperature_c": None,
            "gpu_power_watts": None,
        }
        device_error = f"nvidia-smi device query failed: {exc}"
    errors = [device_error] if device_error else []
    process_memory = None
    if shutil.which("nvidia-smi") is not None:
        process_memory, process_error = container_nvml_process_memory_used_bytes(
            gpu_index=gpu_index, cgroup_path=cgroup_path, proc_root=proc_root
        )
        if process_error:
            errors.append(f"container NVML process GPU memory: {process_error}")
    return {
        **device,
        "container_nvml_process_gpu_memory_used_bytes": process_memory,
    }, errors


def system_record(
    *,
    run_id: str,
    cgroup_path: Path,
    gpu_index: int,
    sampler_started_ns: int,
    interval: float,
) -> dict[str, Any]:
    timestamp = utc_now()
    observed_ns = time.monotonic_ns()
    errors: list[str] = []
    started = time.monotonic()

    memory_current = read_int(cgroup_path / "memory.current")
    if memory_current is None:
        errors.append("cgroup memory.current is unavailable")
    memory_events = key_values(cgroup_path / "memory.events")
    try:
        host_memory = meminfo()
    except OSError as exc:
        host_memory = {}
        errors.append(f"host meminfo failed: {exc}")
    try:
        host_vmstat = vmstat()
    except OSError as exc:
        host_vmstat = {}
        errors.append(f"host vmstat failed: {exc}")
    try:
        gpu, gpu_errors = gpu_sample(gpu_index, cgroup_path)
    except (OSError, subprocess.SubprocessError) as exc:
        gpu = {
            "gpu_utilization_percent": None,
            "gpu_fb_memory_status": "error",
            "gpu_memory_used_mib": None,
            "gpu_temperature_c": None,
            "gpu_power_watts": None,
            "container_nvml_process_gpu_memory_used_bytes": None,
        }
        gpu_errors = [f"GPU sample failed: {exc}"]
    errors.extend(gpu_errors)

    return {
        "schema_version": 1,
        "record_type": "system_sample",
        "run_id": run_id,
        "timestamp_utc": timestamp,
        "monotonic_ns": observed_ns,
        "elapsed_seconds": (observed_ns - sampler_started_ns) / 1_000_000_000,
        "configured_interval_seconds": interval,
        "sample_duration_seconds": time.monotonic() - started,
        "sample_success": not errors,
        "errors": errors,
        "cgroup_memory_current_bytes": memory_current,
        "cgroup_memory_peak_bytes": read_int(cgroup_path / "memory.peak"),
        "cgroup_memory_high_bytes": read_int(cgroup_path / "memory.high"),
        "cgroup_memory_max_bytes": read_int(cgroup_path / "memory.max"),
        "cgroup_memory_swap_current_bytes": read_int(
            cgroup_path / "memory.swap.current"
        ),
        "cgroup_memory_events_high_total": memory_events.get("high"),
        "cgroup_memory_events_max_total": memory_events.get("max"),
        "cgroup_memory_events_oom_total": memory_events.get("oom"),
        "cgroup_memory_events_oom_kill_total": memory_events.get("oom_kill"),
        "host_memory_total_bytes": host_memory.get("MemTotal"),
        "host_memory_available_bytes": host_memory.get("MemAvailable"),
        "host_swap_total_bytes": host_memory.get("SwapTotal"),
        "host_swap_free_bytes": host_memory.get("SwapFree"),
        "host_pgscan_kswapd_total": host_vmstat.get("pgscan_kswapd"),
        "host_pgsteal_kswapd_total": host_vmstat.get("pgsteal_kswapd"),
        "host_pswpin_total": host_vmstat.get("pswpin"),
        "host_pswpout_total": host_vmstat.get("pswpout"),
        **gpu,
    }


def positive(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=positive, default=1.0)
    parser.add_argument("--gpu-index", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if args.gpu_index < 0:
        raise SystemExit("--gpu-index cannot be negative")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    try:
        container_id, cgroup_path = resolve_container_cgroup(args.container)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        raise SystemExit(f"cannot resolve container cgroup: {exc}") from exc
    print(
        json.dumps(
            {
                "container_id": container_id,
                "cgroup_version": 2,
                "sampling_interval_seconds": args.interval,
            },
            sort_keys=True,
        )
    )
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    sampler_started_ns = time.monotonic_ns()
    deadline = time.monotonic()
    while not STOP.is_set():
        append_jsonl(
            args.output,
            system_record(
                run_id=args.run_id,
                cgroup_path=cgroup_path,
                gpu_index=args.gpu_index,
                sampler_started_ns=sampler_started_ns,
                interval=args.interval,
            ),
        )
        deadline += args.interval
        STOP.wait(max(0.0, deadline - time.monotonic()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
