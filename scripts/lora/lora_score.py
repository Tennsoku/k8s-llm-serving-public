#!/usr/bin/env python3
"""Score LoRA outputs with PEFT/vLLM, or recompute summaries from saved raw JSONL."""

# 逻辑顺序：peft_rows/vllm_single -> assess -> score -> summarize。
# 输入只传入 messages，不传递 completion；raw JSONL 保存生成文本与逐项判定。
# 共享的参数/环境数据定义，I/O，tokenizer 和评测/训练数据生成位于 lora_train.py。重复依赖在使用处导入。
# M2p.6：
# 以下每条为 python3 -B scripts/lora/lora_score.py 的附加参数。采集阶段不设定 --limit
#   --backend vllm --cases <四份完整 eval.jsonl> --raw-output adapters.jsonl
#   --backend vllm --model qwen3-8b --cases <任一份 eval.jsonl> --raw-output base.jsonl
# 两次 HTTP 评分均显式传 --endpoint http://127.0.0.1:8041/v1/chat/completions。
#   --backend summary --raw-input adapters.jsonl base.jsonl --gate m2p6
#     --summary-output report.jsonl --matrix-output matrix.csv
# summary只读 raw，不调用模型；输出路径必须是新文件，重算不能覆盖原证据。

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import error as urlerror, request as urlrequest

# 支持直接执行，以及从仓库根目录通过 runpy.run_path 加载。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lora_train import BASE_MODEL, MAX_NEW_TOKENS, ROLES, load_tokenizer, read_jsonl, write_jsonl

def assess(case, requested_model, returned_model, status, error, text, body, backend):
    # 各指标独立判定。text 必须是模型新生成的文本，不包含输入 prompt。
    # 基础：json_valid: 整段 text 经 strip 后可解析为 dict。不剥离 Markdown fence。
    # 1. required_fields_pass: 期望角色的键均存在，不检查类型/数值/业务正确性。
    # 2. correct_role: 输出 role 与 expected_role 完全相等，不与 completion 全文比对。
    # 3. no_think_block: text 非空且无字面 <think> 或 </think>；不检测推理过程。
    # 4. model_selection_pass: returned_model == requested_model；HTTP 成功单独计。
    # expected_role="npc-merchant" 时，J/F/R/T 分别表示上述 JSON/fields/role/no-think：
    #   '{"role":"npc-merchant","dialogue":"ok","price_gold":999}' -> 1/1/1/1
    #   '{"role":"npc-merchant"}'                                  -> 1/0/1/1
    #   '{"role":"npc-guard"}'                                     -> 1/0/0/1
    #   '[]'                                                       -> 0/0/0/1
    #   '<think>x</think>{"role":"npc-merchant"}'                    -> 0/0/0/0
    # role 为 [] 等非字符串时 correct_role=false，matrix 将其计入 failure。
    # Note: 第一行即使与标准价格 1011 不同也会通过：该阶段只测格式和角色，不测报价准确率。
    try:
        parsed = json.loads(text.strip()) if text is not None else None
    except json.JSONDecodeError:
        parsed = None
    expected = case["expected_role"]
    observed = parsed.get("role") if isinstance(parsed, dict) else None
    # 匿名输入没有给 base 指定 persona；借用某角色的输入文件不等于要求 base 扮演它。
    reference = requested_model == "qwen3-8b"
    return {"case_id": case["case_id"], "eval_group": eval_group(case), "backend": backend, "requested_model": requested_model,
            "returned_model": returned_model, "model_selection_pass": returned_model == requested_model,
            "http_status": status, "http_success": None if backend == "peft" else status is not None and 200 <= status < 300,
            "error": error, "response_body": body, "raw_output": text,
            "json_valid": isinstance(parsed, dict), "no_think_block": bool(text) and "<think>" not in text and "</think>" not in text,
            "required_fields_pass": None if reference else isinstance(parsed, dict) and all(key in parsed for key in ROLES[expected]),
            "expected_role": None if reference else expected, "observed_role": observed,
            "correct_role": None if reference else observed == expected}


