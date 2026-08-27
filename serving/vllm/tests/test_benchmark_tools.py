from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

VLLM_DIR = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = VLLM_DIR / "benchmark"
REPO_ROOT = VLLM_DIR.parents[1]
sys.path.insert(0, str(BENCHMARK_DIR))

from benchmark_client import derive_cache_salt, report_progress  # noqa: E402
from benchmark_config import ConfigError, fingerprint, load_config, render_prompt  # noqa: E402
import benchmark_utils as benchmark_utils_module  # noqa: E402
from benchmark_utils import (  # noqa: E402
    measure_request,
    percentile,
    summarize_metrics,
    summarize_request_records,
)
import runtime_metrics as runtime_metrics_module  # noqa: E402
from output_evaluator import score_output, summarize_rows  # noqa: E402
from metrics_utils import (  # noqa: E402
    histogram_delta,
    semantic_counter_delta,
    snapshot_semantics,
)
from summary_context import case_contract_fingerprint  # noqa: E402


BEFORE = """# TYPE vllm:num_preemptions_total counter
vllm:num_requests_running{model_name="model"} 0
vllm:num_requests_waiting{model_name="model"} 0
vllm:kv_cache_usage_perc{model_name="model"} 0
vllm:num_preemptions_total{model_name="model"} 2
vllm:prompt_tokens_total{model_name="model"} 100
vllm:generation_tokens_total{model_name="model"} 50
vllm:request_success_total{model_name="model",finished_reason="stop"} 1
vllm:prefix_cache_queries_total{model_name="model"} 10
vllm:prefix_cache_hits_total{model_name="model"} 5
vllm:spec_decode_num_drafts_total{model_name="model"} 10
vllm:spec_decode_num_draft_tokens_total{model_name="model"} 30
vllm:spec_decode_num_accepted_tokens_total{model_name="model"} 15
vllm:time_to_first_token_seconds_bucket{model_name="model",le="1.0"} 1
vllm:time_to_first_token_seconds_bucket{model_name="model",le="+Inf"} 1
vllm:time_to_first_token_seconds_sum{model_name="model"} 0.5
vllm:time_to_first_token_seconds_count{model_name="model"} 1
"""

AFTER = """# TYPE vllm:num_preemptions_total counter
vllm:num_requests_running{model_name="model"} 0
vllm:num_requests_waiting{model_name="model"} 0
vllm:kv_cache_usage_perc{model_name="model"} 0
vllm:num_preemptions_total{model_name="model"} 5
vllm:prompt_tokens_total{model_name="model"} 228
vllm:generation_tokens_total{model_name="model"} 114
vllm:request_success_total{model_name="model",finished_reason="stop"} 2
vllm:prefix_cache_queries_total{model_name="model"} 138
vllm:prefix_cache_hits_total{model_name="model"} 69
vllm:spec_decode_num_drafts_total{model_name="model"} 14
vllm:spec_decode_num_draft_tokens_total{model_name="model"} 42
vllm:spec_decode_num_accepted_tokens_total{model_name="model"} 23
vllm:time_to_first_token_seconds_bucket{model_name="model",le="1.0"} 2
vllm:time_to_first_token_seconds_bucket{model_name="model",le="+Inf"} 2
vllm:time_to_first_token_seconds_sum{model_name="model"} 0.9
vllm:time_to_first_token_seconds_count{model_name="model"} 2
"""


