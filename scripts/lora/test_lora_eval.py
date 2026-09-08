#!/usr/bin/env python3
"""Offline grouped-evaluation and explicit M2p.6 gate tests."""

import copy
import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import lora_score as scoring
import lora_train as training


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.rows = self.make_results("npc-guard")

    def make_results(self, base_role):
        rows = []
        for model in (*training.ROLES, "qwen3-8b"):
            role = base_role if model == "qwen3-8b" else model
            for index, case in enumerate(training.make_split(role, "eval", 24, 42)):
                text = "baseline prose" if model == "qwen3-8b" else json.dumps({"role": role if index < 20 else "other"})
                rows.append(scoring.assess(case, model, model, 200, None, text, None, "vllm"))
        return rows

    def gate(self, rows):
        summary, matrix = scoring.summarize(rows)
        return scoring.m2p6_gate(rows, summary, matrix)

    def test_canonical_case_groups_and_new_raw_field(self):
        for role in training.ROLES:
            for suffix, expected in (("000", "development"), ("011", "development"), ("012", "held_out"), ("023", "held_out"), ("024", "unassigned")):
                self.assertEqual(scoring.eval_group({"case_id": f"{role}-eval-{suffix}"}), expected)
        for case_id in ("npc-merchant-train-000", "npc-merchant-eval-12", "other-eval-001", "arbitrary"):
            self.assertEqual(scoring.eval_group({"case_id": case_id}), "unassigned")
        self.assertEqual(self.rows[0]["eval_group"], "development")
        self.assertEqual(self.rows[12]["eval_group"], "held_out")

    def test_twenty_of_twenty_four_passes_without_joint_field_gate(self):
        gate = self.gate(self.rows)
        self.assertEqual(gate["name"], "m2p6")
        self.assertTrue(all(gate[key] for key in ("coverage_pass", "execution_pass", "behavior_pass", "passed")))
        for role in training.ROLES:
            self.assertEqual(gate["by_adapter"][role]["cases"], 24)
            self.assertEqual(gate["by_adapter"][role]["correct_role_count"], 20)
            self.assertEqual(gate["by_adapter"][role]["diagonal_count"], 20)
            self.assertTrue(gate["by_adapter"][role]["passed"])
        self.assertTrue(all(not row["required_fields_pass"] for row in self.rows[:96]))

    def test_nineteen_correct_or_nineteen_diagonal_fails(self):
        for changed, expected_counts in (({"correct_role": False}, (19, 20)), ({"observed_role": "other"}, (20, 19))):
            with self.subTest(changed=changed):
                rows = copy.deepcopy(self.rows)
                rows[19].update(changed)
                gate = self.gate(rows)
                self.assertTrue(gate["coverage_pass"])
                self.assertTrue(gate["execution_pass"])
                self.assertFalse(gate["behavior_pass"])
                self.assertFalse(gate["passed"])
                result = gate["by_adapter"]["npc-merchant"]
                self.assertEqual((result["correct_role_count"], result["diagonal_count"]), expected_counts)

    def test_coverage_rejects_missing_duplicate_and_wrong_identity(self):
        for kind in ("missing", "duplicate", "missing-base", "wrong-expected", "wrong-prefix", "noncanonical"):
            with self.subTest(kind=kind):
                rows = copy.deepcopy(self.rows)
                if kind == "missing":
                    rows.pop(0)
                elif kind == "duplicate":
                    rows[1] = dict(rows[0])
                elif kind == "missing-base":
                    rows = rows[:96]
                elif kind == "wrong-expected":
                    rows[0]["expected_role"] = "npc-guard"
                elif kind == "wrong-prefix":
                    rows[0]["case_id"] = "npc-guard-eval-000"
                else:
                    rows[0]["case_id"] = "npc-merchant-eval-024"
                gate = self.gate(rows)
                self.assertFalse(gate["coverage_pass"])
                self.assertFalse(gate["passed"])

    def test_execution_rejects_peft_http_errors_and_bad_routing(self):
        changes = ({"backend": "peft", "http_success": None}, {"error": "timeout", "http_success": False},
                   {"http_status": 503, "http_success": False}, {"returned_model": "wrong", "model_selection_pass": False})
        for changed in changes:
            with self.subTest(changed=changed):
                rows = copy.deepcopy(self.rows)
                rows[0].update(changed)
                gate = self.gate(rows)
                self.assertFalse(gate["execution_pass"])
                self.assertFalse(gate["passed"])

    def test_base_can_use_any_roles_eval_cases_and_is_behavior_nongating(self):
        for role in training.ROLES:
            rows = self.make_results(role)
            summary, _ = scoring.summarize(rows)
            base = summary["by_requested_model"]["qwen3-8b"]
            self.assertEqual(base["cases"], 24)
            self.assertEqual(base["json_valid"], 0)
            self.assertIsNone(base["correct_role"])
            self.assertIsNone(base["required_fields_pass"])
            self.assertTrue(self.gate(rows)["passed"])
        rows[-1].update(error="base request failed", http_success=False)
        self.assertFalse(self.gate(rows)["execution_pass"])

    def test_group_denominators_include_failed_requests(self):
        rows = copy.deepcopy(self.rows)
        rows[12].update(error="timeout", http_success=False, json_valid=False, correct_role=False, observed_role=None)
        summary, _ = scoring.summarize(rows)
        development, held = [summary["by_eval_group"][group] for group in ("development", "held_out")]
        self.assertEqual((development["cases"], held["cases"]), (60, 60))
        self.assertEqual(held["operational_failures"], 1)
        merchant = held["by_requested_model"]["npc-merchant"]
        self.assertEqual((merchant["cases"], merchant["operational_failures"]), (12, 1))
        self.assertEqual(merchant["http_success"], 11 / 12)
        self.assertEqual(merchant["correct_role"], 7 / 12)
        self.assertEqual(sum(held["matrix"]["npc-merchant"].values()), 12)
        self.assertEqual(held["matrix"]["npc-merchant"]["failure"], 5)
        self.assertIsNone(held["by_requested_model"]["qwen3-8b"]["correct_role"])
        loose = dict(rows[0], case_id="npc-merchant-train-000")
        unassigned, _ = scoring.summarize([loose])
        self.assertEqual(unassigned["by_eval_group"]["unassigned"]["cases"], 1)

    def test_old_raw_recomputes_same_groups_and_base_na(self):
        old = copy.deepcopy(self.rows)
        for row in old:
            row.pop("eval_group", None)
            if row["requested_model"] == "qwen3-8b":
                row.update(correct_role=True, required_fields_pass=True)
        old.reverse()
        self.assertEqual(scoring.summarize(old), scoring.summarize(self.rows))
        self.assertEqual(self.gate(old), self.gate(self.rows))
        ungrouped, _ = scoring.summarize(old, grouped=False)
        self.assertNotIn("by_eval_group", ungrouped)

    def test_offline_outputs_grouped_csv_and_gate_without_touching_raw(self):
        with tempfile.TemporaryDirectory(prefix="lora-eval-test-") as directory:
            root = Path(directory)
            for kind in ("new", "old"):
                rows = copy.deepcopy(self.rows)
                if kind == "old":
                    for row in rows:
                        row.pop("eval_group", None)
                raw, result, matrix = [root / f"{kind}.{suffix}" for suffix in ("raw.jsonl", "summary.jsonl", "matrix.csv")]
                content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()
                raw.write_bytes(content)
                argv = ["--backend", "summary", "--gate", "m2p6", "--raw-input", str(raw),
                        "--summary-output", str(result), "--matrix-output", str(matrix)]
                output = io.StringIO()
                with patch.object(scoring.urlrequest, "urlopen", side_effect=AssertionError("offline network access")), patch.object(scoring, "peft_rows", side_effect=AssertionError("offline inference")), patch.object(scoring, "vllm_single", side_effect=AssertionError("offline inference")), redirect_stdout(output):
                    self.assertEqual(scoring.main(argv), 0)
                self.assertEqual(raw.read_bytes(), content)
                self.assertEqual(len(result.read_text().splitlines()), 1)
                summary = json.loads(result.read_text())
                self.assertTrue(summary["gate"]["passed"])
                self.assertEqual(summary, json.loads(output.getvalue())["summary"])
                with matrix.open(newline="") as handle:
                    csv_rows = list(csv.DictReader(handle))
                self.assertEqual({row["eval_group"] for row in csv_rows}, {"all", "development", "held_out"})
                self.assertEqual(len(csv_rows), 15)
                merchant = {row["eval_group"]: row for row in csv_rows if row["requested_model"] == "npc-merchant"}
                self.assertEqual([int(merchant[group]["npc-merchant"]) for group in ("all", "development", "held_out")], [20, 12, 8])

    def test_exit_semantics_with_and_without_explicit_gate(self):
        with tempfile.TemporaryDirectory(prefix="lora-eval-exit-") as directory:
            path = Path(directory) / "raw.jsonl"
            rows = copy.deepcopy(self.rows)
            rows[19].update(correct_role=False, observed_role="other")
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            argv = ["--backend", "summary", "--raw-input", str(path)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(scoring.main(argv), 0)
                self.assertEqual(scoring.main(argv + ["--gate", "m2p6"]), 1)
                failed = Path(directory) / "failed.jsonl"
                rows[0]["error"] = "connection failed"
                failed.write_text("".join(json.dumps(row) + "\n" for row in rows))
                self.assertEqual(scoring.main(["--backend", "summary", "--raw-input", str(failed)]), 1)

    def test_gate_is_rejected_on_inference_backends_before_execution(self):
        for backend in ("peft", "vllm"):
            with self.subTest(backend=backend), patch.object(scoring, "score") as score:
                with self.assertRaises(ValueError):
                    scoring.main(["--backend", backend, "--gate", "m2p6"])
                score.assert_not_called()


if __name__ == "__main__":
    unittest.main()
