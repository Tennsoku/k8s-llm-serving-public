#!/usr/bin/env python3
"""Capture or periodically sample the vLLM Prometheus exposition."""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from pathlib import Path
from typing import Any

from benchmark_utils import append_jsonl, utc_now
from metrics_utils import scrape_exposition, snapshot_semantics

STOP = threading.Event()


def runtime_record(
    *,
    run_id: str,
    base_url: str,
    model_name: str | None,
    sampler_started_ns: int,
    interval: float,
    scrape_timeout: float = 10.0,
) -> dict[str, Any]:
    timestamp = utc_now()
    observed_ns = time.monotonic_ns()
    text, status, duration, error = scrape_exposition(base_url, scrape_timeout)
    values: dict[str, float | None]
    names: dict[str, str | None]
    if text is not None and status == 200 and error is None:
        values, names = snapshot_semantics(text, model_name)
    else:
        values = {
            key: None
            for key in (
                "running_requests",
                "waiting_requests",
                "kv_cache_usage_ratio",
                "preemption_events_total",
                "prompt_tokens_total",
                "generation_tokens_total",
                "request_success_total",
                "prefix_cache_queries_total",
                "prefix_cache_hits_total",
                "avg_prompt_throughput_tps",
                "avg_generation_throughput_tps",
            )
        }
        names = {key: None for key in values}
    return {
        "schema_version": 1,
        "record_type": "runtime_sample",
        "run_id": run_id,
        "timestamp_utc": timestamp,
        "monotonic_ns": observed_ns,
        "elapsed_seconds": (observed_ns - sampler_started_ns) / 1_000_000_000,
        "configured_interval_seconds": interval,
        "scrape_duration_seconds": duration,
        "scrape_success": text is not None and status == 200 and error is None,
        "http_status": status,
        "error": error,
        **values,
        "metric_names": names,
    }


def capture(args: argparse.Namespace) -> int:
    text, status, duration, error = scrape_exposition(
        args.base_url, args.timeout
    )
    if text is None or status != 200 or error is not None:
        raise SystemExit(
            f"metrics capture failed: status={status} "
            f"duration={duration:.3f}s error={error}"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
    print(
        f"metrics_capture={args.output} http_status={status} "
        f"duration_seconds={duration:.6f}"
    )
    return 0


def sample(args: argparse.Namespace) -> int:
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    sampler_started_ns = time.monotonic_ns()
    deadline = time.monotonic()
    while not STOP.is_set():
        append_jsonl(
            args.output,
            runtime_record(
                run_id=args.run_id,
                base_url=args.base_url,
                model_name=args.model_name,
                sampler_started_ns=sampler_started_ns,
                interval=args.interval,
            ),
        )
        deadline += args.interval
        STOP.wait(max(0.0, deadline - time.monotonic()))
    return 0


def wait_idle(args: argparse.Namespace) -> int:
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    sampler_started_ns = time.monotonic_ns()
    deadline = time.monotonic() + args.timeout
    stable = 0
    while time.monotonic() < deadline:
        remaining_seconds = deadline - time.monotonic()
        record = runtime_record(
            run_id=args.run_id,
            base_url=args.base_url,
            model_name=args.model_name,
            sampler_started_ns=sampler_started_ns,
            interval=args.interval,
            scrape_timeout=min(10.0, remaining_seconds),
        )
        append_jsonl(args.output, record)
        if not record["scrape_success"]:
            stable = 0
        elif (
            record["running_requests"] is None
            or record["waiting_requests"] is None
        ):
            raise SystemExit("running/waiting request metrics are unavailable")
        elif (
            record["running_requests"] == 0
            and record["waiting_requests"] == 0
        ):
            stable += 1
            if stable >= args.stable_samples:
                print(json.dumps(record, sort_keys=True))
                return 0
        else:
            stable = 0
        remaining_seconds = max(0.0, deadline - time.monotonic())
        time.sleep(min(args.interval, remaining_seconds))
    raise SystemExit(
        f"runtime did not remain idle for {args.stable_samples} samples "
        f"within {args.timeout} seconds"
    )


def positive(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--base-url", required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    capture_parser.add_argument("--timeout", type=positive, default=10.0)

    sample_parser = subparsers.add_parser("sample")
    sample_parser.add_argument("--base-url", required=True)
    sample_parser.add_argument("--run-id", required=True)
    sample_parser.add_argument("--model-name")
    sample_parser.add_argument("--output", type=Path, required=True)
    sample_parser.add_argument("--interval", type=positive, default=1.0)

    idle_parser = subparsers.add_parser("wait-idle")
    idle_parser.add_argument("--base-url", required=True)
    idle_parser.add_argument("--run-id", required=True)
    idle_parser.add_argument("--model-name")
    idle_parser.add_argument("--output", type=Path, required=True)
    idle_parser.add_argument("--interval", type=positive, default=0.5)
    idle_parser.add_argument("--timeout", type=positive, default=30.0)
    idle_parser.add_argument("--stable-samples", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if getattr(args, "stable_samples", 1) < 1:
        raise SystemExit("--stable-samples must be positive")
    if args.command == "capture":
        return capture(args)
    if args.command == "sample":
        signal.signal(signal.SIGINT, lambda *_: STOP.set())
        signal.signal(signal.SIGTERM, lambda *_: STOP.set())
        return sample(args)
    return wait_idle(args)


if __name__ == "__main__":
    raise SystemExit(main())
