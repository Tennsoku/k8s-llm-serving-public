#!/usr/bin/env python3
"""Load and validate the single-node benchmark configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


CONFIG_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "benchmarks/configs/vllm-single-node/benchmark-config.schema.json"
)

MANAGED_VLLM_ARGUMENTS = {
    "--dtype",
    "--enable-request-id-headers",
    "--generation-config",
    "--gpu-memory-utilization",
    "--host",
    "--max-model-len",
    "--max-num-seqs",
    "--model",
    "--port",
    "--quantization",
    "--revision",
    "--served-model-name",
    "--tokenizer-revision",
}


class ConfigError(ValueError):
    """The benchmark configuration is incomplete or inconsistent."""


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def render_prompt(
    config: dict[str, Any],
    case_id: str | None = None,
    request_index: int | None = None,
) -> str:
    """Render the base or request-specific prompt without mutating config."""
    workload = _mapping(config.get("workload"), "workload")
    prompt = workload.get("prompt")
    if isinstance(prompt, str):
        rendered = prompt
    else:
        parts = _mapping(prompt, "workload.prompt")
        rendered = (
            str(parts["prefix"])
            + str(parts["repeated_text"]) * int(parts["repetitions"])
            + str(parts["suffix"])
        )
    if (
        workload.get("request_suffix") is not None
        and case_id is not None
        and request_index is not None
    ):
        rendered += f"\n\nRequest: {case_id}:{request_index:06d}"
    return rendered


def fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validation_location(error: Any) -> str:
    path = ".".join(str(part) for part in error.absolute_path)
    return path or "<config>"


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    root = _mapping(config, "config")

    schema = json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(root),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{_validation_location(error)}: {error.message}"
            for error in errors[:8]
        )
        if len(errors) > 8:
            details += f"; ... {len(errors) - 8} more error(s)"
        raise ConfigError(details)

    rendered_prompt = render_prompt(root)
    if not rendered_prompt.strip():
        raise ConfigError("workload.prompt renders to an empty string")

    sweep = root["sweep"]
    concurrencies = sweep["concurrency"]
    if concurrencies != sorted(set(concurrencies)):
        raise ConfigError("sweep.concurrency must be unique and increasing")
    for argument in root["runtime"]["extra_args"]:
        if any(character.isspace() for character in argument):
            raise ConfigError(
                "runtime.extra_args entries are individual argv tokens and cannot contain whitespace"
            )
        flag = argument.split("=", 1)[0]
        if flag in MANAGED_VLLM_ARGUMENTS:
            raise ConfigError(
                f"runtime.extra_args must not override managed argument {flag}"
            )

    return root


def config_value(config: dict[str, Any], name: str) -> Any:
    if name == "output-evaluation-cases":
        evaluation = config.get("output_evaluation")
        return evaluation.get("cases_path") if isinstance(evaluation, dict) else None

    paths = {
        "config-id": ("config_id",),
        "config-status": ("experiment", "status"),
        "experiment-step": ("experiment", "step"),
        "experiment-kind": ("experiment", "kind"),
        "comparison-group": ("experiment", "comparison_group"),
        "variant": ("experiment", "variant"),
        "axis": ("experiment", "axis"),
        "image": ("runtime", "image"),
        "model-path": ("model", "path"),
        "model-artifact-revision": ("model", "artifact_revision"),
        "model-runtime-revision": ("model", "runtime_revision"),
        "tokenizer-revision": ("model", "tokenizer_revision"),
        "served-model-name": ("model", "served_name"),
        "dtype": ("runtime", "dtype"),
        "quantization": ("runtime", "quantization"),
        "generation-config": ("runtime", "generation_config"),
        "max-model-len": ("runtime", "max_model_len"),
        "max-num-seqs": ("runtime", "max_num_seqs"),
        "gpu-memory-utilization": ("runtime", "gpu_memory_utilization"),
        "container-memory-limit": ("runtime", "container_memory_limit"),
        "request-count": ("workload", "total_requests_per_repetition"),
        "timeout": ("workload", "request_timeout_seconds"),
        "warmup-requests": ("warmup", "requests"),
        "warmup-concurrency": ("warmup", "concurrency"),
        "repetitions": ("sweep", "measured_repetitions"),
        "sample-interval": ("metrics", "sample_interval_seconds"),
        "ready-timeout": ("orchestration", "ready_timeout_seconds"),
        "idle-timeout": ("orchestration", "idle_timeout_seconds"),
        "stop-timeout": ("orchestration", "stop_timeout_seconds"),
        "stop-on-failure": ("orchestration", "stop_on_failure"),
    }
    current: Any = config
    for key in paths[name]:
        current = current[key]
    return current


GET_NAMES = (
    "config-id",
    "config-status",
    "experiment-step",
    "experiment-kind",
    "comparison-group",
    "variant",
    "axis",
    "image",
    "model-path",
    "model-artifact-revision",
    "model-runtime-revision",
    "tokenizer-revision",
    "served-model-name",
    "dtype",
    "quantization",
    "generation-config",
    "max-model-len",
    "max-num-seqs",
    "gpu-memory-utilization",
    "container-memory-limit",
    "request-count",
    "timeout",
    "warmup-requests",
    "warmup-concurrency",
    "repetitions",
    "sample-interval",
    "ready-timeout",
    "idle-timeout",
    "stop-timeout",
    "stop-on-failure",
    "output-evaluation-cases",
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("name", choices=GET_NAMES)
    subparsers.add_parser("concurrency")
    subparsers.add_parser("extra-args")
    subparsers.add_parser("fingerprint")
    return parser.parse_args()


def _print_value(value: Any) -> None:
    if value is None:
        print("")
    elif isinstance(value, bool):
        print("true" if value else "false")
    else:
        print(value)


def main() -> int:
    args = arguments()
    try:
        config = load_config(args.config)
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ConfigError) as exc:
        raise SystemExit(f"invalid benchmark config: {exc}") from exc
    if args.command == "validate":
        print("valid=true")
    elif args.command == "get":
        _print_value(config_value(config, args.name))
    elif args.command == "concurrency":
        for value in config["sweep"]["concurrency"]:
            print(value)
    elif args.command == "extra-args":
        for value in config["runtime"]["extra_args"]:
            print(value)
    else:
        print(fingerprint(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
