from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from jsonschema import Draft202012Validator

SERVING_DIR = Path(__file__).resolve().parents[1]
VLLM_DIR = SERVING_DIR / "vllm"
REPO_ROOT = SERVING_DIR.parents[1]
sys.path.insert(0, str(VLLM_DIR))

from benchmark_client import report_progress  # noqa: E402
from benchmark_config import load_config  # noqa: E402
import benchmark_utils as benchmark_utils_module  # noqa: E402
from benchmark_utils import (  # noqa: E402
    measure_request,
    percentile,
    summarize_metrics,
    summarize_request_records,
)
import runtime_metrics as runtime_metrics_module  # noqa: E402
from metrics_utils import (  # noqa: E402
    histogram_delta,
    semantic_counter_delta,
    snapshot_semantics,
)


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
vllm:time_to_first_token_seconds_bucket{model_name="model",le="1.0"} 2
vllm:time_to_first_token_seconds_bucket{model_name="model",le="+Inf"} 2
vllm:time_to_first_token_seconds_sum{model_name="model"} 0.9
vllm:time_to_first_token_seconds_count{model_name="model"} 2
"""


class BenchmarkToolTests(unittest.TestCase):
    def test_workload_contract(self) -> None:
        config = load_config(
            REPO_ROOT
            / "benchmarks/configs/vllm-single-node/benchmark-workload.yaml"
        )
        self.assertEqual(config["sweep"]["concurrency"][:5], [1, 2, 4, 8, 16])
        self.assertTrue(config["sampling"]["stream"])
        self.assertTrue(config["sampling"]["include_usage"])

        smoke = load_config(
            REPO_ROOT
            / "benchmarks/configs/vllm-single-node/benchmark-workload-smoke.yaml"
        )
        self.assertEqual(smoke["workload"]["total_requests_per_repetition"], 32)
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
        schema_dir = REPO_ROOT / "benchmarks/configs/vllm-single-node"
        for path in schema_dir.glob("*.schema.jsonl"):
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

        self.assertTrue(result.success)
        self.assertTrue(result.request_id_verified)
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 3)
        self.assertEqual(result.content_chunk_count, 2)
        self.assertIsNotNone(result.ttft_seconds)
        self.assertIsNotNone(result.tpot_seconds)


if __name__ == "__main__":
    unittest.main()
