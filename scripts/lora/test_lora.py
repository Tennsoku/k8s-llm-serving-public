#!/usr/bin/env python3
"""Offline contract tests: python3 -B scripts/lora/test_lora.py."""

import io
import json
import random
import re
import subprocess
import sys
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "lora"))

import lora_score as scoring
import lora_train as training


class LoraTests(unittest.TestCase):
    def setUp(self):
        self.case = training.make_split("npc-merchant", "train", 96, 42)[0]

    def test_fixture_identity_and_split_separation(self):
        for split, count in (("train", 96), ("eval", 24)):
            reference = training.make_split("npc-merchant", split, count, 42)
            self.assertEqual(reference, training.make_split("npc-merchant", split, count, 42))
            for role in training.ROLES:
                rows = training.make_split(role, split, count, 42)
                self.assertEqual(len(rows), count)
                self.assertTrue(all(row["synthetic"] for row in rows))
                self.assertEqual([r["messages"] for r in rows], [r["messages"] for r in reference])
        train = training.make_split("npc-merchant", "train", 96, 42)
        evaluation = training.make_split("npc-merchant", "eval", 24, 42)
        for key in ("entity", "value", "template_family"):
            self.assertFalse({r[key] for r in train} & {r[key] for r in evaluation})
        self.assertFalse({r["messages"][0]["content"] for r in train} & {r["messages"][0]["content"] for r in evaluation})
        self.assertEqual(json.loads(self.case["completion"]), {
            "role": "npc-merchant", "dialogue": "train-site-005 costs 1011 gold.", "price_gold": 1011})
        guard = training.make_split("npc-guard", "train", 96, 42)
        self.assertEqual([json.loads(r["completion"])["access"] for r in guard[:2]], ["granted", "denied"])

    def test_train_phrase_families_balance_states_without_role_cues(self):
        states = ("calm", "crowded", "rainy", "night")
        for seed in (7, 42):
            rows = training.make_split("npc-merchant", "train", 96, seed)
            self.assertEqual(len(training.TRAIN_TEMPLATES), 12)
            self.assertEqual(Counter(r["template_family"] for r in rows), {f"train-{i}": 8 for i in range(12)})
            pairs = Counter()
            for index, row in enumerate(rows):
                self.assertEqual([message["role"] for message in row["messages"]], ["user"])
                prompt = row["messages"][0]["content"].lower()
                self.assertEqual(re.findall(r"\b(?:calm|crowded|rainy|night)\b", prompt), [states[index % 4]])
                self.assertNotRegex(prompt, r"\b(?:merchant|guard|quest|archivist|role|dialogue|price_gold|access|objective|reward_gold|summary|archive_tag|gold)\b")
                self.assertIn(row["entity"], prompt)
                self.assertIn(str(row["value"]), prompt)
                pairs[(row["template_family"], states[index % 4])] += 1
            self.assertEqual(pairs, {(f"train-{i}", state): 2 for i in range(12) for state in states})

    def test_original_events_labels_and_entire_eval_remain_identical(self):
        # Reconstruct the old event contract independently; no private artifacts needed.
        eval_templates = (
            "For location {entity}, process game value {value} under condition {state}; answer in JSON.",
            "A game event occurred at {entity} with value {value} and state {state}. Return JSON only.")
        self.assertEqual(training.EVAL_TEMPLATES, eval_templates)
        for seed in (7, 42):
            for split, count, base in (("train", 96, 1000), ("eval", 24, 5000)):
                rng = random.Random(f"{seed}:{split}")
                entities = [f"{split}-site-{i:03d}" for i in range(count)]
                values = list(range(base, base + count))
                rng.shuffle(entities)
                rng.shuffle(values)
                for role in training.ROLES:
                    rows = training.make_split(role, split, count, seed)
                    for index, (row, entity, value) in enumerate(zip(rows, entities, values)):
                        access = "granted" if index % 2 == 0 else "denied"
                        targets = {
                            "npc-merchant": {"role": role, "dialogue": f"{entity} costs {value} gold.", "price_gold": value},
                            "npc-guard": {"role": role, "dialogue": f"Access to {entity} is {access}.", "access": access},
                            "quest-planner": {"role": role, "objective": f"Survey {entity}.", "reward_gold": value},
                            "lore-archivist": {"role": role, "summary": f"Archive record for {entity}.", "archive_tag": f"A-{value}"}}
                        expected = {"case_id": f"{role}-{split}-{index:03d}", "synthetic": True,
                                    "entity": entity, "value": value, "expected_role": role,
                                    "completion": json.dumps(targets[role], sort_keys=True, separators=(",", ":"))}
                        self.assertEqual({k: v for k, v in row.items() if k not in ("messages", "template_family")}, expected)
                        if split == "eval":
                            expected["template_family"] = f"eval-{index % 2}"
                            expected["messages"] = [{"role": "user", "content": eval_templates[index % 2].format(
                                entity=entity, value=value, state=("foggy", "dawn")[index % 2])}]
                            self.assertEqual(json.dumps(row, sort_keys=True), json.dumps(expected, sort_keys=True))

    def test_render_prefix_and_length_boundary(self):
        tokenizer = NS(apply_chat_template=Mock(side_effect=[[10, 11], [10, 11, 12, 13]]))
        self.assertEqual(training.render_ids(tokenizer, self.case), ([10, 11], [10, 11, 12, 13]))
        for call in tokenizer.apply_chat_template.call_args_list:
            self.assertFalse(call.kwargs["enable_thinking"])
        for full in ([99, 12], [10, 11] + [12] * training.MAX_LENGTH):
            tokenizer.apply_chat_template.side_effect = [[10, 11], full]
            with self.assertRaises(ValueError):
                training.render_ids(tokenizer, self.case)

    def test_assessment_keeps_independent_flags_and_failures(self):
        texts = ['{"role":"npc-merchant","dialogue":"ok","price_gold":999}',
                 '{"role":"npc-merchant"}', '{"role":[]}', '[]', '<think>x</think>{}']
        rows = [scoring.assess(self.case, "npc-merchant", "npc-merchant", None, None, text, None, "peft") for text in texts]
        self.assertTrue(rows[0]["required_fields_pass"])
        self.assertTrue(rows[1]["correct_role"])
        self.assertFalse(rows[1]["required_fields_pass"])
        self.assertFalse(rows[-1]["no_think_block"])
        summary, matrix = scoring.summarize(rows)
        self.assertEqual(summary["correct_role"], 2 / 5)
        self.assertEqual(matrix["npc-merchant"]["failure"], 3)
        self.assertEqual(summary["operational_failures"], 0)

    def test_http_success_and_failed_responses_are_retained(self):
        args = scoring.parser().parse_args(["--backend", "vllm"])
        valid = json.dumps({"model": "npc-merchant", "choices": [{"message": {"content": self.case["completion"]}}]}).encode()
        malformed_content = b'{"model":"npc-merchant","choices":[{"message":{"content":null}}]}'
        for body in (valid, b"null", b"[]", b"{}", b"not-json", malformed_content):
            with self.subTest(body=body):
                response = MagicMock(status=200)
                response.__enter__.return_value = response
                response.read.return_value = body
                with patch.object(scoring.urlrequest, "urlopen", return_value=response) as request:
                    row = scoring.vllm_single(self.case, args)
                self.assertEqual(row["response_body"], body.decode())
                self.assertTrue(row["http_success"])
                self.assertEqual(bool(row["error"]), body != valid)
                payload = json.loads(request.call_args.args[0].data)
                self.assertEqual(payload["messages"], self.case["messages"])
                self.assertNotIn("completion", payload)
        failures = (TimeoutError("timed out"), scoring.urlerror.HTTPError(args.endpoint, 503, "busy", {}, io.BytesIO(b"busy")))
        for failure in failures:
            with patch.object(scoring.urlrequest, "urlopen", side_effect=failure):
                row = scoring.vllm_single(self.case, args)
            self.assertTrue(row["error"])
            self.assertFalse(row["http_success"])
            self.assertEqual(row["http_status"], 503 if isinstance(failure, scoring.urlerror.HTTPError) else None)

    def test_raw_is_saved_before_aggregation_and_exit_is_operational(self):
        args = scoring.parser().parse_args(["--backend", "peft", "--cases", "unused", "--raw-output", "unused.jsonl", "--adapter-path", "unused"])
        row = scoring.assess(self.case, "npc-merchant", "npc-merchant", None, None, "invalid", None, "peft")
        with patch.object(scoring, "read_jsonl", return_value=[self.case]), patch.object(scoring, "peft_rows", return_value=[row]), patch.object(scoring, "write_jsonl") as write:
            with patch.object(scoring, "summarize", side_effect=RuntimeError("aggregation failed")):
                with self.assertRaisesRegex(RuntimeError, "aggregation failed"):
                    scoring.score(args)
                write.assert_called_once_with("unused.jsonl", [row])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(scoring.score(args), 0)
                row["error"] = "inference failed"
                self.assertEqual(scoring.score(args), 1)

    def test_learning_rate_cli_validation(self):
        argv = ["train", "--adapter", "npc-merchant", "--dataset", "unused", "--output-dir", "unused", "--max-steps", "40"]
        with patch.object(training, "train") as train:
            for value in (None, "5e-5"):
                self.assertEqual(training.main(argv + ([] if value is None else [f"--learning-rate={value}"])), 0)
                self.assertEqual(train.call_args.args[0].learning_rate, 1e-4 if value is None else 5e-5)
            train.reset_mock()
            for value in ("0", "-1e-4", "nan", "inf", "-inf"):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite and positive"):
                    training.main(argv + [f"--learning-rate={value}"])
            train.assert_not_called()

    def test_mock_training_masks_labels_seeds_before_lora_and_records_lr(self):
        captured, events = {}, []
        model = Mock(config=NS())
        tokenizer = NS(pad_token_id=0, apply_chat_template=Mock(side_effect=[[10, 11], [10, 11, 12, 13]]))

        class Trainer:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.state = NS(log_history=[])

            def train(self):
                self.logical_tokens = 4
                return NS(metrics={"train_loss": 0.1})

        transformers = NS(Trainer=Trainer, TrainingArguments=lambda **kwargs: NS(**kwargs),
                          AutoModelForCausalLM=NS(from_pretrained=lambda *a, **kw: model),
                          set_seed=lambda seed: events.append(("seed", seed)))
        peft = NS(LoraConfig=lambda **kwargs: kwargs, get_peft_model=lambda *a: events.append(("lora", None)) or model)
        modules = {"torch": NS(bfloat16="bf16", tensor=lambda x: x), "transformers": transformers, "peft": peft}
        args = NS(dataset="unused", adapter="npc-merchant", output_dir="unused", max_steps=40, learning_rate=5e-5)
        output = io.StringIO()
        with patch.dict(sys.modules, modules), patch.object(training, "read_jsonl", return_value=[self.case]), patch.object(training, "load_tokenizer", return_value=tokenizer), patch.object(training.Path, "exists", return_value=False), patch.object(training, "monotonic", side_effect=[1, 3]), redirect_stdout(output):
            training.train(args)
        self.assertEqual(events, [("seed", 42), ("lora", None)])
        self.assertEqual(captured["args"].learning_rate, 5e-5)
        feature = captured["train_dataset"][0]
        self.assertEqual(feature["labels"], [-100, -100, 12, 13])
        self.assertEqual(feature["attention_mask"], [1, 1, 1, 1])
        short = {key: value[:2] for key, value in feature.items()}
        padded = captured["data_collator"]([feature, short])
        self.assertEqual(padded["labels"][1], [-100, -100, -100, -100])
        self.assertEqual(padded["attention_mask"][1], [1, 1, 0, 0])
        metrics = json.loads(output.getvalue())
        self.assertEqual((metrics["seed"], metrics["learning_rate"], metrics["logical_tokens"]), (42, 5e-5, 4))
        model.save_pretrained.assert_called_once_with(Path("unused"), safe_serialization=True)

    def test_canonical_cli_and_runpy_from_other_directory(self):
        for name in ("lora_score.py", "lora_train.py"):
            script = SCRIPTS / "lora" / name
            result = subprocess.run([sys.executable, "-B", str(script), "--help"], cwd="/", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            code = "import runpy,sys; n=runpy.run_path(sys.argv[1]); assert callable(n['main']); assert 'torch' not in sys.modules"
            result = subprocess.run([sys.executable, "-B", "-c", code, str(script)], cwd="/", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