class BenchmarkToolTests(unittest.TestCase):
    def test_workload_contract(self) -> None:
        config = load_config(
            REPO_ROOT
            / "benchmarks/configs/benchmark-workload.yaml"
        )
        self.assertEqual(config["schema_version"], 2)
        self.assertEqual(config["sweep"]["concurrency"][:5], [1, 2, 4, 8, 16])
        self.assertEqual(config["runtime"]["max_model_len"], 8192)
        self.assertEqual(config["runtime"]["max_num_seqs"], 128)
        self.assertEqual(
            config["workload"]["cache_identity"]["mode"], "request_unique"
        )
        self.assertTrue(config["sampling"]["stream"])
        self.assertTrue(config["sampling"]["include_usage"])

        smoke = load_config(
            REPO_ROOT
            / "benchmarks/configs/benchmark-smoke.yaml"
        )
        self.assertEqual(smoke["workload"]["total_requests_per_repetition"], 4)
        self.assertEqual(smoke["sweep"]["measured_repetitions"], 1)

    def test_progress_reports_completion_rate_and_eta(self) -> None:
        output = io.StringIO()
        with redirect_stderr(output):
            report_progress(
                case_id="c001-r01",
                completed=25,
                planned=100,
                successful=24,
                failed=1,
                elapsed_seconds=10.0,
            )
        line = output.getvalue()
        self.assertIn("completed=25/100", line)
        self.assertIn("request_throughput_rps=2.500", line)
        self.assertIn("eta_seconds=30.0", line)

    def test_runtime_record_forwards_scrape_timeout(self) -> None:
        observed: dict[str, object] = {}

        def fake_scrape(base_url: str, timeout: float):
            observed["base_url"] = base_url
            observed["timeout"] = timeout
            return BEFORE, 200, 0.01, None

        original = runtime_metrics_module.scrape_exposition
        runtime_metrics_module.scrape_exposition = fake_scrape
        try:
            record = runtime_metrics_module.runtime_record(
                run_id="run",
                base_url="http://example.invalid",
                model_name="model",
                sampler_started_ns=0,
                interval=0.5,
                scrape_timeout=0.25,
            )
        finally:
            runtime_metrics_module.scrape_exposition = original

        self.assertEqual(observed["timeout"], 0.25)
        self.assertEqual(record["running_requests"], 0)
        self.assertNotIn("speculative_drafts_total", record)

    def test_percentile_and_request_summary(self) -> None:
        self.assertEqual(percentile([1.0, 2.0, 3.0], 0.5), 2.0)
        self.assertIsNone(percentile([], 0.95))
        summary = summarize_request_records(
            [
                {
                    "success": True,
                    "timeout": False,
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "ttft_seconds": 0.1,
                    "tpot_seconds": 0.02,
                    "e2e_seconds": 0.2,
                }
            ],
            1.0,
        )
        self.assertEqual(summary["output_token_throughput_tps"], 4.0)
        self.assertEqual(summary["ttft_p95_seconds"], 0.1)

    def test_prometheus_aliases_and_deltas(self) -> None:
        values, names = snapshot_semantics(BEFORE, "model")
        self.assertEqual(values["preemption_events_total"], 2)
        self.assertEqual(
            names["kv_cache_usage_ratio"], "vllm:kv_cache_usage_perc"
        )
        counter = semantic_counter_delta(
            BEFORE, AFTER, "preemption_events_total", "model"
        )
        self.assertTrue(counter["valid"])
        self.assertEqual(counter["delta"], 3)
        histogram = histogram_delta(
            BEFORE, AFTER, "ttft_seconds", "model"
        )
        self.assertTrue(histogram["valid"])
        self.assertEqual(histogram["count"], 1)
        self.assertAlmostEqual(histogram["sum"], 0.4)
        self.assertEqual(histogram["bucket_encoding"], "prometheus_cumulative")
        self.assertNotIn("buckets", histogram)
        self.assertEqual(
            histogram["cumulative_buckets"],
            [
                {"le": "1.0", "cumulative_count": 1, "cdf": 1.0},
                {"le": "+Inf", "cumulative_count": 1, "cdf": 1.0},
            ],
        )

    def test_histogram_buckets_are_sorted_numerically_with_cdf(self) -> None:
        before = """vllm:time_to_first_token_seconds_bucket{model_name="model",le="2.5"} 0
vllm:time_to_first_token_seconds_bucket{model_name="model",le="+Inf"} 0
vllm:time_to_first_token_seconds_bucket{model_name="model",le="0.1"} 0
vllm:time_to_first_token_seconds_bucket{model_name="model",le="10.0"} 0
vllm:time_to_first_token_seconds_sum{model_name="model"} 0
vllm:time_to_first_token_seconds_count{model_name="model"} 0
"""
        after = """vllm:time_to_first_token_seconds_bucket{model_name="model",le="10.0"} 3
vllm:time_to_first_token_seconds_bucket{model_name="model",le="0.1"} 1
vllm:time_to_first_token_seconds_bucket{model_name="model",le="+Inf"} 4
vllm:time_to_first_token_seconds_bucket{model_name="model",le="2.5"} 2
vllm:time_to_first_token_seconds_sum{model_name="model"} 13
vllm:time_to_first_token_seconds_count{model_name="model"} 4
"""

        histogram = histogram_delta(before, after, "ttft_seconds", "model")

        self.assertTrue(histogram["valid"])
        self.assertEqual(
            histogram["cumulative_buckets"],
            [
                {"le": "0.1", "cumulative_count": 1, "cdf": 0.25},
                {"le": "2.5", "cumulative_count": 2, "cdf": 0.5},
                {"le": "10.0", "cumulative_count": 3, "cdf": 0.75},
                {"le": "+Inf", "cumulative_count": 4, "cdf": 1.0},
            ],
        )

    def test_zero_count_histogram_has_null_cdf(self) -> None:
        histogram = histogram_delta(BEFORE, BEFORE, "ttft_seconds", "model")

        self.assertTrue(histogram["valid"])
        self.assertEqual(histogram["count"], 0)
        self.assertIsNone(histogram["mean"])
        self.assertEqual(
            histogram["cumulative_buckets"],
            [
                {"le": "1.0", "cumulative_count": 0, "cdf": None},
                {"le": "+Inf", "cumulative_count": 0, "cdf": None},
            ],
        )

    def test_histogram_rejects_non_monotonic_cumulative_buckets(self) -> None:
        after = AFTER.replace(
            'le="1.0"} 2',
            'le="1.0"} 3',
        )

        histogram = histogram_delta(BEFORE, after, "ttft_seconds", "model")

        self.assertFalse(histogram["valid"])
        self.assertEqual(histogram["error"], "histogram_non_monotonic_buckets")

    def test_histogram_requires_inf_bucket_to_match_count(self) -> None:
        after = AFTER.replace(
            'le="+Inf"} 2',
            'le="+Inf"} 3',
        )

        histogram = histogram_delta(BEFORE, after, "ttft_seconds", "model")

        self.assertFalse(histogram["valid"])
        self.assertEqual(
            histogram["error"], "histogram_inf_bucket_count_mismatch"
        )

    def test_json_schemas_are_valid(self) -> None:
        schema_dir = REPO_ROOT / "benchmarks/configs"
        paths = [
            *schema_dir.glob("*.schema.json"),
            *schema_dir.glob("*.schema.jsonl"),
        ]
        self.assertTrue(paths)
        for path in paths:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)

    def test_summary_uses_per_case_exposition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            raw = run_dir / "raw"
            case_dir = raw / "cases/c001-r01"
            case_dir.mkdir(parents=True)
            (case_dir / "metrics-before.prom").write_text(
                BEFORE, encoding="utf-8"
            )
            (case_dir / "metrics-after.prom").write_text(
                AFTER, encoding="utf-8"
            )

            request = {
                "run_id": "run",
                "case_id": "c001-r01",
                "success": True,
                "timeout": False,
                "input_tokens": 128,
                "output_tokens": 64,
                "ttft_seconds": 0.1,
                "tpot_seconds": 0.02,
                "e2e_seconds": 1.4,
            }
            (raw / "requests.jsonl").write_text(
                json.dumps(request) + "\n", encoding="utf-8"
            )
            events = [
                {
                    "event_type": "start",
                    "measured": True,
                    "run_id": "run",
                    "case_id": "c001-r01",
                    "model": "model",
                    "concurrency": 1,
                    "repetition": 1,
                    "planned_requests": 1,
                    "monotonic_ns": 100,
                },
                {
                    "event_type": "end",
                    "measured": True,
                    "run_id": "run",
                    "case_id": "c001-r01",
                    "model": "model",
                    "concurrency": 1,
                    "repetition": 1,
                    "planned_requests": 1,
                    "monotonic_ns": 300,
                    "wall_time_seconds": 2.0,
                },
            ]
            (raw / "case-events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            runtime = {
                "monotonic_ns": 200,
                "scrape_success": True,
                "running_requests": 1,
                "waiting_requests": 0,
                "kv_cache_usage_ratio": 0.5,
                "avg_prompt_throughput_tps": None,
                "avg_generation_throughput_tps": None,
            }
            (raw / "runtime-samples.jsonl").write_text(
                json.dumps(runtime) + "\n", encoding="utf-8"
            )
            system = {
                "monotonic_ns": 200,
                "sample_success": True,
                "cgroup_memory_current_bytes": 10,
                "cgroup_memory_peak_bytes": 20,
                "host_memory_total_bytes": 100,
                "host_memory_available_bytes": 60,
                "gpu_utilization_percent": 50,
                "gpu_fb_memory_status": "unsupported",
                "container_nvml_process_gpu_memory_used_bytes": 30,
            }
            (raw / "system-samples.jsonl").write_text(
                json.dumps(system) + "\n", encoding="utf-8"
            )

            summary = summarize_metrics(run_dir)
            self.assertEqual(summary["schema_version"], 2)
            case = summary["cases"][0]
            self.assertTrue(case["measurement_complete"])
            self.assertEqual(
                case["runtime_counters"]["preemption_events_total"]["delta"],
                3,
            )
            self.assertEqual(
                case["runtime_counters"][
                    "speculative_accepted_tokens_total"
                ]["delta"],
                8,
            )
            self.assertAlmostEqual(
                case["speculative_acceptance_rate"], 2 / 3
            )
            self.assertEqual(
                case["speculative_accepted_tokens_per_draft"], 2
            )
            self.assertEqual(
                case["client"]["output_token_throughput_tps"], 32.0
            )
            self.assertEqual(
                case["system"]["gpu_fb_memory_status_counts"]["unsupported"],
                1,
            )
            self.assertEqual(
                case["system"][
                    "max_container_nvml_process_gpu_memory_used_bytes"
                ],
                30,
            )
            self.assertEqual(
                summary["concurrency_summary"][0][
                    "max_container_nvml_process_gpu_memory_used_bytes_median"
                ],
                30,
            )
            self.assertAlmostEqual(
                summary["concurrency_summary"][0][
                    "speculative_acceptance_rate_median"
                ],
                2 / 3,
            )

    def test_output_evaluator_uses_declared_deterministic_scores(self) -> None:
        self.assertTrue(score_output("Ａ\n  B", "normalized_exact", "a b"))
        self.assertTrue(
            score_output("answer two", "normalized_exact", ["answer one", "ANSWER TWO"])
        )
        self.assertFalse(score_output("almost", "normalized_exact", "exact"))
        self.assertTrue(
            score_output('{"b": [2], "a": 1}', "json_exact", {"a": 1, "b": [2]})
        )
        self.assertFalse(
            score_output('{"value": 1}', "json_exact", {"value": True})
        )

        rows = [
            {
                "id": "normalized",
                "prompt": "Return the declared answer.",
                "scorer": "normalized_exact",
                "expected": "yes",
                "output": " YES ",
                "error": None,
                "correct": False,
            },
            {
                "id": "request-error",
                "prompt": "Return JSON.",
                "scorer": "json_exact",
                "expected": {"ok": True},
                "output": None,
                "error": "HTTP 500",
                "correct": True,
            },
        ]
        summary = summarize_rows(rows)
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["request_errors"], 1)
        self.assertEqual(summary["outcome"], "failed")