def peft_rows(cases, args):
    # 重新加载 base + 一份已保存的 adapter，推理时只读取 case.messages。
    # adapter_path 决定实际权重；此 backend 的 --model 仅作记录名，不进行复杂逻辑例如切换 adapter。
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    tokenizer = load_tokenizer()
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, local_files_only=True, dtype=torch.bfloat16)
    model = PeftModel.from_pretrained(base, args.adapter_path, is_trainable=False).eval().to("cuda")
    results = []
    for case in cases:
        requested = args.model or case["expected_role"]
        inputs = tokenizer.apply_chat_template(case["messages"], tokenize=True, add_generation_prompt=True, enable_thinking=False, return_tensors="pt").to("cuda")
        with torch.inference_mode():
            # 显式 mask 避免依赖 tokenizer 对 padding 的自动推断。
            output = model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs), do_sample=False, temperature=None, top_p=None, top_k=None, max_new_tokens=MAX_NEW_TOKENS, pad_token_id=tokenizer.pad_token_id)
        # generate 返回 prompt+新增 tokens；切掉 prompt（含模板预填的空 think 段）
        # 后才继续评分，否则 no_think_block 会把输入模板误认为模型输出。
        text = tokenizer.decode(output[0, inputs.shape[1] :], skip_special_tokens=True)
        results.append(assess(case, requested, requested, None, None, text, None, "peft"))
    return results


