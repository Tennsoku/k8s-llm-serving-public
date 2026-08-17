from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

VLLM_DIR = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = VLLM_DIR / "benchmark"
REPO_ROOT = VLLM_DIR.parents[1]
sys.path.insert(0, str(BENCHMARK_DIR))

from benchmark_config import load_config  # noqa: E402
from benchmark_utils import summarize_metrics  # noqa: E402
from summarize_metrics import (  # noqa: E402
    augment_summary,
    build_selection_analysis,
    validate_summary,
)


class SummaryContextTests(unittest.TestCase):
    def schema_path(self) -> Path:
        return (
            REPO_ROOT
            / "benchmarks/configs/vllm-single-node/benchmark-summary.schema.json"
        )

    def test_zero_case_summary_keeps_context_warnings_as_annotations(self) -> None:
        config_path = (
            REPO_ROOT / "benchmarks/configs/vllm-single-node/benchmark-smoke.yaml"
        )
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "metadata-run-id"
            raw = run_dir / "raw"
            raw.mkdir(parents=True)
            shutil.copyfile(config_path, raw / "benchmark-config.yaml")
            metadata = {
                "schema_version": 2,
                "run_id": "metadata-run-id",
                "purpose": "exploratory",
                "timestamp_utc": "2026-08-13T00:00:00+00:00",
                "finished_at_utc": "2026-08-13T00:01:00+00:00",
                "config_fingerprint": "different-recorded-value",
                "environment": {"node": "spark-a", "architecture": "aarch64"},
                "lifecycle": {
                    "outcome": "failed",
                    "failure_phase": "wait_ready",
                    "stop_reason": "readiness_timeout",
                },
            }
            (run_dir / "run.yaml").write_text(
                yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
            )

            summary = summarize_metrics(run_dir)
            summary["raw_validation"] = {}
            summary["raw_validation_passed"] = False
            augment_summary(run_dir, summary)
            validate_summary(summary, self.schema_path())

            self.assertEqual(summary["run_id"], "metadata-run-id")
            self.assertEqual(summary["cases"], [])
            self.assertFalse(summary["data_quality"]["raw_schema_valid"])
            context = summary["context"]
            self.assertEqual(context["run"]["failure_phase"], "wait_ready")
            self.assertIn("config_fingerprint_mismatch", context["context_warnings"])
            self.assertNotIn("comparison_eligible", context)
            self.assertNotIn("cross_run_eligible", context)

    def test_selection_analysis_is_annotation_only(self) -> None:
        config_path = (
            REPO_ROOT
            / "benchmarks/configs/vllm-single-node/m1.4/selection/long-long.yaml"
        )
        config = load_config(config_path)
        rows = [
            {
                "concurrency": 1,
                "output_token_throughput_tps_median": 100.0,
                "ttft_p95_seconds_median": 1.0,
                "e2e_p95_seconds_median": 2.0,
                "max_waiting_requests_median": 0.0,
                "max_waiting_requests_max": 0.0,
                "max_kv_cache_usage_ratio_median": 0.10,
                "max_kv_cache_usage_ratio_max": 0.10,
            },
            {
                "concurrency": 2,
                "output_token_throughput_tps_median": 180.0,
                "ttft_p95_seconds_median": 1.2,
                "e2e_p95_seconds_median": 2.4,
                "max_waiting_requests_median": 0.0,
                "max_waiting_requests_max": 0.0,
                "max_kv_cache_usage_ratio_median": 0.15,
                "max_kv_cache_usage_ratio_max": 0.15,
            },
            {
                "concurrency": 4,
                "output_token_throughput_tps_median": 195.0,
                "ttft_p95_seconds_median": 2.1,
                "e2e_p95_seconds_median": 3.0,
                "max_waiting_requests_median": 0.0,
                "max_waiting_requests_max": 1.0,
                "max_kv_cache_usage_ratio_median": 0.20,
                "max_kv_cache_usage_ratio_max": 0.20,
            },
        ]

        analysis = build_selection_analysis(config["experiment"], rows)

        self.assertIsNotNone(analysis)
        assert analysis is not None
        self.assertEqual(analysis["interpretation"], "annotations_only")
        self.assertEqual(
            analysis["criteria"], config["experiment"]["selection_criteria"]
        )
        point = analysis["points"][2]
        self.assertAlmostEqual(
            point["throughput_gain_ratio_vs_previous"], 15.0 / 180.0
        )
        self.assertAlmostEqual(
            point["throughput_marginal_tps_per_concurrency"], 7.5
        )
        self.assertAlmostEqual(
            point["throughput_marginal_ratio"], 7.5 / 80.0
        )
        self.assertTrue(point["throughput_below_floor"])
        self.assertTrue(point["latency"][0]["above_ceiling"])
        self.assertTrue(point["pressure_indicators"][0]["matched"])

    def test_legacy_selection_policy_is_normalized_for_summary(self) -> None:
        config = load_config(
            REPO_ROOT
            / "benchmarks/configs/vllm-single-node/m1.4/selection/long-long.yaml"
        )
        policy = config["experiment"].pop("selection_criteria")
        policy["pressure_signals"] = policy.pop("pressure_indicators")
        policy["stop_rule"] = "legacy_text_only"
        config["experiment"]["selection_policy"] = policy

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "legacy-selection"
            raw = run_dir / "raw"
            raw.mkdir(parents=True)
            (raw / "benchmark-config.yaml").write_text(
                yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
            )
            (run_dir / "run.yaml").write_text(
                yaml.safe_dump(
                    {"schema_version": 2, "run_id": "legacy-selection"},
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            summary = summarize_metrics(run_dir)
            summary["raw_validation"] = {}
            summary["raw_validation_passed"] = False
            augment_summary(run_dir, summary)

        experiment = summary["context"]["experiment"]
        self.assertIn("selection_criteria", experiment)
        self.assertNotIn("selection_policy", experiment)
        self.assertNotIn("stop_rule", experiment["selection_criteria"])
        self.assertIn(
            "legacy_selection_policy_normalized",
            summary["context"]["context_warnings"],
        )
        self.assertEqual(
            summary["selection_analysis"]["interpretation"],
            "annotations_only",
        )

    def test_raw_validation_diagnostics_do_not_reject_summary(self) -> None:
        config_path = (
            REPO_ROOT / "benchmarks/configs/vllm-single-node/benchmark-smoke.yaml"
        )
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "diagnostic-run"
            raw = run_dir / "raw"
            raw.mkdir(parents=True)
            shutil.copyfile(config_path, raw / "benchmark-config.yaml")
            (run_dir / "run.yaml").write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 2,
                        "run_id": "diagnostic-run",
                        "lifecycle": {
                            "outcome": "failed",
                            "stop_reason": "readiness_timeout",
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            process = subprocess.run(
                [
                    sys.executable,
                    str(BENCHMARK_DIR / "summarize_metrics.py"),
                    "--run-dir",
                    str(run_dir),
                    "--schema-dir",
                    str(REPO_ROOT / "benchmarks/configs/vllm-single-node"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(process.returncode, 0, process.stderr)
            summary = json.loads(
                (run_dir / "derived/summary.json").read_text(encoding="utf-8")
            )
            self.assertFalse(summary["raw_validation_passed"])
            self.assertFalse(summary["data_quality"]["raw_schema_valid"])

    def test_viewer_contract_fields_are_schema_constrained(self) -> None:
        base = {
            "schema_version": 2,
            "enrichment_schema_version": 1,
            "run_id": "contract-run",
            "generated_at_utc": "2026-08-13T00:00:00+00:00",
            "raw_record_counts": {},
            "cases": [],
            "concurrency_summary": [],
            "raw_validation": {},
            "raw_validation_passed": True,
            "context": {
                "schema_version": 1,
                "run": {},
                "experiment": {},
                "environment": {},
                "observed_server": {},
                "configuration": {},
                "fingerprints": {
                    "config_sha256": None,
                    "model_sha256": None,
                    "runtime_sha256": None,
                    "workload_sha256": None,
                    "measurement_plan_sha256": None,
                },
            },
        }
        malformed = []
        selection = json.loads(json.dumps(base))
        selection["context"]["experiment"]["selection_criteria"] = {
            "pressure_indicators": "wrong"
        }
        malformed.append(selection)
        boundary = json.loads(json.dumps(base))
        boundary["context"]["experiment"]["boundary_policy"] = {
            "stop_conditions": "wrong"
        }
        malformed.append(boundary)

        for summary in malformed:
            with self.subTest(experiment=summary["context"]["experiment"]):
                with self.assertRaises(SystemExit):
                    validate_summary(summary, self.schema_path())

    def test_legacy_v2_summary_still_validates(self) -> None:
        summary = {
            "schema_version": 2,
            "run_id": "legacy-run",
            "generated_at_utc": "2026-08-13T00:00:00+00:00",
            "raw_record_counts": {},
            "cases": [],
            "concurrency_summary": [],
            "raw_validation": {},
            "raw_validation_passed": True,
        }

        validate_summary(summary, self.schema_path())


if __name__ == "__main__":
    unittest.main()
