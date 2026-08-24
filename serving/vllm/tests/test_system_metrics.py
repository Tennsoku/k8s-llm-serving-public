#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

SERVING_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SERVING_DIR / "benchmark"
REPO_ROOT = SERVING_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import system_metrics  # noqa: E402


def completed(
    stdout: str = "", *, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["nvidia-smi"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def write_pid_cgroup(proc_root: Path, pid: int, relative: str) -> None:
    directory = proc_root / str(pid)
    directory.mkdir(parents=True)
    (directory / "cgroup").write_text(
        f"0::{relative}\n",
        encoding="utf-8",
    )


class SystemMetricTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = (
            system_metrics.CGROUP_ROOT / "system.slice/docker-target.scope"
        )

    def test_unsupported_fb_and_strict_container_pid_sum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc_root = Path(temporary)
            write_pid_cgroup(
                proc_root, 101, "/system.slice/docker-target.scope"
            )
            write_pid_cgroup(
                proc_root, 102, "/system.slice/docker-target.scope/worker"
            )
            write_pid_cgroup(proc_root, 103, "/user.slice/other.scope")
            write_pid_cgroup(proc_root, 104, "/user.slice/other.scope")
            responses = [
                completed("95, [N/A], 70, 40\n"),
                completed("101, 10\n102, 2.5\n103, 999\n104, [N/A]\n"),
            ]
            with (
                patch.object(system_metrics.shutil, "which", return_value="/bin/nvidia-smi"),
                patch.object(system_metrics.subprocess, "run", side_effect=responses),
            ):
                values, errors = system_metrics.gpu_sample(
                    0, self.target, proc_root=proc_root
                )

        self.assertEqual(values["gpu_fb_memory_status"], "unsupported")
        self.assertIsNone(values["gpu_memory_used_mib"])
        self.assertEqual(
            values["container_nvml_process_gpu_memory_used_bytes"],
            int(12.5 * system_metrics.MIB_BYTES),
        )
        self.assertEqual(errors, [])

    def test_numeric_fb_is_ok_and_empty_process_list_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.object(system_metrics.shutil, "which", return_value="/bin/nvidia-smi"),
                patch.object(
                    system_metrics.subprocess,
                    "run",
                    side_effect=[completed("95, 123, 70, 40\n"), completed()],
                ),
            ):
                values, errors = system_metrics.gpu_sample(
                    0, self.target, proc_root=Path(temporary)
                )

        self.assertEqual(values["gpu_fb_memory_status"], "ok")
        self.assertEqual(values["gpu_memory_used_mib"], 123.0)
        self.assertEqual(
            values["container_nvml_process_gpu_memory_used_bytes"], 0
        )
        self.assertEqual(errors, [])

    def test_malformed_fb_does_not_discard_process_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc_root = Path(temporary)
            write_pid_cgroup(
                proc_root, 101, "/system.slice/docker-target.scope"
            )
            with (
                patch.object(system_metrics.shutil, "which", return_value="/bin/nvidia-smi"),
                patch.object(
                    system_metrics.subprocess,
                    "run",
                    side_effect=[
                        completed("95, garbage, 70, 40\n"),
                        completed("101, 10\n"),
                    ],
                ),
            ):
                values, errors = system_metrics.gpu_sample(
                    0, self.target, proc_root=proc_root
                )

        self.assertEqual(values["gpu_fb_memory_status"], "error")
        self.assertIsNone(values["gpu_memory_used_mib"])
        self.assertEqual(
            values["container_nvml_process_gpu_memory_used_bytes"],
            10 * system_metrics.MIB_BYTES,
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid framebuffer memory", errors[0])

    def test_process_query_error_is_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.object(system_metrics.shutil, "which", return_value="/bin/nvidia-smi"),
                patch.object(
                    system_metrics.subprocess,
                    "run",
                    side_effect=[
                        completed("95, 123, 70, 40\n"),
                        completed(returncode=1, stderr="permission denied"),
                    ],
                ),
            ):
                values, errors = system_metrics.gpu_sample(
                    0, self.target, proc_root=Path(temporary)
                )

        self.assertEqual(values["gpu_fb_memory_status"], "ok")
        self.assertEqual(values["gpu_memory_used_mib"], 123.0)
        self.assertIsNone(
            values["container_nvml_process_gpu_memory_used_bytes"]
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("container NVML process GPU memory", errors[0])

    def test_process_race_requeries_instead_of_returning_partial_sum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc_root = Path(temporary)
            write_pid_cgroup(
                proc_root, 101, "/system.slice/docker-target.scope"
            )
            run = unittest.mock.Mock(
                side_effect=[
                    completed("95, [N/A], 70, 40\n"),
                    completed("999, 100\n"),
                    completed("101, 3\n"),
                ]
            )
            with (
                patch.object(system_metrics.shutil, "which", return_value="/bin/nvidia-smi"),
                patch.object(system_metrics.subprocess, "run", run),
            ):
                values, errors = system_metrics.gpu_sample(
                    0, self.target, proc_root=proc_root
                )

        self.assertEqual(
            values["container_nvml_process_gpu_memory_used_bytes"],
            3 * system_metrics.MIB_BYTES,
        )
        self.assertEqual(errors, [])
        self.assertEqual(run.call_count, 3)

    def test_persistent_process_race_returns_null(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.object(system_metrics.shutil, "which", return_value="/bin/nvidia-smi"),
                patch.object(
                    system_metrics.subprocess,
                    "run",
                    side_effect=[
                        completed("95, [N/A], 70, 40\n"),
                        completed("999, 100\n"),
                        completed("999, 100\n"),
                    ],
                ),
            ):
                values, errors = system_metrics.gpu_sample(
                    0, self.target, proc_root=Path(temporary)
                )

        self.assertIsNone(
            values["container_nvml_process_gpu_memory_used_bytes"]
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("exited while resolving", errors[0])

    def test_matching_process_na_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc_root = Path(temporary)
            write_pid_cgroup(
                proc_root, 101, "/system.slice/docker-target.scope"
            )
            with (
                patch.object(system_metrics.shutil, "which", return_value="/bin/nvidia-smi"),
                patch.object(
                    system_metrics.subprocess,
                    "run",
                    side_effect=[
                        completed("95, [N/A], 70, 40\n"),
                        completed("101, [N/A]\n"),
                    ],
                ),
            ):
                values, errors = system_metrics.gpu_sample(
                    0, self.target, proc_root=proc_root
                )

        self.assertEqual(values["gpu_fb_memory_status"], "unsupported")
        self.assertIsNone(
            values["container_nvml_process_gpu_memory_used_bytes"]
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("process memory is unsupported", errors[0])

    def test_system_record_emits_new_fields_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cgroup = Path(temporary)
            (cgroup / "memory.current").write_text("10\n", encoding="utf-8")
            gpu = {
                "gpu_utilization_percent": 95.0,
                "gpu_fb_memory_status": "unsupported",
                "gpu_memory_used_mib": None,
                "gpu_temperature_c": 70.0,
                "gpu_power_watts": 40.0,
                "container_nvml_process_gpu_memory_used_bytes": 10,
            }
            with (
                patch.object(system_metrics, "gpu_sample", return_value=(gpu, [])),
                patch.object(
                    system_metrics,
                    "meminfo",
                    return_value={
                        "MemTotal": 100,
                        "MemAvailable": 50,
                        "SwapTotal": 0,
                        "SwapFree": 0,
                    },
                ),
                patch.object(system_metrics, "vmstat", return_value={}),
            ):
                record = system_metrics.system_record(
                    run_id="run",
                    cgroup_path=cgroup,
                    gpu_index=0,
                    sampler_started_ns=0,
                    interval=1.0,
                )

        self.assertTrue(record["sample_success"])
        self.assertEqual(record["gpu_fb_memory_status"], "unsupported")
        self.assertEqual(
            record["container_nvml_process_gpu_memory_used_bytes"], 10
        )
        schema = json.loads(
            (
                REPO_ROOT
                / "benchmarks/configs/system-metrics.schema.jsonl"
            ).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(record)), [])

        legacy = dict(record)
        legacy.pop("gpu_fb_memory_status")
        legacy.pop("container_nvml_process_gpu_memory_used_bytes")
        self.assertEqual(list(validator.iter_errors(legacy)), [])

        invalid = dict(record)
        invalid["gpu_fb_memory_status"] = None
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_system_record_propagates_process_query_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cgroup = Path(temporary)
            (cgroup / "memory.current").write_text("10\n", encoding="utf-8")
            gpu = {
                "gpu_utilization_percent": 95.0,
                "gpu_fb_memory_status": "ok",
                "gpu_memory_used_mib": 123.0,
                "gpu_temperature_c": 70.0,
                "gpu_power_watts": 40.0,
                "container_nvml_process_gpu_memory_used_bytes": None,
            }
            with (
                patch.object(
                    system_metrics,
                    "gpu_sample",
                    return_value=(gpu, ["container process query failed"]),
                ),
                patch.object(system_metrics, "meminfo", return_value={}),
                patch.object(system_metrics, "vmstat", return_value={}),
            ):
                record = system_metrics.system_record(
                    run_id="run",
                    cgroup_path=cgroup,
                    gpu_index=0,
                    sampler_started_ns=0,
                    interval=1.0,
                )

        self.assertFalse(record["sample_success"])
        self.assertIn("container process query failed", record["errors"])


if __name__ == "__main__":
    unittest.main()