# vLLM 生命周期由外层管理。此处 model 字段真正选择服务端已注册的 adapter；
# 请求只含 messages，不发送 completion/expected_role 等标准答案和评分元数据。
def vllm_single(case, args):
    requested = args.model or case["expected_role"]
    payload = {"model": requested, "messages": case["messages"], "temperature": 0, "max_tokens": MAX_NEW_TOKENS, "chat_template_kwargs": {"enable_thinking": False}}
    http_request = urlrequest.Request(args.endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    status, error, body = None, None, None
    try:
        with urlrequest.urlopen(http_request, timeout=args.timeout) as response:
            status, body = response.status, response.read().decode("utf-8", errors="replace")
    except urlerror.HTTPError as exc:
        status, error, body = exc.code, str(exc), exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        error = str(exc)
    returned, text = None, None
    try:
        document = json.loads(body) if body is not None else None
        # timeout 后 body=None；API 的 null/array/缺字段也在同一解析边界记为错误。
        returned = document["model"]
        text = document["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise TypeError("choices[0].message.content must be a string")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        text, error = None, error or f"invalid API response: {exc}"
    return assess(case, requested, returned, status, error, text, body, "vllm")


def eval_group(row):
    # 固定 fixture 的编号为 split 内原始行号，不是 raw 当前排序或模板编号。
    # 000..011 = development，012..023 = held_out；train/其他 ID 不作为留出样本。
    # 从 case_id 推导使旧 raw 也能重算，不修改冻结的 dataset 或历史 raw。
    role, _, index = row["case_id"].rpartition("-eval-")
    if role in ROLES and index in {f"{i:03d}" for i in range(24)}:
        return "development" if int(index) < 12 else "held_out"
    return "unassigned"


def metrics(rows):
    keys = ("http_success", "model_selection_pass", "json_valid", "no_think_block", "required_fields_pass", "correct_role")
    result = {"cases": len(rows), "operational_failures": sum(bool(r.get("error")) for r in rows)}
    for key in keys:
        # 同时修正旧 raw 的 base 汇总语义，但不改写原始行：角色/字段不适用于 base。
        values = [r.get(key) for r in rows if r.get(key) is not None
                  and not (r["requested_model"] == "qwen3-8b" and key in ("required_fields_pass", "correct_role"))]
        result[key] = sum(bool(value) for value in values) / len(values) if values else None
    return result


def summarize(rows, grouped=True):
    # 从 raw 已记录的布尔判定重算统计，不重新运行模型或调用 assess。
    # e.g.: 3 条 merchant 请求中 2 条 role 正确、1 条无法解析，correct_role=2/3；
    # by_eval_group.held_out.by_requested_model["npc-merchant"] 保存该角色后 12 条指标；
    # 每组 matrix 同样保留 failure 列。整体 fields/role 分母只含 adapter，其他指标含 base。
    summary = metrics(rows)
    matrix = {}
    groups = {}
    for row in rows:
        requested = row["requested_model"]
        groups.setdefault(requested, []).append(row)
        observed = row.get("observed_role")
        column = observed if isinstance(observed, str) and observed in ROLES else "failure"
        matrix.setdefault(requested, {role: 0 for role in (*ROLES, "failure")})[column] += 1
    summary["by_requested_model"] = {model: metrics(group) for model, group in groups.items()}
    if grouped:
        split_rows = {}
        for row in rows:
            split_rows.setdefault(eval_group(row), []).append(row)
        summary["by_eval_group"] = {}
        for name, group in split_rows.items():
            split_summary, split_matrix = summarize(group, grouped=False)
            summary["by_eval_group"][name] = {**split_summary, "matrix": split_matrix}
    return summary, matrix


def m2p6_gate(rows, summary, matrix):
    # m2p.6 专用验收口径: docs/milestone-plan/m2p-plan.md#M2p.6。
    # 在公共池 eval：四 adapter 各 24 + base 24
    # 20/24 hard threshold
    # HTTP/选模失败暂列为执行缺口。本 gate 不代表全部 milestone exit criteria。
    models = (*ROLES, "qwen3-8b")
    coverage = set(summary["by_requested_model"]) == set(models)
    adapters = {}
    for model in models:
        group = [row for row in rows if row["requested_model"] == model]
        role = model if model in ROLES else group[0]["case_id"].rpartition("-eval-")[0] if group else None
        expected_ids = {f"{role}-eval-{index:03d}" for index in range(24)}
        complete = len(group) == 24 and role in ROLES and {row["case_id"] for row in group} == expected_ids
        if model in ROLES:
            complete = complete and all(row["expected_role"] == model for row in group)
            correct = sum(bool(row.get("correct_role")) for row in group)
            diagonal = matrix.get(model, {}).get(model, 0)
            adapters[model] = {"cases": len(group), "correct_role_count": correct, "diagonal_count": diagonal,
                               "passed": complete and correct >= 20 and diagonal >= 20}
        coverage = coverage and complete
    execution = bool(rows) and all((row["backend"] == "vllm") and (not row.get("error"))
            and row.get("http_success") and row.get("model_selection_pass") for row in rows)
    behavior = all(result["passed"] for result in adapters.values())
    return {"name": "m2p6", "coverage_pass": coverage, "execution_pass": execution,
        "behavior_pass": behavior, "by_adapter": adapters, "passed": coverage and execution and behavior}


def score(args):
    if args.backend == "summary":
        if not args.raw_input:
            raise ValueError("--raw-input is required for summary backend")
        rows = [row for path in args.raw_input for row in read_jsonl(path)]
    else:
        if not args.cases or not args.raw_output:
            raise ValueError("--cases and --raw-output are required for inference backends")
        cases = [row for path in args.cases for row in read_jsonl(path)]
        cases = cases[: args.limit] if args.limit is not None else cases
        for case in cases:
            if not isinstance(case.get("case_id"), str) or case.get("expected_role") not in ROLES or not isinstance(case.get("messages"), list):
                raise ValueError(f"invalid scoring case: {case.get('case_id')}")
        if args.backend == "peft":
            if not args.adapter_path:
                raise ValueError("--adapter-path is required for PEFT")
            rows = peft_rows(cases, args)
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                rows = list(pool.map(lambda case: vllm_single(case, args), cases))
        # Raw observations are committed before any derived aggregation.
        write_jsonl(args.raw_output, rows)
    summary, matrix = summarize(rows)
    if args.gate:
        summary["gate"] = m2p6_gate(rows, summary, matrix)
    if args.summary_output:
        write_jsonl(args.summary_output, [summary])
    if args.matrix_output:
        path = Path(args.matrix_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["eval_group", "requested_model", *ROLES, "failure"])
            writer.writeheader()
            matrices = {"all": matrix, **{name: group["matrix"] for name, group in summary["by_eval_group"].items()}}
            for name, values in matrices.items():
                for requested in sorted(values):
                    writer.writerow({"eval_group": name, "requested_model": requested, **values[requested]})
    print(json.dumps({"summary": summary, "matrix": matrix}, sort_keys=True))
    # 普通评分仅在 operational error 时 exit 1；JSON/role 分数低不会自动 exit 1。
    # 只有显式 --gate m2p6 时，exit 0 才同时代表本次完整行为评测通过。
    return 1 if summary["operational_failures"] or (args.gate and not summary["gate"]["passed"]) else 0


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--backend", required=True, choices=("peft", "vllm", "summary"))
    root.add_argument("--cases", nargs="+")
    root.add_argument("--raw-output")
    root.add_argument("--raw-input", nargs="+")
    root.add_argument("--gate", choices=("m2p6",), help="summary only: require four adapters plus qwen3-8b, 24 unique eval cases each")
    for option in ("summary-output", "matrix-output", "adapter-path", "model"):
        root.add_argument(f"--{option}")
    root.add_argument("--limit", type=int)
    root.add_argument("--concurrency", type=int, default=1)
    root.add_argument("--endpoint", default="http://127.0.0.1:8000/v1/chat/completions")
    root.add_argument("--timeout", type=float, default=120)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be positive")
    if args.concurrency < 1:
        raise ValueError("--concurrency must be positive")
    if args.gate and args.backend != "summary":
        raise ValueError("--gate requires --backend summary; save all raw responses before evaluating the gate")
    return score(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"lora_score.py: {exc}", file=sys.stderr)
        sys.exit(2)
