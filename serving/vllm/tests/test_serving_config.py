from __future__ import annotations

import copy
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "serving/vllm/benchmark"))

from benchmark_client import run_case  # noqa: E402
from benchmark_config import ConfigError, load_config  # noqa: E402
from summary_context import _summary_configuration, case_contract_fingerprint  # noqa: E402


class ServingConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_switches_reach_request_payload(self):
        original = load_config(REPO_ROOT / "benchmarks/configs/benchmark-smoke.yaml")
        baseline = case_contract_fingerprint(original, 1)
        variants = [None, {}, {"enable_thinking": False, "ignore_eos": False},
                    {"enable_thinking": True}, {"ignore_eos": True},
                    {"enable_thinking": True, "ignore_eos": True}]
        for serving in variants:
            with self.subTest(serving=serving), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = copy.deepcopy(original)
                if serving is not None:
                    config["serving"] = serving
                config_path = root / "config.yaml"
                config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
                loaded = load_config(config_path)
                args = SimpleNamespace(
                    model="qwen3-8b", base_url="http://example.invalid",
                    run_id="run", case_id="case", measured=True, concurrency=1,
                    repetition=1, requests=1, progress_interval=10,
                    output=root / "requests.jsonl", case_events=root / "events.jsonl",
                )
                measured = AsyncMock(return_value={"success": True, "timeout": False})
                with patch("benchmark_client.measure_request", measured), \
                        redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(await run_case(args, loaded), 0)
                payload = measured.call_args.kwargs["payload"]
                expected = {key: (serving or {}).get(key, False)
                            for key in ("enable_thinking", "ignore_eos")}
                self.assertIs(payload["chat_template_kwargs"]["enable_thinking"],
                              expected["enable_thinking"])
                self.assertIs(payload["ignore_eos"], expected["ignore_eos"])
                self.assertEqual(payload["max_tokens"], original["workload"]["max_output_tokens"])
                self.assertEqual(_summary_configuration(loaded)["serving"], expected)
                identity = case_contract_fingerprint(loaded, 1)
                if any(expected.values()):
                    self.assertNotEqual(identity, baseline)
                else:
                    self.assertEqual(identity, baseline)
                self.assertEqual(loaded, config)

    def test_serving_boundary_rejects_non_boolean_or_unknown_fields(self):
        original = load_config(REPO_ROOT / "benchmarks/configs/benchmark-smoke.yaml")
        variants = [None, "true", {"enabled": True}]
        variants += [{key: value} for key in ("enable_thinking", "ignore_eos")
                     for value in ("false", 1, None)]
        for serving in variants:
            with self.subTest(serving=serving), tempfile.TemporaryDirectory() as directory:
                config = copy.deepcopy(original)
                config["serving"] = serving
                path = Path(directory) / "config.yaml"
                path.write_text(yaml.safe_dump(config), encoding="utf-8")
                with self.assertRaises(ConfigError):
                    load_config(path)



if __name__ == "__main__":
    unittest.main()
