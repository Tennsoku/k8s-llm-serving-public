#!/usr/bin/env python3
"""Load and validate the M1 single-node benchmark workload contract."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """The benchmark workload contract is incomplete or inconsistent."""


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return float(value)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    root = _mapping(config, "config")
    if root.get("schema_version") != 1:
        raise ConfigError("schema_version must be 1")

    workload = _mapping(root.get("workload"), "workload")
    prompt = workload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ConfigError("workload.prompt must be a non-empty string")
    _positive_int(workload.get("input_tokens_target"), "workload.input_tokens_target")
    _positive_int(workload.get("max_output_tokens"), "workload.max_output_tokens")
    request_count = _positive_int(
        workload.get("total_requests_per_repetition"),
        "workload.total_requests_per_repetition",
    )
    _positive_number(
        workload.get("request_timeout_seconds"),
        "workload.request_timeout_seconds",
    )

    sampling = _mapping(root.get("sampling"), "sampling")
    if sampling.get("stream") is not True:
        raise ConfigError("sampling.stream must be true for TTFT measurement")
    if sampling.get("include_usage") is not True:
        raise ConfigError("sampling.include_usage must be true for token accounting")
    temperature = sampling.get("temperature")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ConfigError("sampling.temperature must be numeric")
    if not isinstance(sampling.get("seed"), int):
        raise ConfigError("sampling.seed must be an integer")

    warmup = _mapping(root.get("warmup"), "warmup")
    warmup_requests = _positive_int(warmup.get("requests"), "warmup.requests")
    warmup_concurrency = _positive_int(
        warmup.get("concurrency"), "warmup.concurrency"
    )
    if warmup_concurrency > warmup_requests:
        raise ConfigError("warmup.concurrency cannot exceed warmup.requests")

    sweep = _mapping(root.get("sweep"), "sweep")
    concurrencies = sweep.get("concurrency")
    if not isinstance(concurrencies, list) or not concurrencies:
        raise ConfigError("sweep.concurrency must be a non-empty list")
    parsed = [_positive_int(item, "sweep.concurrency[]") for item in concurrencies]
    if parsed != sorted(set(parsed)):
        raise ConfigError("sweep.concurrency must be unique and increasing")
    if max(parsed) > request_count:
        raise ConfigError(
            "workload.total_requests_per_repetition must be >= maximum concurrency"
        )
    _positive_int(
        sweep.get("measured_repetitions"), "sweep.measured_repetitions"
    )

    metrics = _mapping(root.get("metrics"), "metrics")
    _positive_number(
        metrics.get("sample_interval_seconds"),
        "metrics.sample_interval_seconds",
    )
    return root


def config_value(config: dict[str, Any], name: str) -> Any:
    paths = {
        "request-count": ("workload", "total_requests_per_repetition"),
        "timeout": ("workload", "request_timeout_seconds"),
        "warmup-requests": ("warmup", "requests"),
        "warmup-concurrency": ("warmup", "concurrency"),
        "repetitions": ("sweep", "measured_repetitions"),
        "sample-interval": ("metrics", "sample_interval_seconds"),
    }
    current: Any = config
    for key in paths[name]:
        current = current[key]
    return current


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    get_parser = subparsers.add_parser("get")
    get_parser.add_argument(
        "name",
        choices=[
            "request-count",
            "timeout",
            "warmup-requests",
            "warmup-concurrency",
            "repetitions",
            "sample-interval",
        ],
    )
    subparsers.add_parser("concurrency")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        config = load_config(args.config)
    except (OSError, yaml.YAMLError, ConfigError) as exc:
        raise SystemExit(f"invalid benchmark config: {exc}") from exc
    if args.command == "validate":
        print("valid=true")
    elif args.command == "get":
        print(config_value(config, args.name))
    else:
        for value in config["sweep"]["concurrency"]:
            print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
