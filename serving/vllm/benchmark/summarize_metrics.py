#!/usr/bin/env python3
"""Validate raw M1 JSONL and derive repeat/concurrency summaries."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from benchmark_utils import read_jsonl, summarize_metrics
from summary_context import (
    build_summary_context,
    case_contract_fingerprint,
    load_run_inputs,
)


def validate_jsonl(data_path: Path, schema_path: Path) -> dict[str, Any]:
    if not data_path.exists():
        return {
            "valid": False,
            "record_count": 0,
            "errors": [f"missing {data_path}"],
        }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    count = 0
    with data_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            count += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{data_path}:{line_number}: {exc}")
                continue
            for error in validator.iter_errors(record):
                location = ".".join(str(part) for part in error.absolute_path)
                errors.append(
                    f"{data_path}:{line_number}:{location or '<record>'}: "
                    f"{error.message}"
                )
                if len(errors) >= 100:
                    break
            if len(errors) >= 100:
                break
    return {"valid": not errors, "record_count": count, "errors": errors}


def write_json(path: Path, value: Any, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"refusing to overwrite {path}; pass --force to rebuild")
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    temporary.replace(path)


def write_jsonl(path: Path, records: list[dict[str, Any]], force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"refusing to overwrite {path}; pass --force to rebuild")
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with temporary.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def metadata_run_id(run_dir: Path) -> str | None:
    metadata, _ = load_run_inputs(run_dir)
    value = metadata.get("run_id")
    return value if isinstance(value, str) and value else None


def build_selection_analysis(
    experiment: dict[str, Any] | None, rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Annotate configured selection criteria after the sweep; never stop or select."""
    if not isinstance(experiment, dict):
        return None
    criteria = experiment.get("selection_criteria")
    required = {
        "throughput_metric",
        "throughput_marginal_floor_ratio",
        "latency_metrics",
        "latency_multiplier_ceiling",
        "pressure_indicators",
    }
    if not isinstance(criteria, dict) or not required.issubset(criteria):
        return None

    ordered = sorted(rows, key=lambda row: int(row["concurrency"]))
    baseline = ordered[0] if ordered else None
    previous: dict[str, Any] | None = None
    points: list[dict[str, Any]] = []

    def observed(
        row: dict[str, Any] | None, metric: str, aggregate: str = "median"
    ) -> float | None:
        if row is None:
            return None
        value = row.get(f"{metric}_{aggregate}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    throughput_metric = str(criteria["throughput_metric"])
    marginal_floor = float(criteria["throughput_marginal_floor_ratio"])
    latency_ceiling = float(criteria["latency_multiplier_ceiling"])
    throughput_steps: dict[int, dict[str, float | None]] = {}
    first_positive_slope: float | None = None
    for row in ordered:
        concurrency = int(row["concurrency"])
        throughput = observed(row, throughput_metric)
        previous_throughput = observed(previous, throughput_metric)
        previous_concurrency = (
            int(previous["concurrency"]) if previous is not None else None
        )
        delta_concurrency = (
            concurrency - previous_concurrency
            if previous_concurrency is not None
            else None
        )
        gain_ratio = (
            (throughput - previous_throughput) / previous_throughput
            if throughput is not None
            and previous_throughput is not None
            and previous_throughput != 0
            else None
        )
        slope = (
            (throughput - previous_throughput) / delta_concurrency
            if throughput is not None
            and previous_throughput is not None
            and delta_concurrency is not None
            and delta_concurrency > 0
            else None
        )
        if first_positive_slope is None and slope is not None and slope > 0:
            first_positive_slope = slope
        throughput_steps[concurrency] = {
            "gain_ratio": gain_ratio,
            "slope": slope,
        }
        previous = row

    for row in ordered:
        concurrency = int(row["concurrency"])
        step = throughput_steps[concurrency]
        slope = step["slope"]
        marginal_ratio = (
            slope / first_positive_slope
            if slope is not None
            and first_positive_slope is not None
            and first_positive_slope > 0
            else None
        )
        latency = []
        for metric in criteria["latency_metrics"]:
            value = observed(row, metric)
            baseline_value = observed(baseline, metric)
            multiplier = (
                value / baseline_value
                if value is not None
                and baseline_value is not None
                and baseline_value != 0
                else None
            )
            latency.append(
                {
                    "metric": metric,
                    "observed_value": value,
                    "multiplier_vs_first_point": multiplier,
                    "above_ceiling": (
                        multiplier > latency_ceiling
                        if multiplier is not None
                        else None
                    ),
                }
            )
        indicators = []
        for indicator in criteria["pressure_indicators"]:
            value = observed(row, str(indicator["metric"]), "max")
            threshold = float(indicator["threshold"])
            indicators.append(
                {
                    "metric": indicator["metric"],
                    "operator": indicator["operator"],
                    "threshold": threshold,
                    "observed_value": value,
                    "matched": value > threshold if value is not None else None,
                }
            )
        points.append(
            {
                "concurrency": concurrency,
                "throughput_gain_ratio_vs_previous": step["gain_ratio"],
                "throughput_marginal_tps_per_concurrency": slope,
                "throughput_marginal_ratio": marginal_ratio,
                "throughput_below_floor": (
                    marginal_ratio < marginal_floor
                    if marginal_ratio is not None
                    else None
                ),
                "latency": latency,
                "pressure_indicators": indicators,
            }
        )

    return {
        "interpretation": "annotations_only",
        "criteria": criteria,
        "baseline_concurrency": (
            int(baseline["concurrency"]) if baseline is not None else None
        ),
        "points": points,
    }


def augment_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    if not summary["cases"]:
        recorded = metadata_run_id(run_dir)
        if recorded is not None:
            summary["run_id"] = recorded
    run_id = summary["run_id"]
    _, config = load_run_inputs(run_dir)
    context = build_summary_context(run_dir, run_id)
    summary["enrichment_schema_version"] = 1
    summary["context"] = context
    config_fingerprint = context["fingerprints"]["config_sha256"]

    complete_by_concurrency: Counter[int] = Counter()
    for case in summary["cases"]:
        invalid = set(case.get("invalid_reasons", []))
        concurrency = int(case["concurrency"])
        case["run_id"] = run_id
        case["config_fingerprint"] = config_fingerprint
        case["case_contract_fingerprint"] = case_contract_fingerprint(
            config, concurrency
        )
        client = case.get("client", {})
        runtime = case.get("runtime_samples", {})
        system = case.get("system", {})
        runtime_samples = runtime.get("sample_count", 0)
        system_samples = system.get("sample_count", 0)
        case["completeness"] = {
            "client": (
                not bool(
                    invalid & {"missing_case_end_event", "request_count_mismatch"}
                )
                and client.get("failed_requests", 0) == 0
            ),
            "runtime": not bool(
                invalid
                & {"missing_case_exposition", "no_runtime_samples_in_case_window"}
            ) and runtime.get("scrape_failure_count", 0) < runtime_samples,
            "system": (
                "no_system_samples_in_case_window" not in invalid
                and system.get("sample_failure_count", 0) < system_samples
            ),
        }
        if case.get("measurement_complete") is True:
            complete_by_concurrency[concurrency] += 1

    for row in summary["concurrency_summary"]:
        concurrency = int(row["concurrency"])
        row["run_id"] = run_id
        row["config_fingerprint"] = config_fingerprint
        row["case_contract_fingerprint"] = case_contract_fingerprint(
            config, concurrency
        )
        row["complete_repetition_count"] = complete_by_concurrency[concurrency]

    summary["data_quality"] = {
        "raw_schema_valid": summary.get("raw_validation_passed"),
        "measured_case_count": len(summary["cases"]),
        "complete_case_count": sum(
            case.get("measurement_complete") is True for case in summary["cases"]
        ),
    }
    selection = build_selection_analysis(
        context["experiment"], summary["concurrency_summary"]
    )
    if selection is not None:
        summary["selection_analysis"] = selection


def validate_summary(summary: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(summary), key=lambda error: list(error.absolute_path)
    )
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<summary>'}: "
            f"{error.message}"
            for error in errors[:20]
        )
        raise SystemExit(f"derived summary failed schema validation: {details}")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--schema-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    raw = args.run_dir / "raw"
    validation = {
        "requests": validate_jsonl(
            raw / "requests.jsonl",
            args.schema_dir / "request-metrics.schema.jsonl",
        ),
        "case_events": validate_jsonl(
            raw / "case-events.jsonl",
            args.schema_dir / "case-events.schema.jsonl",
        ),
        "runtime_samples": validate_jsonl(
            raw / "runtime-samples.jsonl",
            args.schema_dir / "runtime-metrics.schema.jsonl",
        ),
        "system_samples": validate_jsonl(
            raw / "system-samples.jsonl",
            args.schema_dir / "system-metrics.schema.jsonl",
        ),
    }
    summary = summarize_metrics(args.run_dir)
    summary["raw_validation"] = validation
    summary["raw_validation_passed"] = all(
        result["valid"] for result in validation.values()
    )
    augment_summary(args.run_dir, summary)
    validate_summary(
        summary, args.schema_dir / "benchmark-summary.schema.json"
    )

    derived = args.run_dir / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    write_json(derived / "summary.json", summary, args.force)
    write_jsonl(derived / "cases.jsonl", summary["cases"], args.force)
    write_jsonl(
        derived / "concurrency-summary.jsonl",
        summary["concurrency_summary"],
        args.force,
    )
    print(
        json.dumps(
            {
                "summary": str(derived / "summary.json"),
                "cases": len(summary["cases"]),
                "raw_validation_passed": summary["raw_validation_passed"],
                "context_warnings": summary["context"]["context_warnings"],
                "selection_analysis": "selection_analysis" in summary,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