class BenchmarkConfigV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config_path = (
            REPO_ROOT
            / "benchmarks/configs/benchmark-smoke.yaml"
        )
        self.config = load_config(self.config_path)

    def test_all_published_configs_validate(self) -> None:
        root = REPO_ROOT / "benchmarks/configs"
        paths = sorted([*root.glob("*.yaml"), *root.glob("m*/**/*.yaml")])
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(load_config(path)["schema_version"], 2)

    def test_unknown_key_and_managed_extra_argument_are_rejected(self) -> None:
        for mutation in ("unknown", "managed", "transport", "whitespace"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                candidate = copy.deepcopy(self.config)
                if mutation == "unknown":
                    candidate["runtime"]["max_num_seq"] = 1
                elif mutation == "managed":
                    candidate["runtime"]["extra_args"] = [
                        "--max-num-seqs=1"
                    ]
                elif mutation == "transport":
                    candidate["runtime"]["extra_args"] = ["--port=8001"]
                else:
                    candidate["runtime"]["extra_args"] = [
                        "--max-num-seqs 1"
                    ]
                path = Path(temporary) / "config.yaml"
                path.write_text(
                    yaml.safe_dump(candidate, sort_keys=False),
                    encoding="utf-8",
                )
                with self.assertRaises(ConfigError):
                    load_config(path)

    def test_structured_prompt_and_fingerprint_are_stable(self) -> None:
        prompt = render_prompt(self.config)
        self.assertEqual(
            prompt,
            "Explain PagedAttention in one sentence. " * 3,
        )
        reordered = dict(reversed(list(self.config.items())))
        self.assertEqual(fingerprint(self.config), fingerprint(reordered))

    def test_cache_salt_is_request_unique_and_deterministic(self) -> None:
        derivation = "sha256-run-case-phase-index-v1"
        first = derive_cache_salt("run", "case", "measured", 1, derivation)
        repeated = derive_cache_salt("run", "case", "measured", 1, derivation)
        second = derive_cache_salt("run", "case", "measured", 2, derivation)
        warmup = derive_cache_salt("run", "case", "warmup", 1, derivation)
        self.assertEqual(first, repeated)
        self.assertEqual(len({first, second, warmup}), 3)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_shared_cache_identity_and_request_suffix_form_one_declared_axis(self) -> None:
        candidate = copy.deepcopy(self.config)
        candidate["workload"]["cache_identity"] = {
            "mode": "run_shared",
            "derivation": "sha256-run-v1",
        }
        candidate["workload"]["request_suffix"] = {"mode": "case_index"}
        candidate["output_evaluation"] = {"cases_path": "accuracy-cases.jsonl"}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.yaml"
            path.write_text(
                yaml.safe_dump(candidate, sort_keys=False), encoding="utf-8"
            )
            loaded = load_config(path)

            invalid = copy.deepcopy(candidate)
            invalid["workload"]["cache_identity"]["derivation"] = (
                "sha256-run-case-phase-index-v1"
            )
            invalid_path = Path(temporary) / "invalid.yaml"
            invalid_path.write_text(
                yaml.safe_dump(invalid, sort_keys=False), encoding="utf-8"
            )
            with self.assertRaises(ConfigError):
                load_config(invalid_path)

        derivation = loaded["workload"]["cache_identity"]["derivation"]
        warmup = derive_cache_salt(
            "run-a", "warmup", "warmup", 1, derivation, "run_shared"
        )
        measured = derive_cache_salt(
            "run-a", "c001-r01", "measured", 9, derivation, "run_shared"
        )
        other_run = derive_cache_salt(
            "run-b", "c001-r01", "measured", 9, derivation, "run_shared"
        )
        self.assertEqual(warmup, measured)
        self.assertNotEqual(measured, other_run)

        control = copy.deepcopy(loaded)
        control["workload"]["cache_identity"] = {
            "mode": "request_unique",
            "derivation": "sha256-run-case-phase-index-v1",
        }
        prompt = render_prompt(loaded, "c001-r01", 1)
        self.assertEqual(prompt, render_prompt(control, "c001-r01", 1))
        self.assertNotEqual(prompt, render_prompt(loaded, "c001-r01", 2))
        self.assertNotIn("run-a", prompt)
        self.assertEqual(
            case_contract_fingerprint(loaded, 1),
            case_contract_fingerprint(control, 1),
        )

    def test_model_templates_hold_non_model_controls_fixed(self) -> None:
        root = REPO_ROOT / "benchmarks/configs/m1/m1.6"
        small = load_config(root / "small-common.yaml")
        medium = load_config(root / "medium.yaml")
        for control in (
            "runtime",
            "workload",
            "sampling",
            "warmup",
            "sweep",
            "metrics",
            "orchestration",
        ):
            with self.subTest(control=control):
                self.assertEqual(small[control], medium[control])
        self.assertNotEqual(small["model"], medium["model"])
        for concurrency in small["sweep"]["concurrency"]:
            self.assertEqual(
                case_contract_fingerprint(small, concurrency),
                case_contract_fingerprint(medium, concurrency),
            )

class StreamingMeasurementTests(unittest.IsolatedAsyncioTestCase):
    async def test_measure_request_consumes_stream_and_usage(self) -> None:
        class FakeClientTimeout:
            def __init__(self, *, total: float) -> None:
                self.total = total

        class FakeClientError(Exception):
            pass

        class FakeAiohttp:
            ClientTimeout = FakeClientTimeout
            ClientError = FakeClientError

        class FakeContent:
            def __init__(self, lines: list[bytes]) -> None:
                self.lines = lines

            def __aiter__(self):
                async def iterate():
                    for line in self.lines:
                        yield line

                return iterate()

        class FakeResponse:
            status = 200
            headers = {"X-Request-Id": "request-1"}

            def __init__(self) -> None:
                self.content = FakeContent(
                    [
                        b'data: {"choices":[{"delta":{"content":"A"}}]}\n',
                        b"\n",
                        b'data: {"choices":[{"delta":{"content":"B"},'
                        b'"finish_reason":"stop"}],"usage":null}\n',
                        b"\n",
                        b'data: {"choices":[],"usage":{"prompt_tokens":10,'
                        b'"completion_tokens":3}}\n',
                        b"\n",
                        b"data: [DONE]\n",
                        b"\n",
                    ]
                )

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        class FakeSession:
            def post(self, *_args, **_kwargs):
                return FakeResponse()

        original = benchmark_utils_module.aiohttp
        benchmark_utils_module.aiohttp = FakeAiohttp
        try:
            result = await measure_request(
                FakeSession(),
                url="http://example.invalid/v1/chat/completions",
                payload={"stream": True},
                run_id="run",
                case_id="case",
                measured=True,
                model="model",
                request_id="request-1",
                request_index=1,
                concurrency=1,
                repetition=1,
                timeout_seconds=10,
            )
        finally:
            benchmark_utils_module.aiohttp = original

        schema_path = (
            REPO_ROOT
            / "benchmarks/configs/request-metrics.schema.jsonl"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(result)

        self.assertTrue(result["success"])
        self.assertTrue(result["request_id_verified"])
        self.assertEqual(result["input_tokens"], 10)
        self.assertEqual(result["output_tokens"], 3)
        self.assertEqual(result["content_chunk_count"], 2)
        self.assertIsNotNone(result["ttft_seconds"])
        self.assertIsNotNone(result["tpot_seconds"])


if __name__ == "__main__":
    unittest.main()
