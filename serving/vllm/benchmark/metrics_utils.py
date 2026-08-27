"""Prometheus exposition parsing and vLLM semantic metric mapping."""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

SAMPLE_RE = re.compile(
    r"^([A-Za-z_:][A-Za-z0-9_:]*)(?:\{(.*)\})?\s+"
    r"([-+]?(?:[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|Inf|NaN))"
)
LABEL_RE = re.compile(r'(\w+)="((?:\\.|[^"])*)"')

METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "running_requests": ("vllm:num_requests_running",),
    "waiting_requests": ("vllm:num_requests_waiting",),
    "kv_cache_usage_ratio": (
        "vllm:kv_cache_usage_perc",
        "vllm:gpu_cache_usage_perc",
    ),
    "preemption_events_total": (
        "vllm:num_preemptions_total",
        "vllm:num_preemptions",
    ),
    "prompt_tokens_total": (
        "vllm:prompt_tokens_total",
        "vllm:prompt_tokens",
    ),
    "generation_tokens_total": (
        "vllm:generation_tokens_total",
        "vllm:generation_tokens",
    ),
    "request_success_total": (
        "vllm:request_success_total",
        "vllm:request_success",
    ),
    "prefix_cache_queries_total": (
        "vllm:prefix_cache_queries_total",
        "vllm:prefix_cache_queries",
    ),
    "prefix_cache_hits_total": (
        "vllm:prefix_cache_hits_total",
        "vllm:prefix_cache_hits",
    ),
    "avg_prompt_throughput_tps": (
        "vllm:avg_prompt_throughput_toks_per_s",
    ),
    "avg_generation_throughput_tps": (
        "vllm:avg_generation_throughput_toks_per_s",
    ),
}

MAX_AGGREGATIONS = {"kv_cache_usage_ratio"}
HISTOGRAM_ALIASES: dict[str, tuple[str, ...]] = {
    "ttft_seconds": ("vllm:time_to_first_token_seconds",),
    "itl_seconds": ("vllm:inter_token_latency_seconds",),
    "e2e_seconds": ("vllm:e2e_request_latency_seconds",),
    "queue_seconds": (
        "vllm:request_queue_time_seconds",
        "vllm:time_in_queue_requests",
    ),
    "prefill_seconds": ("vllm:request_prefill_time_seconds",),
    "decode_seconds": ("vllm:request_decode_time_seconds",),
}


@dataclass(frozen=True)
class MetricSample:
    name: str
    labels: dict[str, str]
    value: float


