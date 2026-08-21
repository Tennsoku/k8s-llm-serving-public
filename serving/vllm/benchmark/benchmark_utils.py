"""Request measurement and summary helpers for vLLM benchmarks."""

from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

try:
    import aiohttp
except ImportError:  # Allow offline summary tools to import this module.
    aiohttp = None  # type: ignore[assignment]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            records.append(value)
    return records


def percentile(values: list[float], quantile: float) -> float | None:
    """Return the R-7/NumPy-default percentile, or None for no observations."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


async def _sse_data(response: Any) -> AsyncIterator[str]:
    data_lines: list[str] = []
    async for raw_line in response.content:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            if data_lines:
                yield "\n".join(data_lines)
                data_lines.clear()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield "\n".join(data_lines)


def _set_error(
    current_type: str | None,
    current_message: str | None,
    error_type: str,
    message: str,
) -> tuple[str, str]:
    if current_type is not None:
        return current_type, current_message or ""
    return error_type, message[:1000]


async def measure_request(
    session: Any,
    *,
    url: str,
    payload: dict[str, Any],
    run_id: str,
    case_id: str,
    measured: bool,
    model: str,
    request_id: str,
    request_index: int,
    concurrency: int,
    repetition: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Send and fully consume one streaming request.

    TTFT ends at the first non-empty generated-content event. HTTP chunks are
    not treated as model tokens. TPOT is derived from the first/last content
    timestamps and final server usage, and is null for fewer than two tokens.
    """
    if aiohttp is None:
        raise RuntimeError("aiohttp is required to run the benchmark client")

    start_wall = utc_now()
    started_ns = time.monotonic_ns()
    headers_ns: int | None = None
    first_content_ns: int | None = None
    last_content_ns: int | None = None
    status: int | None = None
    response_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    event_count = 0
    content_chunk_count = 0
    saw_done = False
    timed_out = False
    error_type: str | None = None
    error_message: str | None = None

    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "X-Request-Id": request_id,
    }
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:
        async with session.post(
            url, json=payload, headers=headers, timeout=timeout
        ) as response:
            headers_ns = time.monotonic_ns()
            status = response.status
            response_request_id = response.headers.get("X-Request-Id")
            if not 200 <= status < 300:
                body = (await response.text())[:1000]
                error_type, error_message = _set_error(
                    error_type, error_message, "http_error", body
                )
            else:
                async for data in _sse_data(response):
                    if data == "[DONE]":
                        saw_done = True
                        continue
                    event_count += 1
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError as exc:
                        error_type, error_message = _set_error(
                            error_type,
                            error_message,
                            "stream_protocol_error",
                            f"invalid SSE JSON: {exc}",
                        )
                        continue
                    if isinstance(event, dict) and event.get("error"):
                        error_type, error_message = _set_error(
                            error_type,
                            error_message,
                            "server_stream_error",
                            json.dumps(event["error"], sort_keys=True),
                        )
                    usage = event.get("usage") if isinstance(event, dict) else None
                    if isinstance(usage, dict):
                        if usage.get("prompt_tokens") is not None:
                            input_tokens = int(usage["prompt_tokens"])
                        if usage.get("completion_tokens") is not None:
                            output_tokens = int(usage["completion_tokens"])
                    choices = event.get("choices") if isinstance(event, dict) else None
                    if not isinstance(choices, list):
                        continue
                    for choice in choices:
                        if not isinstance(choice, dict):
                            continue
                        if choice.get("finish_reason") is not None:
                            finish_reason = str(choice["finish_reason"])
                        delta = choice.get("delta")
                        content = delta.get("content") if isinstance(delta, dict) else None
                        if isinstance(content, str) and content:
                            observed_ns = time.monotonic_ns()
                            if first_content_ns is None:
                                first_content_ns = observed_ns
                            last_content_ns = observed_ns
                            content_chunk_count += 1
    except asyncio.TimeoutError as exc:
        timed_out = True
        error_type, error_message = _set_error(
            error_type, error_message, "timeout", str(exc) or "request timed out"
        )
    except aiohttp.ClientError as exc:
        error_type, error_message = _set_error(
            error_type,
            error_message,
            "transport_error",
            f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # Preserve unexpected client/parser failures.
        error_type, error_message = _set_error(
            error_type,
            error_message,
            "client_error",
            f"{type(exc).__name__}: {exc}",
        )

    ended_ns = time.monotonic_ns()
    if error_type is None and status is not None and 200 <= status < 300:
        if not saw_done:
            error_type, error_message = "incomplete_stream", "missing [DONE] marker"
        elif input_tokens is None or output_tokens is None:
            error_type, error_message = (
                "missing_usage",
                "stream did not provide prompt/completion token usage",
            )
        elif output_tokens > 0 and first_content_ns is None:
            error_type, error_message = (
                "missing_generated_content",
                "positive completion token count without generated content",
            )

    ttft = (
        (first_content_ns - started_ns) / 1_000_000_000
        if first_content_ns is not None
        else None
    )
    decode = (
        (last_content_ns - first_content_ns) / 1_000_000_000
        if first_content_ns is not None and last_content_ns is not None
        else None
    )
    tpot = (
        decode / (output_tokens - 1)
        if decode is not None and output_tokens is not None and output_tokens > 1
        else None
    )
    return {
        "schema_version": 1,
        "record_type": "request",
        "run_id": run_id,
        "case_id": case_id,
        "measured": measured,
        "model": model,
        "request_id": request_id,
        "request_index": request_index,
        "concurrency": concurrency,
        "repetition": repetition,
        "start_wall_utc": start_wall,
        "end_wall_utc": utc_now(),
        "start_monotonic_ns": started_ns,
        "response_headers_monotonic_ns": headers_ns,
        "first_content_monotonic_ns": first_content_ns,
        "last_content_monotonic_ns": last_content_ns,
        "end_monotonic_ns": ended_ns,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "token_count_source": (
            "server_usage"
            if input_tokens is not None and output_tokens is not None
            else "unavailable"
        ),
        "stream_event_count": event_count,
        "content_chunk_count": content_chunk_count,
        "ttft_seconds": ttft,
        "decode_seconds": decode,
        "tpot_seconds": tpot,
        "e2e_seconds": (ended_ns - started_ns) / 1_000_000_000,
        "http_status": status,
        "finish_reason": finish_reason,
        "response_request_id": response_request_id,
        "request_id_verified": response_request_id == request_id,
        "success": error_type is None,
        "timeout": timed_out,
        "error_type": error_type,
        "error_message": error_message,
    }


def summarize_request_records(
    records: list[dict[str, Any]], wall_time_seconds: float
) -> dict[str, Any]:
    successful = [record for record in records if record.get("success") is True]

    def observed(name: str) -> list[float]:
        return [
            float(record[name])
            for record in successful
            if record.get(name) is not None
        ]

    input_tokens = sum(int(record["input_tokens"]) for record in successful)
    output_tokens = sum(int(record["output_tokens"]) for record in successful)
    summary: dict[str, Any] = {
        "request_count": len(records),
        "successful_requests": len(successful),
        "failed_requests": len(records) - len(successful),
        "timeout_requests": sum(record.get("timeout") is True for record in records),
        "wall_time_seconds": wall_time_seconds,
        "request_throughput_rps": (
            len(successful) / wall_time_seconds if wall_time_seconds > 0 else None
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_token_throughput_tps": (
            input_tokens / wall_time_seconds if wall_time_seconds > 0 else None
        ),
        "output_token_throughput_tps": (
            output_tokens / wall_time_seconds if wall_time_seconds > 0 else None
        ),
    }
    for field, prefix in (
        ("ttft_seconds", "ttft"),
        ("tpot_seconds", "tpot"),
        ("e2e_seconds", "e2e"),
    ):
        values = observed(field)
        summary[f"{prefix}_sample_count"] = len(values)
        for quantile, suffix in ((0.50, "p50"), (0.95, "p95"), (0.99, "p99")):
            summary[f"{prefix}_{suffix}_seconds"] = percentile(values, quantile)
    return summary


def _numeric(records: list[dict[str, Any]], field: str) -> list[float]:
    return [
        float(record[field])
        for record in records
        if record.get(field) is not None
    ]


def _range_delta(
    records: list[dict[str, Any]], field: str
) -> float | None:
    values = _numeric(records, field)
    if len(values) < 2:
        return None
    delta = values[-1] - values[0]
    return delta if delta >= 0 else None


def _runtime_sample_summary(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    running = _numeric(records, "running_requests")
    waiting = _numeric(records, "waiting_requests")
    kv_usage = _numeric(records, "kv_cache_usage_ratio")
    prompt_rate = _numeric(records, "avg_prompt_throughput_tps")
    generation_rate = _numeric(records, "avg_generation_throughput_tps")
    return {
        "sample_count": len(records),
        "scrape_failure_count": sum(
            record.get("scrape_success") is not True for record in records
        ),
        "max_running_requests": max(running) if running else None,
        "max_waiting_requests": max(waiting) if waiting else None,
        "waiting_nonzero_sample_ratio": (
            sum(value > 0 for value in waiting) / len(waiting) if waiting else None
        ),
        "max_kv_cache_usage_ratio": max(kv_usage) if kv_usage else None,
        "p95_kv_cache_usage_ratio": percentile(kv_usage, 0.95),
        "avg_prompt_throughput_gauge_tps": (
            sum(prompt_rate) / len(prompt_rate) if prompt_rate else None
        ),
        "avg_generation_throughput_gauge_tps": (
            sum(generation_rate) / len(generation_rate)
            if generation_rate
            else None
        ),
    }


def _system_sample_summary(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    cgroup_current = _numeric(records, "cgroup_memory_current_bytes")
    cgroup_peak = _numeric(records, "cgroup_memory_peak_bytes")
    host_available = _numeric(records, "host_memory_available_bytes")
    host_used = [
        float(record["host_memory_total_bytes"])
        - float(record["host_memory_available_bytes"])
        for record in records
        if record.get("host_memory_total_bytes") is not None
        and record.get("host_memory_available_bytes") is not None
    ]
    gpu_utilization = _numeric(records, "gpu_utilization_percent")
    gpu_memory = _numeric(records, "gpu_memory_used_mib")
    container_nvml_process_memory = _numeric(
        records, "container_nvml_process_gpu_memory_used_bytes"
    )
    gpu_fb_memory_status_counts = {
        status: sum(record.get("gpu_fb_memory_status") == status for record in records)
        for status in ("ok", "unsupported", "error")
    }
    return {
        "sample_count": len(records),
        "sample_failure_count": sum(
            record.get("sample_success") is not True for record in records
        ),
        "max_cgroup_memory_current_bytes": (
            max(cgroup_current) if cgroup_current else None
        ),
        "max_cgroup_memory_peak_bytes": max(cgroup_peak) if cgroup_peak else None,
        "min_host_memory_available_bytes": (
            min(host_available) if host_available else None
        ),
        "max_host_memory_used_bytes": max(host_used) if host_used else None,
        "avg_gpu_utilization_percent": (
            sum(gpu_utilization) / len(gpu_utilization)
            if gpu_utilization
            else None
        ),
        "max_gpu_utilization_percent": (
            max(gpu_utilization) if gpu_utilization else None
        ),
        "max_gpu_memory_used_mib": max(gpu_memory) if gpu_memory else None,
        "gpu_fb_memory_status_counts": gpu_fb_memory_status_counts,
        "max_container_nvml_process_gpu_memory_used_bytes": (
            max(container_nvml_process_memory)
            if container_nvml_process_memory
            else None
        ),
        "cgroup_memory_high_events_delta": _range_delta(
            records, "cgroup_memory_events_high_total"
        ),
        "cgroup_memory_max_events_delta": _range_delta(
            records, "cgroup_memory_events_max_total"
        ),
        "cgroup_oom_events_delta": _range_delta(
            records, "cgroup_memory_events_oom_total"
        ),
        "cgroup_oom_kill_events_delta": _range_delta(
            records, "cgroup_memory_events_oom_kill_total"
        ),
        "host_pgscan_kswapd_delta": _range_delta(
            records, "host_pgscan_kswapd_total"
        ),
        "host_pgsteal_kswapd_delta": _range_delta(
            records, "host_pgsteal_kswapd_total"
        ),
        "host_pswpin_delta": _range_delta(records, "host_pswpin_total"),
        "host_pswpout_delta": _range_delta(records, "host_pswpout_total"),
    }


def _concurrency_summary(
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from statistics import median

    grouped: dict[int, list[dict[str, Any]]] = {}
    for case in cases:
        grouped.setdefault(int(case["concurrency"]), []).append(case)
    output: list[dict[str, Any]] = []
    for concurrency in sorted(grouped):
        all_rows = grouped[concurrency]
        rows = [
            row for row in all_rows if row.get("measurement_complete") is True
        ]

        def observed(path: tuple[str, str]) -> list[float]:
            return [
                float(row[path[0]][path[1]])
                for row in rows
                if row[path[0]].get(path[1]) is not None
            ]

        summary: dict[str, Any] = {
            "concurrency": concurrency,
            "repetition_count": len(all_rows),
            "case_ids": [row["case_id"] for row in all_rows],
        }
        for name, path in (
            ("request_throughput_rps", ("client", "request_throughput_rps")),
            (
                "output_token_throughput_tps",
                ("client", "output_token_throughput_tps"),
            ),
            ("ttft_p95_seconds", ("client", "ttft_p95_seconds")),
            ("tpot_p95_seconds", ("client", "tpot_p95_seconds")),
            ("e2e_p95_seconds", ("client", "e2e_p95_seconds")),
            (
                "max_waiting_requests",
                ("runtime_samples", "max_waiting_requests"),
            ),
            (
                "max_kv_cache_usage_ratio",
                ("runtime_samples", "max_kv_cache_usage_ratio"),
            ),
            (
                "max_container_nvml_process_gpu_memory_used_bytes",
                ("system", "max_container_nvml_process_gpu_memory_used_bytes"),
            ),
        ):
            values = observed(path)
            summary[f"{name}_median"] = median(values) if values else None
            summary[f"{name}_min"] = min(values) if values else None
            summary[f"{name}_max"] = max(values) if values else None
        output.append(summary)
    return output


def summarize_metrics(run_dir: Path) -> dict[str, Any]:
    """Derive repeat and concurrency summaries exclusively from raw artifacts."""
    from metrics_utils import (
        HISTOGRAM_ALIASES,
        histogram_delta,
        semantic_counter_delta,
    )

    raw_dir = run_dir / "raw"
    requests = read_jsonl(raw_dir / "requests.jsonl")
    events = read_jsonl(raw_dir / "case-events.jsonl")
    runtime_samples = read_jsonl(raw_dir / "runtime-samples.jsonl")
    system_samples = read_jsonl(raw_dir / "system-samples.jsonl")

    starts = {
        event["case_id"]: event
        for event in events
        if event.get("event_type") == "start" and event.get("measured") is True
    }
    ends = {
        event["case_id"]: event
        for event in events
        if event.get("event_type") == "end" and event.get("measured") is True
    }
    ordered_starts = sorted(starts.values(), key=lambda event: event["monotonic_ns"])
    cases: list[dict[str, Any]] = []
    counter_semantics = (
        "preemption_events_total",
        "prompt_tokens_total",
        "generation_tokens_total",
        "request_success_total",
        "prefix_cache_queries_total",
        "prefix_cache_hits_total",
    )

    for start in ordered_starts:
        case_id = start["case_id"]
        end = ends.get(case_id)
        case_requests = [
            record for record in requests if record.get("case_id") == case_id
        ]
        case_dir = raw_dir / "cases" / case_id
        before_path = case_dir / "metrics-before.prom"
        after_path = case_dir / "metrics-after.prom"
        before_text = (
            before_path.read_text(encoding="utf-8") if before_path.exists() else None
        )
        after_text = (
            after_path.read_text(encoding="utf-8") if after_path.exists() else None
        )
        start_ns = int(start["monotonic_ns"])
        end_ns = int(end["monotonic_ns"]) if end else start_ns
        runtime_window = [
            record
            for record in runtime_samples
            if start_ns <= int(record["monotonic_ns"]) <= end_ns
        ]
        system_window = [
            record
            for record in system_samples
            if start_ns <= int(record["monotonic_ns"]) <= end_ns
        ]
        wall = float(end["wall_time_seconds"]) if end else 0.0
        client = summarize_request_records(case_requests, wall)
        runtime_counters: dict[str, Any] = {}
        server_histograms: dict[str, Any] = {}
        if before_text is not None and after_text is not None:
            for semantic in counter_semantics:
                runtime_counters[semantic] = semantic_counter_delta(
                    before_text, after_text, semantic, start["model"]
                )
            for semantic in HISTOGRAM_ALIASES:
                server_histograms[semantic] = histogram_delta(
                    before_text, after_text, semantic, start["model"]
                )

        invalid_reasons: list[str] = []
        if end is None:
            invalid_reasons.append("missing_case_end_event")
        if len(case_requests) != int(start["planned_requests"]):
            invalid_reasons.append("request_count_mismatch")
        if before_text is None or after_text is None:
            invalid_reasons.append("missing_case_exposition")
        if not runtime_window:
            invalid_reasons.append("no_runtime_samples_in_case_window")
        if not system_window:
            invalid_reasons.append("no_system_samples_in_case_window")

        prefix_queries = runtime_counters.get("prefix_cache_queries_total", {}).get(
            "delta"
        )
        prefix_hits = runtime_counters.get("prefix_cache_hits_total", {}).get(
            "delta"
        )
        prefix_ratio = (
            prefix_hits / prefix_queries
            if prefix_queries is not None
            and prefix_hits is not None
            and prefix_queries > 0
            else None
        )
        prompt_delta = runtime_counters.get("prompt_tokens_total", {}).get("delta")
        generation_delta = runtime_counters.get(
            "generation_tokens_total", {}
        ).get("delta")
        cases.append(
            {
                "case_id": case_id,
                "concurrency": start["concurrency"],
                "repetition": start["repetition"],
                "measurement_complete": not invalid_reasons,
                "invalid_reasons": invalid_reasons,
                "client": client,
                "runtime_samples": _runtime_sample_summary(runtime_window),
                "runtime_counters": runtime_counters,
                "server_prompt_throughput_tps": (
                    prompt_delta / wall
                    if prompt_delta is not None and wall > 0
                    else None
                ),
                "server_generation_throughput_tps": (
                    generation_delta / wall
                    if generation_delta is not None and wall > 0
                    else None
                ),
                "prefix_cache_token_hit_ratio": prefix_ratio,
                "server_histograms": server_histograms,
                "system": _system_sample_summary(system_window),
            }
        )

    run_id = (
        ordered_starts[0]["run_id"] if ordered_starts else run_dir.resolve().name
    )
    return {
        "schema_version": 2,
        "run_id": run_id,
        "generated_at_utc": utc_now(),
        "raw_record_counts": {
            "requests": len(requests),
            "case_events": len(events),
            "runtime_samples": len(runtime_samples),
            "system_samples": len(system_samples),
        },
        "cases": cases,
        "concurrency_summary": _concurrency_summary(cases),
    }

