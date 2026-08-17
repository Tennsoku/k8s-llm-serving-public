#!/usr/bin/env python3
"""Create, enrich, and finalize the lightweight M1 run metadata document."""

from __future__ import annotations

import argparse
import platform
import subprocess
from pathlib import Path
from typing import Any

import yaml

from benchmark_config import fingerprint, load_config
from benchmark_utils import utc_now


def git_value(repo_root: Path, *arguments: str) -> str | None:
    process = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    return process.stdout.strip() if process.returncode == 0 else None


def load_metadata(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        metadata = yaml.safe_load(handle)
    if not isinstance(metadata, dict):
        raise SystemExit("run metadata is not a mapping")
    return metadata


def write_metadata(path: Path, metadata: dict[str, Any], *, create: bool) -> None:
    if create and path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    temporary = path.with_suffix(".yaml.tmp")
    if temporary.exists():
        temporary.unlink()
    with temporary.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(metadata, handle, sort_keys=False)
    temporary.replace(path)


def read_optional_first(path: Path) -> str | None:
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[0] if lines else ""


def read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            values[key] = value
    return values


def attach_server_observation(
    metadata: dict[str, Any], server_dir: Path
) -> None:
    observed: dict[str, Any] = {}
    for field, name in (
        ("started_at_utc", "server-start-time.txt"),
        ("run_label", "run-id.txt"),
        ("container_name", "container-name.txt"),
        ("container_id", "container-id.txt"),
        ("base_url", "base-url.txt"),
        ("image", "image.txt"),
        ("runtime_revision", "revision.txt"),
        ("tokenizer_revision", "tokenizer-revision.txt"),
    ):
        value = read_optional_first(server_dir / name)
        if value is not None:
            observed[field] = value or None
    command_path = server_dir / "server-command.txt"
    if command_path.is_file():
        observed["expanded_command"] = command_path.read_text(
            encoding="utf-8"
        ).strip()
    graceful_path = server_dir / "graceful-shutdown.env"
    if graceful_path.is_file():
        observed["graceful_shutdown_evidence"] = graceful_path.read_text(
            encoding="utf-8"
        ).strip()
        observed["shutdown"] = read_key_values(graceful_path)
    if observed:
        metadata["observed_server"] = observed


def capture(args: argparse.Namespace) -> int:
    output = args.run_dir / "run.yaml"
    config = load_config(args.config)
    git_status = git_value(args.repo_root, "status", "--porcelain")
    git_commit = git_value(args.repo_root, "rev-parse", "HEAD")
    metadata: dict[str, Any] = {
        "schema_version": 2,
        "run_id": args.run_id,
        "milestone": "M1",
        "purpose": args.purpose,
        "timestamp_utc": utc_now(),
        "config_id": config["config_id"],
        "config_fingerprint": fingerprint(config),
        "experiment": config["experiment"],
        "git": {
            "commit": git_commit,
            "dirty": bool(git_status) if git_status is not None else None,
        },
        "environment": {
            "node": args.node_label,
            "architecture": platform.machine(),
        },
        "runner": {
            "host": args.host,
            "port": args.port,
            "container_name": args.container_name,
            "gpu_index": args.gpu_index,
        },
        "configuration": config,
        "lifecycle": {
            "phase": "planned",
            "outcome": "running",
            "failure_phase": None,
            "warnings": [],
            "stop_reason": None,
            "last_supported_case": None,
            "first_unsupported_case": None,
        },
        "outcome": "running",
    }
    args.run_dir.mkdir(parents=True, exist_ok=True)
    write_metadata(output, metadata, create=True)
    print(output)
    return 0


def observe(args: argparse.Namespace) -> int:
    metadata = load_metadata(args.run_yaml)
    attach_server_observation(metadata, args.server_dir)
    metadata.setdefault("lifecycle", {})["phase"] = args.phase
    write_metadata(args.run_yaml, metadata, create=False)
    return 0


def finalize(args: argparse.Namespace) -> int:
    metadata = load_metadata(args.run_yaml)
    if args.server_dir is not None:
        attach_server_observation(metadata, args.server_dir)
    lifecycle = metadata.setdefault("lifecycle", {})
    lifecycle["phase"] = "finished"
    lifecycle["outcome"] = args.outcome
    lifecycle["failure_phase"] = args.failure_phase
    lifecycle["warnings"] = args.warning or []
    lifecycle["stop_reason"] = args.stop_reason
    lifecycle["last_supported_case"] = args.last_supported_case
    lifecycle["first_unsupported_case"] = args.first_unsupported_case
    metadata["finished_at_utc"] = utc_now()
    metadata["outcome"] = args.outcome
    write_metadata(args.run_yaml, metadata, create=False)
    return 0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--run-dir", type=Path, required=True)
    capture_parser.add_argument("--run-id", required=True)
    capture_parser.add_argument("--node-label", required=True)
    capture_parser.add_argument(
        "--purpose", choices=["exploratory", "canonical"], required=True
    )
    capture_parser.add_argument("--config", type=Path, required=True)
    capture_parser.add_argument("--repo-root", type=Path, required=True)
    capture_parser.add_argument("--host", required=True)
    capture_parser.add_argument("--port", type=int, required=True)
    capture_parser.add_argument("--container-name", required=True)
    capture_parser.add_argument("--gpu-index", type=int, required=True)

    observe_parser = subparsers.add_parser("observe")
    observe_parser.add_argument("--run-yaml", type=Path, required=True)
    observe_parser.add_argument("--server-dir", type=Path, required=True)
    observe_parser.add_argument("--phase", required=True)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--run-yaml", type=Path, required=True)
    finalize_parser.add_argument("--server-dir", type=Path)
    finalize_parser.add_argument(
        "--outcome",
        choices=["success", "failed", "aborted", "invalid"],
        required=True,
    )
    finalize_parser.add_argument("--failure-phase")
    finalize_parser.add_argument("--warning", action="append")
    finalize_parser.add_argument("--stop-reason")
    finalize_parser.add_argument("--last-supported-case")
    finalize_parser.add_argument("--first-unsupported-case")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if args.command == "capture":
        return capture(args)
    if args.command == "observe":
        return observe(args)
    return finalize(args)


if __name__ == "__main__":
    raise SystemExit(main())
