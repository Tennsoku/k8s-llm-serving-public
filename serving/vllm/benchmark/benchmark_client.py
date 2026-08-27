#!/usr/bin/env python3
"""Run one warm-up or measured M1 streaming benchmark case."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import aiohttp

from benchmark_config import ConfigError, load_config, render_prompt
from benchmark_utils import append_jsonl, measure_request, utc_now

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
CACHE_SALT_DERIVATION = "sha256-run-case-phase-index-v1"
RUN_SHARED_CACHE_SALT_DERIVATION = "sha256-run-v1"


def positive(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def derive_cache_salt(
    run_id: str,
    case_id: str,
    phase: str,
    request_index: int,
    derivation: str,
    mode: str = "request_unique",
) -> str:
    if mode == "request_unique" and derivation == CACHE_SALT_DERIVATION:
        identity = f"{run_id}:{case_id}:{phase}:{request_index}"
    elif mode == "run_shared" and derivation == RUN_SHARED_CACHE_SALT_DERIVATION:
        identity = run_id
    else:
        raise ValueError(f"unsupported cache identity: {mode}/{derivation}")
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-events", type=Path, required=True)
    parser.add_argument("--progress-interval", type=positive, default=10.0)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--measured", dest="measured", action="store_true")
    mode.add_argument("--warmup", dest="measured", action="store_false")
    return parser.parse_args()


def report_progress(
    *,
    case_id: str,
    completed: int,
    planned: int,
    successful: int,
    failed: int,
    elapsed_seconds: float,
    phase: str = "running",
) -> None:
    requests_per_second = completed / elapsed_seconds if elapsed_seconds > 0 else 0.0
    eta_seconds = (
        (planned - completed) / requests_per_second
        if completed < planned and requests_per_second > 0
        else 0.0
    )
    print(
        f"phase={phase} case_id={case_id} completed={completed}/{planned} "
        f"successful={successful} failed={failed} "
        f"elapsed_seconds={elapsed_seconds:.1f} "
        f"request_throughput_rps={requests_per_second:.3f} "
        f"eta_seconds={eta_seconds:.1f}",
        file=sys.stderr,
        flush=True,
    )


def case_event(
    *,
    event_type: str,
    run_id: str,
    case_id: str,
    measured: bool,
    model: str,
    concurrency: int,
    repetition: int,
    planned_requests: int,
    timestamp_utc: str,
    monotonic_ns: int,
    wall_time_seconds: float | None,
    completed_requests: int | None,
    successful_requests: int | None,
    failed_requests: int | None,
    outcome: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_type": "case_event",
        "event_type": event_type,
        "run_id": run_id,
        "case_id": case_id,
        "measured": measured,
        "model": model,
        "concurrency": concurrency,
        "repetition": repetition,
        "planned_requests": planned_requests,
        "timestamp_utc": timestamp_utc,
        "monotonic_ns": monotonic_ns,
        "wall_time_seconds": wall_time_seconds,
        "completed_requests": completed_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "outcome": outcome,
    }


async def run_case(args: argparse.Namespace, config: dict[str, Any]) -> int:
    workload = config["workload"]
    sampling = config["sampling"]
    cache_identity = workload["cache_identity"]
    payload = {
        "chat_template_kwargs": {"enable_thinking": False},  # hardcode the chat template kwargs to disable thinking for now
        "model": args.model,
        "max_tokens": workload["max_output_tokens"],
        "temperature": sampling["temperature"],
        "seed": sampling["seed"],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    url = f"{args.base_url.rstrip('/')}/v1/chat/completions"
    started_ns = time.monotonic_ns()
    append_jsonl(
        args.case_events,
        case_event(
            event_type="start",
            run_id=args.run_id,
            case_id=args.case_id,
            measured=args.measured,
            model=args.model,
            concurrency=args.concurrency,
            repetition=args.repetition,
            planned_requests=args.requests,
            timestamp_utc=utc_now(),
            monotonic_ns=started_ns,
            wall_time_seconds=None,
            completed_requests=None,
            successful_requests=None,
            failed_requests=None,
            outcome="running",
        ),
    )
    report_progress(
        case_id=args.case_id,
        completed=0,
        planned=args.requests,
        successful=0,
        failed=0,
        elapsed_seconds=0.0,
        phase="started",
    )

    gate = asyncio.Semaphore(args.concurrency)
    records: list[dict[str, Any]] = []
    successful_so_far = 0
    failed_so_far = 0
    next_progress_ns = started_ns + int(args.progress_interval * 1_000_000_000)
    connector = aiohttp.TCPConnector(limit=args.concurrency)
    request_phase = "measured" if args.measured else "warmup"

    async with aiohttp.ClientSession(connector=connector) as session:
        async def one(index: int) -> dict[str, Any]:
            request_id = f"{args.run_id}-{args.case_id}-request-{index:06d}"
            request_payload = dict(payload)
            prompt = render_prompt(config, args.case_id, index)
            request_payload["messages"] = [{"role": "user", "content": prompt}]
            request_payload["cache_salt"] = derive_cache_salt(
                args.run_id,
                args.case_id,
                request_phase,
                index,
                cache_identity["derivation"],
                cache_identity["mode"],
            )
            async with gate:
                record = await measure_request(
                    session,
                    url=url,
                    payload=request_payload,
                    run_id=args.run_id,
                    case_id=args.case_id,
                    measured=args.measured,
                    model=args.model,
                    request_id=request_id,
                    request_index=index,
                    concurrency=args.concurrency,
                    repetition=args.repetition,
                    timeout_seconds=float(workload["request_timeout_seconds"]),
                )
            record["cache_salt"] = request_payload["cache_salt"]
            return record

        tasks = [
            asyncio.create_task(one(index)) for index in range(1, args.requests + 1)
        ]
        for task in asyncio.as_completed(tasks):
            record = await task
            append_jsonl(args.output, record)
            records.append(record)
            if record["success"] is True:
                successful_so_far += 1
            else:
                failed_so_far += 1
            observed_ns = time.monotonic_ns()
            if observed_ns >= next_progress_ns or len(records) == args.requests:
                report_progress(
                    case_id=args.case_id,
                    completed=len(records),
                    planned=args.requests,
                    successful=successful_so_far,
                    failed=failed_so_far,
                    elapsed_seconds=(observed_ns - started_ns) / 1_000_000_000,
                )
                next_progress_ns = observed_ns + int(
                    args.progress_interval * 1_000_000_000
                )

    ended_ns = time.monotonic_ns()
    successful = sum(record["success"] is True for record in records)
    failed = len(records) - successful
    if not records:
        outcome = "failed"
    elif failed:
        outcome = "partial_failure"
    else:
        outcome = "success"
    end_event = case_event(
        event_type="end",
        run_id=args.run_id,
        case_id=args.case_id,
        measured=args.measured,
        model=args.model,
        concurrency=args.concurrency,
        repetition=args.repetition,
        planned_requests=args.requests,
        timestamp_utc=utc_now(),
        monotonic_ns=ended_ns,
        wall_time_seconds=(ended_ns - started_ns) / 1_000_000_000,
        completed_requests=len(records),
        successful_requests=successful,
        failed_requests=failed,
        outcome=outcome,
    )
    append_jsonl(args.case_events, end_event)
    print(json.dumps(end_event, sort_keys=True))
    if failed == 0 and len(records) == args.requests:
        return 0
    if any(record.get("timeout") is True for record in records):
        return 2
    return 1


def main() -> int:
    args = arguments()
    for name in ("run_id", "case_id"):
        value = getattr(args, name)
        if not SAFE_ID.fullmatch(value):
            raise SystemExit(f"--{name.replace('_', '-')} contains unsafe characters")
    if args.concurrency < 1 or args.requests < 1:
        raise SystemExit("--concurrency and --requests must be positive")
    if args.concurrency > args.requests:
        raise SystemExit("--concurrency cannot exceed --requests")
    if args.repetition < 0:
        raise SystemExit("--repetition cannot be negative")
    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as exc:
        raise SystemExit(f"invalid benchmark config: {exc}") from exc
    return asyncio.run(run_case(args, config))


if __name__ == "__main__":
    raise SystemExit(main())
