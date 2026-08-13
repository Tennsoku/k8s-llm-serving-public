#!/usr/bin/env python3
"""Validate raw M1 JSONL and derive repeat/concurrency summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from benchmark_utils import summarize_metrics


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
            },
            sort_keys=True,
        )
    )
    return 0 if summary["raw_validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
