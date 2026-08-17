#!/usr/bin/env python3
"""Run cache-isolated prefill/decode shapes and append aggregates to CSV."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "shared" / "scripts"
sys.path.insert(0, str(SHARED))
from benchmark_utils import RequestResult, percentile, post_chat  # noqa: E402

CASES = {
    "short-short": ("Explain PagedAttention in one sentence. " * 3, 32),
    "short-long": ("Write a detailed primer on LLM inference scheduling. " * 3, 512),
    "long-short": ("Explain the main inference bottleneck in this context: " + "Models process input tokens during prefill and output tokens during decode. " * 450, 32),
    "long-long": ("Write an analysis of this inference context: " + "Models process input tokens during prefill and output tokens during decode. " * 450, 512),
}
FIELDS = ["timestamp", "case_name", "model", "concurrency", "request_count", "input_tokens_per_request", "output_tokens_per_request", "wall_time_seconds", "request_throughput_rps", "input_token_throughput_tps", "output_token_throughput_tps", "avg_latency_seconds", "p50_latency_seconds", "p95_latency_seconds", "p99_latency_seconds", "peak_gpu_memory_mb", "avg_gpu_utilization_percent", "successful_requests", "failed_requests", "notes"]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--case", choices=["all", *CASES], default="all")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--requests", type=int, default=16)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--request-namespace", required=True, help="Unique namespace used to derive per-request vLLM cache_salt values")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--sample-interval", type=float, default=0.5)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "workload-results.csv")
    return parser.parse_args()


def request_payloads(args: argparse.Namespace, case_name: str, phase: str, count: int) -> list[dict]:
    prompt, max_tokens = CASES[case_name]
    return [
        {
            "model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "cache_salt": hashlib.sha256(
                f"{args.request_namespace}:{case_name}:{phase}:{index}".encode()
            ).hexdigest(),
            "max_tokens": max_tokens,
            "temperature": 0,
            "seed": 42,
        }
        for index in range(count)
    ]


async def requests(url: str, payloads: list[dict], concurrency: int, timeout: float) -> list[RequestResult]:
    gate = asyncio.Semaphore(concurrency)

    async def one(payload: dict) -> RequestResult:
        async with gate:
            return await asyncio.to_thread(post_chat, url, payload, timeout)

    return await asyncio.gather(*(one(payload) for payload in payloads))


async def sample_gpu(stop: asyncio.Event, gpu_index: int, interval: float) -> list[tuple[float, float]]:
    samples: list[tuple[float, float]] = []
    if not shutil.which("nvidia-smi"):
        return samples
    while not stop.is_set():
        process = await asyncio.create_subprocess_exec(
            "nvidia-smi", f"--id={gpu_index}", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        if process.returncode == 0:
            try:
                memory, utilization = stdout.decode().strip().split(",")[:2]
                samples.append((float(memory.strip()), float(utilization.strip())))
            except ValueError:
                pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    return samples


async def run_case(args: argparse.Namespace, case_name: str) -> tuple[dict[str, object], list[RequestResult]]:
    url = f"{args.base_url.rstrip('/')}/v1/chat/completions"
    if args.warmup:
        warm = await requests(
            url,
            request_payloads(args, case_name, "warmup", args.warmup),
            min(args.concurrency, args.warmup),
            args.timeout,
        )
        if not all(item.successful for item in warm):
            raise RuntimeError(f"warm-up failed for {case_name}: {warm[0].error}")

    stop = asyncio.Event()
    sampler = asyncio.create_task(sample_gpu(stop, args.gpu_index, args.sample_interval))
    started = time.perf_counter()
    payloads = request_payloads(args, case_name, "measured", args.requests)
    results = await requests(
        url,
        payloads,
        args.concurrency,
        args.timeout,
    )
    wall = time.perf_counter() - started
    stop.set()
    gpu = await sampler
    good = [item for item in results if item.successful]
    latencies = [item.latency_seconds for item in good]
    input_total = sum(item.input_tokens for item in good)
    output_total = sum(item.output_tokens for item in good)
    row: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(), "case_name": case_name, "model": args.model,
        "concurrency": args.concurrency, "request_count": args.requests,
        "input_tokens_per_request": round(input_total / len(good), 2) if good else 0,
        "output_tokens_per_request": round(output_total / len(good), 2) if good else 0,
        "wall_time_seconds": f"{wall:.6f}", "request_throughput_rps": f"{len(good) / wall:.6f}",
        "input_token_throughput_tps": f"{input_total / wall:.6f}", "output_token_throughput_tps": f"{output_total / wall:.6f}",
        "avg_latency_seconds": f"{sum(latencies) / len(latencies):.6f}" if latencies else "0",
        "p50_latency_seconds": f"{percentile(latencies, .50):.6f}", "p95_latency_seconds": f"{percentile(latencies, .95):.6f}",
        "p99_latency_seconds": f"{percentile(latencies, .99):.6f}",
        "peak_gpu_memory_mb": max((x[0] for x in gpu), default=""),
        "avg_gpu_utilization_percent": f"{sum(x[1] for x in gpu) / len(gpu):.2f}" if gpu else "",
        "successful_requests": len(good), "failed_requests": len(results) - len(good), "notes": f"prefix_cache_control=True; cache_salt:{','.join(payload['cache_salt'] for payload in payloads)};request_namespace={args.request_namespace}",
    }
    return row, results


async def main() -> int:
    args = arguments()
    if args.concurrency < 1 or args.requests < 1 or args.sample_interval <= 0:
        raise SystemExit("concurrency, requests, and sample interval must be positive")
    if not args.request_namespace.strip():
        raise SystemExit("request namespace must not be empty")
    selected = list(CASES) if args.case == "all" else [args.case]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    exists = args.output.exists() and args.output.stat().st_size > 0
    failed = False
    with args.output.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        for case_name in selected:
            print(f"Running {case_name}...")
            try:
                row, results = await run_case(args, case_name)
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            writer.writerow(row)
            handle.flush()
            print(" ".join(f"{key}={value}" for key, value in row.items() if key != "notes"))
            for item in results:
                if not item.successful:
                    failed = True
                    print(f"failure: status={item.status} error={item.error}", file=sys.stderr)
    print(f"CSV: {args.output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