def _parse_labels(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    labels: dict[str, str] = {}
    for match in LABEL_RE.finditer(raw):
        escaped = match.group(2)
        try:
            labels[match.group(1)] = json.loads(f'"{escaped}"')
        except json.JSONDecodeError:
            labels[match.group(1)] = escaped
    return labels


def parse_prometheus(text: str) -> list[MetricSample]:
    samples: list[MetricSample] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = SAMPLE_RE.match(line)
        if not match:
            continue
        try:
            value = float(match.group(3))
        except ValueError:
            continue
        if not math.isfinite(value):
            continue
        samples.append(
            MetricSample(
                name=match.group(1),
                labels=_parse_labels(match.group(2)),
                value=value,
            )
        )
    return samples


def _model_matches(sample: MetricSample, model_name: str | None) -> bool:
    observed = sample.labels.get("model_name")
    return model_name is None or observed is None or observed == model_name


def select_semantics(
    samples: list[MetricSample],
    model_name: str | None = None,
    aliases_by_semantic: dict[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, float | None], dict[str, str | None]]:
    values: dict[str, float | None] = {}
    names: dict[str, str | None] = {}
    metric_aliases = (
        METRIC_ALIASES if aliases_by_semantic is None else aliases_by_semantic
    )
    for semantic, aliases in metric_aliases.items():
        selected: list[MetricSample] = []
        selected_name: str | None = None
        for alias in aliases:
            candidate = [
                sample
                for sample in samples
                if sample.name == alias and _model_matches(sample, model_name)
            ]
            if candidate:
                selected = candidate
                selected_name = alias
                break
        if not selected:
            values[semantic] = None
            names[semantic] = None
            continue
        if semantic in MAX_AGGREGATIONS:
            values[semantic] = max(sample.value for sample in selected)
        else:
            values[semantic] = sum(sample.value for sample in selected)
        names[semantic] = selected_name
    return values, names


def scrape_exposition(
    base_url: str, timeout_seconds: float = 10.0
) -> tuple[str | None, int | None, float, str | None]:
    url = f"{base_url.rstrip('/')}/metrics"
    started = time.monotonic()
    request = urllib.request.Request(
        url, headers={"Accept": "text/plain", "User-Agent": "m1-benchmark-sampler"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
            status = response.status
            error = None if status == 200 else f"unexpected HTTP status {status}"
    except urllib.error.HTTPError as exc:
        text = exc.read(1000).decode("utf-8", errors="replace")
        status = exc.code
        error = f"HTTPError: {exc}"
    except Exception as exc:
        text = None
        status = None
        error = f"{type(exc).__name__}: {exc}"
    return text, status, time.monotonic() - started, error


def snapshot_semantics(
    text: str, model_name: str | None = None
) -> tuple[dict[str, float | None], dict[str, str | None]]:
    return select_semantics(parse_prometheus(text), model_name)


def semantic_counter_delta(
    before_text: str,
    after_text: str,
    semantic: str,
    model_name: str | None = None,
    aliases: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    metric_aliases = {semantic: aliases} if aliases is not None else None
    before_values, before_names = select_semantics(
        parse_prometheus(before_text), model_name, metric_aliases
    )
    after_values, after_names = select_semantics(
        parse_prometheus(after_text), model_name, metric_aliases
    )
    before = before_values.get(semantic)
    after = after_values.get(semantic)
    metric_name = after_names.get(semantic) or before_names.get(semantic)
    if before is None or after is None:
        return {
            "metric_name": metric_name,
            "before": before,
            "after": after,
            "delta": None,
            "valid": False,
            "error": "metric_missing",
        }
    delta = after - before
    if delta < 0:
        return {
            "metric_name": metric_name,
            "before": before,
            "after": after,
            "delta": None,
            "valid": False,
            "error": "counter_reset_or_process_restart",
        }
    return {
        "metric_name": metric_name,
        "before": before,
        "after": after,
        "delta": delta,
        "valid": True,
        "error": None,
    }


def extract_histogram(
    text: str, semantic: str, model_name: str | None = None
) -> dict[str, Any] | None:
    samples = parse_prometheus(text)
    bases = HISTOGRAM_ALIASES[semantic]
    selected_base: str | None = None
    for base in bases:
        if any(
            sample.name in {f"{base}_bucket", f"{base}_sum", f"{base}_count"}
            and _model_matches(sample, model_name)
            for sample in samples
        ):
            selected_base = base
            break
    if selected_base is None:
        return None

    count = 0.0
    total = 0.0
    buckets: dict[str, float] = {}
    for sample in samples:
        if not _model_matches(sample, model_name):
            continue
        if sample.name == f"{selected_base}_count":
            count += sample.value
        elif sample.name == f"{selected_base}_sum":
            total += sample.value
        elif sample.name == f"{selected_base}_bucket":
            le = sample.labels.get("le")
            if le is not None:
                buckets[le] = buckets.get(le, 0.0) + sample.value
    return {
        "metric_name": selected_base,
        "count": count,
        "sum": total,
        "buckets": buckets,
    }


def histogram_delta(
    before_text: str,
    after_text: str,
    semantic: str,
    model_name: str | None = None,
) -> dict[str, Any]:
    before = extract_histogram(before_text, semantic, model_name)
    after = extract_histogram(after_text, semantic, model_name)
    if before is None or after is None:
        return {"valid": False, "error": "histogram_missing"}
    count = after["count"] - before["count"]
    total = after["sum"] - before["sum"]
    bucket_keys = set(before["buckets"]) | set(after["buckets"])
    buckets = {
        key: after["buckets"].get(key, 0.0) - before["buckets"].get(key, 0.0)
        for key in bucket_keys
    }
    if count < 0 or total < 0 or any(value < 0 for value in buckets.values()):
        return {
            "metric_name": after["metric_name"],
            "valid": False,
            "error": "histogram_reset_or_process_restart",
        }

    try:
        parsed_bounds = [(float(le), le) for le in bucket_keys]
    except ValueError:
        return {
            "metric_name": after["metric_name"],
            "valid": False,
            "error": "histogram_invalid_bucket_bound",
        }
    if any(
        math.isnan(bound) or math.isinf(bound) and le != "+Inf"
        for bound, le in parsed_bounds
    ):
        return {
            "metric_name": after["metric_name"],
            "valid": False,
            "error": "histogram_invalid_bucket_bound",
        }

    cumulative_buckets: list[dict[str, Any]] = []
    previous_count = 0.0
    positive_inf_count: float | None = None
    for _, le in sorted(parsed_bounds):
        cumulative_count = buckets[le]
        if cumulative_count < previous_count:
            return {
                "metric_name": after["metric_name"],
                "valid": False,
                "error": "histogram_non_monotonic_buckets",
            }
        if le == "+Inf":
            positive_inf_count = cumulative_count
        cumulative_buckets.append(
            {
                "le": le,
                "cumulative_count": (
                    int(cumulative_count)
                    if cumulative_count.is_integer()
                    else cumulative_count
                ),
                "cdf": cumulative_count / count if count > 0 else None,
            }
        )
        previous_count = cumulative_count

    if positive_inf_count is None or not math.isclose(
        positive_inf_count, count, rel_tol=1e-12, abs_tol=1e-9
    ):
        return {
            "metric_name": after["metric_name"],
            "valid": False,
            "error": "histogram_inf_bucket_count_mismatch",
        }

    return {
        "metric_name": after["metric_name"],
        "valid": True,
        "error": None,
        "count": count,
        "sum": total,
        "mean": total / count if count > 0 else None,
        "bucket_encoding": "prometheus_cumulative",
        "cumulative_buckets": cumulative_buckets,
    }
