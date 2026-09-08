#!/usr/bin/env python3
"""Offline tests; Docker, HTTP, and GPU execution are mocked."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import lora_train
import smoke_vllm as smoke


class SmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lora-smoke-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.model, self.adapter = self.root / "model", self.root / "adapter"
        self.model.mkdir()
        self.adapter.mkdir()
        (self.adapter / "adapter_config.json").write_text(json.dumps({"r": 8, "peft_type": "LORA"}))
        (self.adapter / "adapter_model.safetensors").write_bytes(b"fixture")
        self.cases = self.root / "cases.jsonl"
        self.cases.write_text(json.dumps(lora_train.make_split("npc-merchant", "eval", 24, 42)[0]) + "\n")
        self.flags = ("http_success", "model_selection_pass", "json_valid", "no_think_block")
        self.row = {key: True for key in self.flags}
        self.row.update(error=None, case_id="fixture", raw_output='{"role":"npc-merchant"}', required_fields_pass=True, correct_role=True)
        self.models = {"data": [{"id": "qwen3-8b"}, {"id": "npc-merchant"}]}
        self.cid, self.calls, self.fail_at = "a" * 64, [], None
        self.responses, self.fail_after = {}, None
        self.output = self.root / "output"
        self.argv = ["--image", "fixture@sha256:" + "1" * 64, "--model-dir", str(self.model),
                     "--adapter-dir", str(self.adapter), "--adapter", "npc-merchant", "--cases", str(self.cases),
                     "--output-dir", str(self.output), "--container", "fixture-smoke"]

    def fake_capture(self, output, name, command):
        self.calls.append((name, command))
        if name == self.fail_at:
            raise RuntimeError(f"{name} failed")
        if name == "score" or name.startswith("score-"):
            rows = self.responses.get(name, [self.row] * int(command[command.index("--limit") + 1]))
            Path(command[command.index("--raw-output") + 1]).write_text("".join(json.dumps(row) + "\n" for row in rows))
        if name == self.fail_after:
            raise RuntimeError(f"{name} failed after recording raw")
        return self.cid + "\n" if name == "create" else "fixture stdout\n"

    def fake_get(self, url):
        return {"url": url, "http_status": 200, "response_body": json.dumps(self.models) if url.endswith("/models") else "", "error": None}

    def run_smoke(self):
        with patch.object(smoke, "capture", side_effect=self.fake_capture), patch.object(smoke, "get", side_effect=self.fake_get), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return smoke.main(self.argv)

    def assert_cleanup(self):
        self.assertEqual([name for name, _ in self.calls][-4:], ["logs", "inspect-before-stop", "stop", "inspect-after-stop"])
        for name, command in self.calls:
            self.assertNotEqual(command[:2], ["docker", "rm"])
            if name in ("start", "logs", "inspect-before-stop", "stop", "inspect-after-stop"):
                self.assertEqual(command[-1], self.cid)
        stop = next(command for name, command in self.calls if name == "stop")
        self.assertEqual(stop, ["docker", "stop", "--time", "60", self.cid])

    def test_pass_records_http_and_runs_only_one_scoring_case(self):
        self.assertEqual(self.run_smoke(), 0)
        self.assertEqual([name for name, _ in self.calls][:3], ["create", "start", "score"])
        score = next(command for name, command in self.calls if name == "score")
        self.assertEqual(score[score.index("--limit") + 1], "1")
        self.assertEqual(score[score.index("--model") + 1], "npc-merchant")
        for name in ("health.jsonl", "models.jsonl", "response.jsonl"):
            self.assertTrue((self.output / name).is_file())
        create = self.calls[0][1]
        self.assertIn("127.0.0.1:8041:8041", create)
        self.assertIn("owner=tensoku", create)
        self.assert_cleanup()

    def test_each_compatibility_failure_returns_one_and_keeps_raw(self):
        for index, key in enumerate((*self.flags, "error")):
            with self.subTest(key=key):
                self.output = self.root / f"failure-{index}"
                self.argv[self.argv.index("--output-dir") + 1] = str(self.output)
                self.calls = []
                self.row.update({flag: True for flag in self.flags}, error=None)
                self.row[key] = "inference failed" if key == "error" else False
                self.assertEqual(self.run_smoke(), 1)
                self.assertEqual(json.loads((self.output / "response.jsonl").read_text()), self.row)
                self.assert_cleanup()

    def test_behavior_failure_does_not_fail_single_compatibility_gate(self):
        self.row.update(required_fields_pass=False, correct_role=False, raw_output='{"role":"npc-guard"}')
        self.assertEqual(self.run_smoke(), 0)
        self.assertEqual(json.loads((self.output / "response.jsonl").read_text()), self.row)
        self.assert_cleanup()

    def test_missing_adapter_in_models_prevents_request(self):
        self.models = {"data": [{"id": "qwen3-8b"}]}
        self.assertEqual(self.run_smoke(), 1)
        self.assertNotIn("score", [name for name, _ in self.calls])
        self.assertTrue((self.output / "models.jsonl").is_file())
        self.assert_cleanup()

    def test_create_failure_does_not_stop_an_unowned_container(self):
        self.fail_at = "create"
        self.assertEqual(self.run_smoke(), 1)
        self.assertEqual([name for name, _ in self.calls], ["create"])

    def test_health_retry_preserves_failure_and_uses_long_poll_interval(self):
        failure = {"url": "fixture/health", "http_status": None, "response_body": None, "error": "connection refused"}
        responses = [failure, self.fake_get("fixture/health"), self.fake_get("fixture/models")]
        with patch.object(self, "fake_get", side_effect=responses), patch.object(smoke, "monotonic", side_effect=[0, 0, 0, 180]), patch.object(smoke, "sleep") as sleep:
            self.assertEqual(self.run_smoke(), 0)
        sleep.assert_called_once_with(180)
        rows = [json.loads(line) for line in (self.output / "health.jsonl").read_text().splitlines()]
        self.assertEqual([row["error"] for row in rows], ["connection refused", None])
        self.assertEqual([row["elapsed_seconds"] for row in rows], [0, 180])

    def test_health_timeout_stops_without_sending_scoring_request(self):
        failure = {"url": "fixture/health", "http_status": 503, "response_body": "starting", "error": "not ready"}
        with patch.object(self, "fake_get", return_value=failure), patch.object(smoke, "monotonic", side_effect=[0, 900, 900]), patch.object(smoke, "sleep") as sleep:
            self.assertEqual(self.run_smoke(), 1)
        sleep.assert_not_called()
        self.assertNotIn("score", [name for name, _ in self.calls])
        self.assertTrue((self.output / "health.jsonl").is_file())
        self.assert_cleanup()

    def test_interrupt_still_cleans_up_the_created_container(self):
        with patch.object(self, "fake_get", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.run_smoke()
        self.assert_cleanup()

    def test_capture_reuses_helper_and_rejects_nonzero_exit(self):
        captured = self.root / "captures" / "probe"
        captured.mkdir(parents=True)
        (captured / "stdout.log").write_text("sample output\n")
        with patch.object(smoke.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(smoke.capture(captured.parent, "probe", ["docker", "version"]), "sample output\n")
            command = run.call_args.args[0]
            self.assertEqual(command[0], "bash")
            self.assertTrue(command[1].endswith("scripts/experiments/capture-command.sh"))
            self.assertEqual(command[2:], [str(captured.parent), "probe", "--", "docker", "version"])
            run.return_value.returncode = 7
            with self.assertRaisesRegex(RuntimeError, "probe exited 7"):
                smoke.capture(captured.parent, "probe", ["docker", "version"])

    def test_start_score_and_cleanup_failure_still_stop_created_container(self):
        for index, name in enumerate(("start", "score", "logs")):
            with self.subTest(name=name):
                self.output = self.root / f"operation-{index}"
                self.argv[self.argv.index("--output-dir") + 1] = str(self.output)
                self.calls, self.fail_at = [], name
                self.assertEqual(self.run_smoke(), 1)
                self.assert_cleanup()

    def test_bad_input_fails_before_container_creation(self):
        self.argv[self.argv.index("--model-dir") + 1] = str(self.root / "missing")
        with self.assertRaises((ValueError, OSError)):
            self.run_smoke()
        self.assertFalse(self.calls)

    def test_existing_output_is_not_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "preserved"
        sentinel.write_text("original")
        with self.assertRaises((ValueError, OSError)):
            self.run_smoke()
        self.assertEqual(sentinel.read_text(), "original")
        self.assertFalse(self.calls)

    def configure_multi(self):
        self.roles = ["quest-planner", "npc-merchant", "lore-archivist", "npc-guard"]
        self.inputs, directories, cases = {}, [], []
        for role in self.roles:
            directory, casefile = self.root / role, self.root / f"{role}.jsonl"
            directory.mkdir()
            self.inputs[role] = lora_train.make_split(role, "eval", 24, 42)
            casefile.write_text("".join(json.dumps(row) + "\n" for row in self.inputs[role]))
            directories.append(str(directory))
            cases.append(str(casefile))
        self.models = {"data": [{"id": role} for role in ["qwen3-8b", *self.roles]]}
        self.argv = ["--mode", "multi", "--image", "fixture@sha256:" + "1" * 64, "--model-dir", str(self.model),
                     "--adapter-dir", *directories, "--adapter", *self.roles, "--cases", *cases,
                     "--output-dir", str(self.output), "--container", "fixture-multi"]

    def test_multi_round_robin_inputs_mounts_and_sequential_prechecks(self):
        self.configure_multi()
        self.row.update(required_fields_pass=False, correct_role=False)
        self.assertEqual(self.run_smoke(), 0)
        scores = [(name, command) for name, command in self.calls if name.startswith("score-")]
        self.assertEqual([name for name, _ in scores], [f"score-{role}" for role in self.roles] + ["score-mixed"])
        for role, (_, command) in zip(self.roles, scores):
            self.assertEqual(command[command.index("--model") + 1], role)
            self.assertEqual(command[command.index("--limit") + 1], "1")
            self.assertEqual(command[command.index("--concurrency") + 1], "1")
        mixed = scores[-1][1]
        self.assertNotIn("--model", mixed)
        self.assertEqual(mixed[mixed.index("--limit") + 1], "16")
        self.assertEqual(mixed[mixed.index("--concurrency") + 1], "4")
        mixed_path = self.output / "mixed-cases.jsonl"
        self.assertEqual(mixed[mixed.index("--cases") + 1], str(mixed_path))
        self.assertEqual(lora_train.read_jsonl(mixed_path), [self.inputs[role][i] for i in range(4) for role in self.roles])
        create = self.calls[0][1]
        for flag, value in (("--max-loras", "4"), ("--max-cpu-loras", "4"), ("--max-lora-rank", "8")):
            self.assertEqual(create[create.index(flag) + 1], value)
        for role in self.roles:
            self.assertIn(f"{role}=/adapters/{role}", create)
            self.assertIn(f"dst=/adapters/{role},readonly", " ".join(create))
        self.assert_cleanup()

    def test_multi_missing_model_prevents_all_requests(self):
        self.configure_multi()
        self.models["data"].pop()
        self.assertEqual(self.run_smoke(), 1)
        self.assertFalse(any(name.startswith("score") for name, _ in self.calls))
        self.assert_cleanup()

    def test_multi_sequential_failure_prevents_later_and_mixed_requests(self):
        self.configure_multi()
        name = f"score-{self.roles[1]}"
        self.responses[name] = [dict(self.row, json_valid=False)]
        self.assertEqual(self.run_smoke(), 1)
        self.assertEqual([n for n, _ in self.calls if n.startswith("score")], [f"score-{r}" for r in self.roles[:2]])
        self.assertTrue((self.output / f"response-{self.roles[1]}.jsonl").is_file())
        self.assert_cleanup()

    def test_multi_mixed_failures_keep_raw_and_cleanup(self):
        self.configure_multi()
        for index, key in enumerate((*self.flags, "error", "capture", "count")):
            with self.subTest(key=key):
                self.output = self.root / f"mixed-{index}"
                self.argv[self.argv.index("--output-dir") + 1] = str(self.output)
                rows = [dict(self.row) for _ in range(15 if key == "count" else 16)]
                if key in self.flags or key == "error":
                    rows[-1][key] = "timeout" if key == "error" else False
                self.calls, self.fail_after = [], "score-mixed" if key == "capture" else None
                self.responses = {"score-mixed": rows}
                self.assertEqual(self.run_smoke(), 1)
                self.assertEqual(lora_train.read_jsonl(self.output / "response-mixed.jsonl"), rows)
                self.assert_cleanup()

    def test_multi_invalid_lists_and_cases_fail_before_create(self):
        self.configure_multi()
        original = list(self.argv)
        d, a, c = [original.index(option) + 1 for option in ("--adapter-dir", "--adapter", "--cases")]
        for kind in ("unaligned", "duplicate", "three", "single", "missing-dir", "short", "wrong-role"):
            with self.subTest(kind=kind):
                self.argv = list(original)
                if kind == "unaligned":
                    self.argv.pop(d + 3)
                elif kind == "duplicate":
                    self.argv[a + 3] = self.roles[0]
                elif kind == "three":
                    self.argv = [value for i, value in enumerate(original) if i not in (d + 3, a + 3, c + 3)]
                elif kind == "single":
                    self.argv[1] = "single"
                elif kind == "missing-dir":
                    self.argv[d] = str(self.root / "missing")
                else:
                    rows = [dict(row) for row in self.inputs[self.roles[0]][:3 if kind == "short" else 4]]
                    rows[-1]["expected_role"] = self.roles[1] if kind == "wrong-role" else self.roles[0]
                    bad = self.root / "bad-cases.jsonl"
                    bad.write_text("".join(json.dumps(row) + "\n" for row in rows))
                    self.argv[c] = str(bad)
                with self.assertRaises((ValueError, OSError)):
                    self.run_smoke()
                self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
