#!/usr/bin/env python3
"""Benchmark an OpenAI-compatible chat-completions endpoint."""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "shared" / "scripts"
sys.path.insert(0, str(SHARED))
from benchmark_utils import RequestResult, percentile, post_chat  # noqa: E402


FIELDS = ["timestamp", "model", "concurrency", "request_count", "successful_requests", "failed_requests", "wall_time_seconds", "throughput_rps", "avg_latency_seconds", "p50_latency_seconds", "p95_latency_seconds", "p99_latency_seconds"]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--prompt", default="Explain continuous batching in two sentences.")
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "baseline.csv")
    return parser.parse_args()


async def execute(url: str, payload: dict, count: int, concurrency: int, timeout: float) -> list[RequestResult]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one() -> RequestResult:
        async with semaphore:
            return await asyncio.to_thread(post_chat, url, payload, timeout)

    return await asyncio.gather(*(one() for _ in range(count)))


async def run(args: argparse.Namespace) -> int:
    for name in ("concurrency", "requests", "max_tokens"):
        if getattr(args, name) < 1:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    payload = {"model": args.model, "messages": [{"role": "user", "content": args.prompt}], "max_tokens": args.max_tokens, "temperature": 0, "seed": 42}
    url = f"{args.base_url.rstrip('/')}/v1/chat/completions"

    if args.warmup:
        print(f"Warm-up: {args.warmup} unmeasured request(s)")
        warm = await execute(url, payload, args.warmup, min(args.concurrency, args.warmup), args.timeout)
        if not all(item.successful for item in warm):
            for item in warm:
                if not item.successful:
                    print(f"warm-up failure: status={item.status} {item.error}", file=sys.stderr)
            return 1

    started = time.perf_counter()
    results = await execute(url, payload, args.requests, args.concurrency, args.timeout)
    wall = time.perf_counter() - started
    successful = [item for item in results if item.successful]
    latencies = [item.latency_seconds for item in successful]
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(), "model": args.model,
        "concurrency": args.concurrency, "request_count": args.requests,
        "successful_requests": len(successful), "failed_requests": len(results) - len(successful),
        "wall_time_seconds": f"{wall:.6f}", "throughput_rps": f"{len(successful) / wall:.6f}",
        "avg_latency_seconds": f"{sum(latencies) / len(latencies):.6f}" if latencies else "0",
        "p50_latency_seconds": f"{percentile(latencies, .50):.6f}",
        "p95_latency_seconds": f"{percentile(latencies, .95):.6f}",
        "p99_latency_seconds": f"{percentile(latencies, .99):.6f}",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    exists = args.output.exists() and args.output.stat().st_size > 0
    with args.output.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    print(" ".join(f"{key}={value}" for key, value in row.items()))
    for index, item in enumerate(results):
        if not item.successful:
            print(f"request[{index}] status={item.status} error={item.error}", file=sys.stderr)
    print(f"CSV: {args.output}")
    return 0 if len(successful) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(arguments())))
