"""Shared, dependency-free helpers for the vLLM HTTP benchmark labs."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class RequestResult:
    latency_seconds: float
    status: int
    input_tokens: int
    output_tokens: int
    error: str = ""

    @property
    def successful(self) -> bool:
        return 200 <= self.status < 300 and not self.error


def post_chat(url: str, payload: dict[str, Any], timeout: float) -> RequestResult:
    """Issue one blocking request. Call this from asyncio.to_thread."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
            usage = data.get("usage") or {}
            return RequestResult(
                time.perf_counter() - started,
                response.status,
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        return RequestResult(time.perf_counter() - started, exc.code, 0, 0, detail)
    except Exception as exc:
        return RequestResult(time.perf_counter() - started, 0, 0, 0, f"{type(exc).__name__}: {exc}")


def percentile(values: list[float], quantile: float) -> float:
    """Linearly interpolated percentile (R-7/NumPy default method)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
