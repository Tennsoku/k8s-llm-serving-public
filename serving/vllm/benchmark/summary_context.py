"""Build normalized, self-contained comparison context for derived summaries."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import yaml

from benchmark_config import fingerprint, render_prompt


def load_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    return value if isinstance(value, dict) else None


def load_run_inputs(
    run_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    metadata = load_mapping(run_dir / "run.yaml") or {}
    config = load_mapping(run_dir / "raw/benchmark-config.yaml")
    if config is None:
        config = load_mapping(run_dir / "raw/workload.yaml")
    if config is None:
        candidate = metadata.get("configuration") or metadata.get("workload")
        config = candidate if isinstance(candidate, dict) else None
    return metadata, config


def _prompt_sha256(config: dict[str, Any]) -> str | None:
    try:
        prompt = render_prompt(config)
    except (KeyError, TypeError, ValueError):
        return None
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _workload_identity(config: dict[str, Any]) -> dict[str, Any] | None:
    workload = config.get("workload")
    if not isinstance(workload, dict):
        return None
    identity = copy.deepcopy(workload)
    identity.pop("prompt", None)
    identity["prompt_sha256"] = _prompt_sha256(config)
    sampling = config.get("sampling")
    identity["sampling"] = copy.deepcopy(sampling)
    return identity


def case_contract_fingerprint(
    config: dict[str, Any] | None, concurrency: int
) -> str | None:
    """Identify a measured point independently of the surrounding sweep."""
    if not isinstance(config, dict) or config.get("schema_version") != 2:
        return None
    contract = {
        "schema_version": 1,
        "concurrency": concurrency,
        "workload": _workload_identity(config),
        "warmup": config["warmup"],
        "metrics": config["metrics"],
    }
    return fingerprint(contract)


def _summary_configuration(config: dict[str, Any] | None) -> dict[str, Any]:
    if config is None:
        return {}
    if config.get("schema_version") != 2:
        legacy = copy.deepcopy(config)
        workload = legacy.get("workload")
        if isinstance(workload, dict) and "prompt" in workload:
            prompt = workload.pop("prompt")
            if isinstance(prompt, str):
                workload["prompt_sha256"] = hashlib.sha256(
                    prompt.encode("utf-8")
                ).hexdigest()
        return {"legacy_config": legacy}

    workload = copy.deepcopy(config["workload"])
    workload.pop("prompt", None)
    workload["prompt_sha256"] = _prompt_sha256(config)
    return {
        "config_id": config["config_id"],
        "model": copy.deepcopy(config["model"]),
        "runtime": copy.deepcopy(config["runtime"]),
        "workload": workload,
        "sampling": copy.deepcopy(config["sampling"]),
        "warmup": copy.deepcopy(config["warmup"]),
        "sweep": copy.deepcopy(config["sweep"]),
        "metrics": copy.deepcopy(config["metrics"]),
        "orchestration": copy.deepcopy(config["orchestration"]),
    }


def _safe_observed_server(metadata: dict[str, Any]) -> dict[str, Any]:
    observed = metadata.get("observed_server")
    if not isinstance(observed, dict):
        return {}
    safe = {
        key: copy.deepcopy(observed[key])
        for key in (
            "started_at_utc",
            "image",
            "runtime_revision",
            "tokenizer_revision",
            "shutdown",
        )
        if key in observed
    }
    command = observed.get("expanded_command")
    if isinstance(command, str) and command:
        safe["command_sha256"] = hashlib.sha256(
            command.encode("utf-8")
        ).hexdigest()
    return safe


def build_summary_context(run_dir: Path, run_id: str) -> dict[str, Any]:
    metadata, config = load_run_inputs(run_dir)
    warnings: list[str] = []
    if metadata.get("schema_version") != 2:
        warnings.append("run_metadata_schema_not_v2")
    if config is None:
        warnings.append("benchmark_config_missing")
    elif config.get("schema_version") != 2:
        warnings.append("benchmark_config_schema_not_v2")
    if metadata and metadata.get("run_id") != run_id:
        warnings.append("run_id_mismatch")

    config_sha = fingerprint(config) if config is not None else None
    if config is not None and config.get("schema_version") == 2:
        recorded = metadata.get("config_fingerprint")
        if isinstance(recorded, str) and recorded != config_sha:
            warnings.append("config_fingerprint_mismatch")

    git = metadata.get("git")

    observed_server = _safe_observed_server(metadata)
    runtime = config.get("runtime") if isinstance(config, dict) else None
    model = config.get("model") if isinstance(config, dict) else None
    if isinstance(runtime, dict) and "image" in observed_server:
        if observed_server["image"] != runtime.get("image"):
            warnings.append("observed_image_mismatch")
    if isinstance(model, dict) and observed_server:
        for observed_key, configured_key in (
            ("runtime_revision", "runtime_revision"),
            ("tokenizer_revision", "tokenizer_revision"),
        ):
            if observed_server.get(observed_key) != model.get(configured_key):
                warnings.append(f"observed_{observed_key}_mismatch")

    configuration = _summary_configuration(config)

    workload = config.get("workload") if isinstance(config, dict) else None
    measurement = None
    if isinstance(config, dict) and config.get("schema_version") == 2:
        measurement = {
            "warmup": config["warmup"],
            "sweep": config["sweep"],
            "metrics": config["metrics"],
            "orchestration": config["orchestration"],
        }

    lifecycle = metadata.get("lifecycle")
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    experiment = (
        config.get("experiment", metadata.get("experiment", {}))
        if isinstance(config, dict)
        else metadata.get("experiment", {})
    )
    if isinstance(experiment, str):
        experiment = {"name": experiment}
    elif isinstance(experiment, dict):
        experiment = copy.deepcopy(experiment)
    else:
        experiment = {}

    legacy_policy = experiment.pop("selection_policy", None)
    if (
        "selection_criteria" not in experiment
        and isinstance(legacy_policy, dict)
    ):
        criteria = {
            key: copy.deepcopy(value)
            for key, value in legacy_policy.items()
            if key not in {"pressure_signals", "stop_rule"}
        }
        criteria["pressure_indicators"] = copy.deepcopy(
            legacy_policy.get("pressure_signals", [])
        )
        experiment["selection_criteria"] = criteria
        warnings.append("legacy_selection_policy_normalized")

    environment = metadata.get("environment")
    environment = copy.deepcopy(environment) if isinstance(environment, dict) else {}
    if isinstance(git, dict):
        environment["git"] = copy.deepcopy(git)

    return {
        "schema_version": 1,
        "run": {
            "purpose": metadata.get("purpose"),
            "started_at_utc": metadata.get("timestamp_utc"),
            "finished_at_utc": metadata.get("finished_at_utc"),
            "outcome": lifecycle.get("outcome", metadata.get("outcome")),
            "failure_phase": lifecycle.get("failure_phase"),
            "warnings": copy.deepcopy(
                lifecycle.get("warnings", lifecycle.get("cleanup_failures", []))
            ),
            "stop_reason": lifecycle.get("stop_reason"),
            "last_supported_case": lifecycle.get("last_supported_case"),
            "first_unsupported_case": lifecycle.get("first_unsupported_case"),
        },
        "experiment": copy.deepcopy(experiment),
        "environment": environment,
        "observed_server": observed_server,
        "configuration": configuration,
        "fingerprints": {
            "config_sha256": config_sha,
            "model_sha256": fingerprint(model) if isinstance(model, dict) else None,
            "runtime_sha256": (
                fingerprint(runtime) if isinstance(runtime, dict) else None
            ),
            "workload_sha256": (
                fingerprint(_workload_identity(config))
                if isinstance(config, dict)
                and isinstance(workload, dict)
                else None
            ),
            "measurement_plan_sha256": (
                fingerprint(measurement) if isinstance(measurement, dict) else None
            ),
        },
        "context_warnings": warnings,
    }
