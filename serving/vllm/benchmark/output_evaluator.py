#!/usr/bin/env python3
"""Capture and score a small, declared set of generated-text cases.

Each JSONL case declares ``id``, ``prompt``, ``scorer``, and ``expected``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import unicodedata
from pathlib import Path
from typing import Any

import aiohttp

from benchmark_config import ConfigError, load_config

SCORERS = {"normalized_exact", "json_exact"}


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _expected_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _json_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(map(_json_equal, left, right))
    return left == right


def score_output(output: str, scorer: str, expected: Any) -> bool:
    if scorer == "normalized_exact":
        accepted = expected if isinstance(expected, list) else [expected]
        return normalize_text(output) in {normalize_text(value) for value in accepted}
    if scorer == "json_exact":
        try:
            observed = json.loads(output)
        except json.JSONDecodeError:
            return False
        return _json_equal(observed, _expected_json(expected))
    raise ValueError(f"unsupported scorer: {scorer}")


def load_cases(path: Path, *, raw: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            location = f"{path}:{line_number}"
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{location}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{location}: case must be an object")
            missing = {"id", "prompt", "scorer", "expected"} - row.keys()
            if missing:
                raise ValueError(f"{location}: missing {sorted(missing)}")
            case_id, prompt, scorer = row["id"], row["prompt"], row["scorer"]
            if not isinstance(case_id, str) or not case_id.strip():
                raise ValueError(f"{location}: id must be a non-empty string")
            if case_id in seen:
                raise ValueError(f"{location}: duplicate id {case_id!r}")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"{location}: prompt must be a non-empty string")
            if scorer not in SCORERS:
                raise ValueError(f"{location}: unsupported scorer {scorer!r}")
            expected = row["expected"]
            if scorer == "normalized_exact":
                values = expected if isinstance(expected, list) else [expected]
                if not values or not all(isinstance(value, str) for value in values):
                    raise ValueError(f"{location}: expected must be string(s)")
            else:
                try:
                    _expected_json(expected)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{location}: expected is invalid JSON: {exc}") from exc
            error = row.get("error")
            invalid_raw = not isinstance(error, (str, type(None))) or (
                error is None and not isinstance(row.get("output"), str))
            if raw and invalid_raw:
                raise ValueError(f"{location}: invalid captured output/error")
            seen.add(case_id)
            rows.append(row)
    if not rows:
        raise ValueError(f"{path}: no evaluation cases")
    return rows


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for row in rows:
        correct = row.get("error") is None and score_output(
            row["output"], row["scorer"], row["expected"]
        )
        items.append(
            {"id": row["id"], "scorer": row["scorer"], "correct": correct,
             "error": row.get("error")}
        )
    errors = sum(item["error"] is not None for item in items)
    correct = sum(item["correct"] for item in items)
    return {
        "schema_version": 1,
        "record_type": "output_evaluation_summary",
        "outcome": "complete" if errors == 0 else "failed",
        "correct": correct,
        "total": len(items),
        "accuracy": correct / len(items),
        "request_errors": errors,
        "items": items,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    temporary.replace(path)


def append_raw(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()


async def request_output(
    session: aiohttp.ClientSession, url: str, payload: dict[str, Any], timeout: float
) -> str:
    async with session.post(
        url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)
    ) as response:
        if response.status != 200:
            await response.read()
            raise RuntimeError(f"HTTP {response.status}")
        body = await response.json(content_type=None)
    try:
        output = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("response has no choices[0].message.content") from exc
    if not isinstance(output, str):
        raise ValueError("response content is not a string")
    return output


async def capture(args: argparse.Namespace, config: dict[str, Any]) -> int:
    cases = load_cases(args.cases)
    if args.raw_output.exists():
        raise ValueError(f"refusing to overwrite {args.raw_output}")
    workload, sampling = config["workload"], config["sampling"]
    url = f"{args.base_url.rstrip('/')}/v1/chat/completions"
    failures = 0
    async with aiohttp.ClientSession() as session:
        for case in cases:
            payload = {
                "chat_template_kwargs": {"enable_thinking": False},  # hardcode the chat template kwargs to disable thinking for now
                "model": args.model,
                "messages": [{"role": "user", "content": case["prompt"]}],
                "max_tokens": workload["max_output_tokens"],
                "temperature": sampling["temperature"],
                "seed": sampling["seed"],
                "stream": False,
            }
            try:
                output = await request_output(
                    session, url, payload, float(workload["request_timeout_seconds"])
                )
                error = None
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RuntimeError) as exc:
                output, error = None, f"{type(exc).__name__}: {exc}"
                failures += 1
            row = {**case, "output": output, "error": error}
            row["correct"] = error is None and score_output(
                output, case["scorer"], case["expected"]
            )
            append_raw(args.raw_output, row)
    write_json(args.summary_output, summarize_rows(load_cases(args.raw_output, raw=True)))
    return 1 if failures else 0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture")
    for name in ("config", "cases", "raw-output", "summary-output"):
        capture_parser.add_argument(f"--{name}", type=Path, required=True)
    capture_parser.add_argument("--base-url", required=True)
    capture_parser.add_argument("--model", required=True)
    summary_parser = commands.add_parser("summarize")
    summary_parser.add_argument("--raw-input", type=Path, required=True)
    summary_parser.add_argument("--summary-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        if args.command == "capture":
            return asyncio.run(capture(args, load_config(args.config)))
        rows = load_cases(args.raw_input, raw=True)
        write_json(args.summary_output, summarize_rows(rows))
        return 0
    except (OSError, ConfigError, ValueError) as exc:
        raise SystemExit(f"output evaluation failed: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
