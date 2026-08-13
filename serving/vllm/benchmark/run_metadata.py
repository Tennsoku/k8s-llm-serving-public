#!/usr/bin/env python3
"""Create and finalize the lightweight M1 run metadata document."""

from __future__ import annotations

import argparse
import platform
import subprocess
from pathlib import Path
from typing import Any

import yaml

from benchmark_config import load_config
from benchmark_utils import utc_now


def read_first(path: Path) -> str:
    return path.read_text(encoding="utf-8").splitlines()[0]


def git_value(repo_root: Path, *arguments: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return process.stdout.strip()


def capture(args: argparse.Namespace) -> int:
    output = args.run_dir / "run.yaml"
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")
    server_dir = args.server_dir
    required = (
        "server-start-time.txt",
        "container-name.txt",
        "container-id.txt",
        "base-url.txt",
        "image.txt",
        "server-command.txt",
    )
    for name in required:
        if not (server_dir / name).is_file():
            raise SystemExit(f"missing server metadata: {server_dir / name}")
    config = load_config(args.config)
    git_status = git_value(args.repo_root, "status", "--porcelain")
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "run_id": args.run_id,
        "milestone": "M1",
        "experiment": "vllm-single-node-concurrency",
        "purpose": args.purpose,
        "timestamp_utc": read_first(server_dir / "server-start-time.txt"),
        "git": {
            "commit": git_value(args.repo_root, "rev-parse", "HEAD"),
            "dirty": bool(git_status),
        },
        "environment": {
            "node": args.node_label,
            "architecture": platform.machine(),
        },
        "runtime": {
            "image": read_first(server_dir / "image.txt"),
            "container_name": read_first(server_dir / "container-name.txt"),
            "container_id": read_first(server_dir / "container-id.txt"),
            "base_url": read_first(server_dir / "base-url.txt"),
            "model_path": args.model_path,
            "model_revision": args.model_revision,
            "served_model_name": args.served_model_name,
            "expanded_command": (server_dir / "server-command.txt")
            .read_text(encoding="utf-8")
            .strip(),
        },
        "workload": config,
        "metrics": {
            "runtime_endpoint": "/metrics",
            "sample_interval_seconds": args.sample_interval,
            "client_clock": "time.monotonic_ns",
            "correlation_clock": "UTC wall clock",
        },
        "outcome": "running",
    }
    args.run_dir.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(metadata, handle, sort_keys=False)
    print(output)
    return 0


def finalize(args: argparse.Namespace) -> int:
    with args.run_yaml.open("r", encoding="utf-8") as handle:
        metadata = yaml.safe_load(handle)
    if not isinstance(metadata, dict):
        raise SystemExit("run metadata is not a mapping")
    metadata["finished_at_utc"] = utc_now()
    metadata["outcome"] = args.outcome
    temporary = args.run_yaml.with_suffix(".yaml.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(metadata, handle, sort_keys=False)
    temporary.replace(args.run_yaml)
    return 0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--run-dir", type=Path, required=True)
    capture_parser.add_argument("--run-id", required=True)
    capture_parser.add_argument("--node-label", required=True)
    capture_parser.add_argument("--purpose", choices=["exploratory", "canonical"], required=True)
    capture_parser.add_argument("--config", type=Path, required=True)
    capture_parser.add_argument("--server-dir", type=Path, required=True)
    capture_parser.add_argument("--repo-root", type=Path, required=True)
    capture_parser.add_argument("--model-path", required=True)
    capture_parser.add_argument("--model-revision", required=True)
    capture_parser.add_argument("--served-model-name", required=True)
    capture_parser.add_argument("--sample-interval", type=float, required=True)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--run-yaml", type=Path, required=True)
    finalize_parser.add_argument(
        "--outcome",
        choices=["success", "failed", "aborted", "invalid"],
        required=True,
    )
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if args.command == "capture":
        return capture(args)
    return finalize(args)


if __name__ == "__main__":
    raise SystemExit(main())
