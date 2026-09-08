#!/usr/bin/env python3
"""Deterministic M2p fixtures and one-adapter LoRA training."""

# 阅读顺序：make_split -> render_ids -> generate -> train。
# generate：Python 模板构造样本，JSONL 每行保存输入、标准答案和元数据。
# train：用标准答案计算 loss，只更新 LoRA 参数；权重保存到 safetensors。
# 推理与评分见同目录 lora_score.py；此模块也提供两条路径共用的 I/O/tokenizer。
# 下面贯穿使用 make_split("npc-merchant", "train", 96, 42)[0] 作为例子。

import argparse
import json
import math
import random
import sys
from pathlib import Path
from time import monotonic

# 训练容器中的固定基座路径；四个 adapter 分别从同一基座开始训练。
BASE_MODEL = "/models/Qwen3-8B"
MAX_LENGTH = 512
MAX_NEW_TOKENS = 128
ROLES = {"npc-merchant": ("role", "dialogue", "price_gold"), "npc-guard": ("role", "dialogue", "access"), "quest-planner": ("role", "objective", "reward_gold"), "lore-archivist": ("role", "summary", "archive_tag")}
# A: vary instruction position, field order and layout, not the role or target schema.
# All templates describe the same three inputs; none supplies a persona or output keys.
TRAIN_TEMPLATES = (
    "Create a JSON game response.\nSite: {entity}; value: {value}; state: {state}.",
    "Site: {entity}; state: {state}; value: {value}.\nProduce the game response in JSON.",
    "Value {value} belongs to the event at {entity}; its state is {state}. Respond with JSON.",
    "The event is {state}, takes place at {entity}, and has value {value}. Give a JSON game response.",
    "The event site is {entity}. Its value is {value} and its state is {state}.\nReturn a JSON game response.",
    "For this game record, produce JSON: value={value} | state={state} | site={entity}.",
    "Game event:\nsite: {entity}\nvalue: {value}\nstate: {state}\nRespond with JSON.",
    "State: {state}\nValue: {value}\nSite: {entity}\nProduce the game response in JSON.",
    "Event details:\n- site: {entity}\n- state: {state}\n- value: {value}\nReturn a JSON game response.",
    "Create a JSON game response for the event (condition: {state}; site: {entity}; value: {value}).",
    "What JSON game response corresponds to an event whose value is {value}, whose site is {entity}, and whose state is {state}?",
    "Location: {entity}\nAn event with state {state} and value {value} was reported here.\nGive its game response as JSON.",
)
EVAL_TEMPLATES = ("For location {entity}, process game value {value} under condition {state}; answer in JSON.", "A game event occurred at {entity} with value {value} and state {state}. Return JSON only.")


def read_jsonl(path):
    try:
        with Path(path).open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSONL {path}: {exc}") from exc
    if not rows:
        raise ValueError(f"JSONL is empty: {path}")
    return rows


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def completion(role, entity, value, index):
    # 不调用 LLM 的情况下人工规则生成监督答案。
    # 守卫角色的通行结果目前只取决于序号奇偶，并非真实权限判断
    # 其余角色直接将 entity/value 填入固定输出格式。
    if role == "npc-merchant":
        return {"role": role, "dialogue": f"{entity} costs {value} gold.", "price_gold": value}
    if role == "npc-guard":
        access = "granted" if index % 2 == 0 else "denied"
        return {"role": role, "dialogue": f"Access to {entity} is {access}.", "access": access}
    if role == "quest-planner":
        return {"role": role, "objective": f"Survey {entity}.", "reward_gold": value}
    return {"role": role, "summary": f"Archive record for {entity}.", "archive_tag": f"A-{value}"}


def make_split(role, split, count, seed):
    # train/eval 使用独立的实体、数值和模板。不是把同一个总集随机切两半。
    # 保留旧 entity/value shuffle、行序与 index 对应的 state/答案，只改 train 句式。
    # 每个 state 的 24 个事件独立打散后分给 12 个模板：每模板每 state 2 条，
    # 即 12 类 × 8 条 = 96。不能用 index % 12，否则仍会绑定 index % 4 的 state。
    # 模板分配用独立 RNG，不改变事件 RNG；eval 不参与此分配，逐条保持原样。
    # seed 不含 role：四个角色的同序号输入一致，目标 completion 各自不同。
    # 示例记录（为便于阅读，把 completion 字符串单独展示为 JSON 文本）：
    #   case_id: npc-merchant-train-000; synthetic: true
    #   template_family: train-7; entity: train-site-005; value: 1011
    #   messages: [{"role": "user", "content":
    #     "State: calm\nValue: 1011\nSite: train-site-005\nProduce the game response in JSON."}]
    #   completion:
    #     {"dialogue":"train-site-005 costs 1011 gold.","price_gold":1011,"role":"npc-merchant"}
    #   expected_role: npc-merchant
    # 同一输入的 guard 答案为：
    #   {"access":"granted","dialogue":"Access to train-site-005 is granted.","role":"npc-guard"}
    # 同一事件换一种句式也应对应原答案，例如模板 0：
    #   "Create a JSON game response.\nSite: train-site-005; value: 1011; state: calm."
    # 这是语义等价示例；生成时每个事件只分配一个模板，不复制事件扩充样本数。
    # messages 是输入，completion 是训练答案；其他字段用于记录/校验/评分。
    # messages.role="user" 是聊天协议对象的角色，completion.role 才是要学的游戏角色。
    rng = random.Random(f"{seed}:{split}")
    templates = TRAIN_TEMPLATES if split == "train" else EVAL_TEMPLATES
    states = ["calm", "crowded", "rainy", "night"] if split == "train" else ["foggy", "dawn"]
    base = 1000 if split == "train" else 5000
    entities, values = [f"{split}-site-{i:03d}" for i in range(count)], list(range(base, base + count))
    rng.shuffle(entities)
    rng.shuffle(values)
    template_indices = [index % len(templates) for index in range(count)]
    if split == "train":
        template_rng = random.Random(f"{seed}:{split}:templates")
        for state_index in range(len(states)):
            indices = list(range(state_index, count, len(states)))
            template_rng.shuffle(indices)
            for slot, index in enumerate(indices):
                template_indices[index] = slot % len(templates)
    rows = []
    for index, (entity, value) in enumerate(zip(entities, values)):
        family = f"{split}-{template_indices[index]}"
        prompt = templates[template_indices[index]].format(
            entity=entity, value=value, state=states[index % len(states)]
        )
        target = json.dumps(completion(role, entity, value, index), sort_keys=True, separators=(",", ":"))
        rows.append({"case_id": f"{role}-{split}-{index:03d}", "synthetic": True,
                     "template_family": family, "entity": entity, "value": value,
                     "messages": [{"role": "user", "content": prompt}],
                     "completion": target, "expected_role": role})
    return rows


def render_ids(tokenizer, row):
    # 将上述样本转成两串 token IDs。这里展示解码后的文本，使用 Python 相邻
    # 字符串表示法；\n 表示换行，字符串之间不额外插入字符。
    # Example prompt:
    #   '<|im_start|>user\n'
    #   'State: calm\nValue: 1011\nSite: train-site-005\nProduce the game response in JSON.<|im_end|>\n'
    #   '<|im_start|>assistant\n<think>\n\n</think>\n\n'
    # Example full:
    #   '<|im_start|>user\n'
    #   'State: calm\nValue: 1011\nSite: train-site-005\nProduce the game response in JSON.<|im_end|>\n'
    #   '<|im_start|>assistant\n<think>\n\n</think>\n\n'
    #   '{"dialogue":"train-site-005 costs 1011 gold.","price_gold":1011,"role":"npc-merchant"}'
    #   '<|im_end|>\n'
    # add_generation_prompt 只添加 assistant 开头，不调用模型生成。
    # 空 think 段由 non-thinking 模板预填；它属于 prompt，不是待学习的答案。
    messages = row["messages"]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, enable_thinking=False
    )
    full = tokenizer.apply_chat_template(
        messages + [{"role": "assistant", "content": row["completion"]}],
        tokenize=True,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    # 按 token 前缀核对边界，防止模板变化使 label mask 错位；超长直接报错，
    # 不截断目标答案。generate 用 full 计数，train 同时用 prompt/full 划分 labels。
    if full[: len(prompt)] != prompt:
        raise ValueError(f"chat-template boundary mismatch for {row['case_id']}")
    if len(full) > MAX_LENGTH:
        raise ValueError(f"rendered case exceeds {MAX_LENGTH} tokens: {row['case_id']}")
    return prompt, full


def load_tokenizer():
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def generate(args):
    # 四个角色各 96 train + 24 eval，输出 8 个 JSONL；只加载 tokenizer，
    # 不加载模型权重。所有 split/长度检查完成后才写文件，token 汇总打印到 stdout。
    tokenizer = load_tokenizer()
    records = {}
    summary = {"seed": args.seed, "synthetic": True, "datasets": {}}
    for role in ROLES:
        train_rows = make_split(role, "train", 96, args.seed)
        eval_rows = make_split(role, "eval", 24, args.seed)
        checks = (({r["messages"][0]["content"].casefold() for r in train_rows}, {r["messages"][0]["content"].casefold() for r in eval_rows}, "input"),
                  ({r["entity"] for r in train_rows}, {r["entity"] for r in eval_rows}, "entity"),
                  ({r["value"] for r in train_rows}, {r["value"] for r in eval_rows}, "value"),
                  ({r["template_family"] for r in train_rows}, {r["template_family"] for r in eval_rows}, "template"))
        for train_values, eval_values, label in checks:
            if train_values & eval_values:
                raise ValueError(f"train/eval {label} overlap for {role}")
        for split, rows in (("train", train_rows), ("eval", eval_rows)):
            token_count = sum(len(render_ids(tokenizer, row)[1]) for row in rows)
            name = f"{role}.{split}.jsonl"
            records[name] = rows
            summary["datasets"][name] = {"cases": len(rows), "logical_tokens": token_count}
    for name, rows in records.items():
        write_jsonl(Path(args.output_dir) / name, rows)
    print(json.dumps(summary, sort_keys=True))


def train(args):
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, Trainer, TrainingArguments, set_seed
    class CountingTrainer(Trainer):
        logical_tokens = 0

        # 统计每次实际训练 micro-batch 的 prompt+答案 tokens，排除 padding；
        # 同一样本重复训练会重复计数，不能当作独立数据量或仅 loss tokens。
        def training_step(self, model, inputs, num_items_in_batch=None):
            self.logical_tokens += int(inputs["attention_mask"].sum().item())
            return super().training_step(model, inputs, num_items_in_batch)

    rows = read_jsonl(args.dataset)
    tokenizer = load_tokenizer()
    features = []
    for row in rows:
        if row.get("expected_role") != args.adapter:
            raise ValueError(f"adapter mismatch in case {row.get('case_id')}")
        prompt, full = render_ids(tokenizer, row)
        # completion-only labels，以下 P/Y/E/PAD 是示意符号，不是真实 token IDs：
        #   input_ids:       [P0 P1 ... | Y0 Y1 ... E | PAD]
        #   attention_mask:  [ 1  1 ... |  1  1 ... 1 |   0]
        #   labels:          [-100 ... | Y0 Y1 ... E | -100]
        # P=prompt，Y=答案，E=模板结束部分；padding 由下面的 collate 补齐。
        # -100 只屏蔽这些位置的 loss，prompt 仍参与上下文计算。
        # Causal-LM loss 内部对齐“预测下一个 token”，此处不要手动 shift labels。
        features.append({"input_ids": full, "attention_mask": [1] * len(full), "labels": [-100] * len(prompt) + full[len(prompt) :]})

    def collate(batch):
        width = max(len(item["input_ids"]) for item in batch)
        padded = {}
        for key, pad in (("input_ids", tokenizer.pad_token_id), ("attention_mask", 0), ("labels", -100)):
            padded[key] = torch.tensor([item[key] + [pad] * (width - len(item[key])) for item in batch])
        return padded

    output = Path(args.output_dir)
    if output.exists():
        raise FileExistsError(f"training output already exists: {output}")
    # PEFT 在 q/k/v/o 投影加入低秩增量：h = W0*x + (alpha/r)*B*A*x。
    # W0 冻结；A/B 可训练，r=8、alpha/r=2；每个 adapter 有自己的一组 A/B。
    # gradient checkpointing 重算中间激活以省内存，不是保存磁盘 checkpoint。
    # enable_input_require_grads 支持梯度传播，不表示解冻基座 embedding 权重。
    # seed 必须早于 LoRA A 的随机初始化；Trainer 内部设 seed 时模型已创建。
    seed = 42
    set_seed(seed)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, local_files_only=True, dtype=torch.bfloat16)
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(
        model,
        LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM", target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]),
    )
    # 单节点 batch=1、accumulation=8：每 8 个 micro-batch 更新一次参数。
    # max_steps 是 optimizer 更新次数，不是样本数；每次调用只训练一个 adapter。
    trainer = CountingTrainer(
        model=model,
        train_dataset=features,
        data_collator=collate,
        args=TrainingArguments(
            output_dir=str(output), per_device_train_batch_size=1, gradient_accumulation_steps=8,
            learning_rate=args.learning_rate, weight_decay=0.0, max_steps=args.max_steps, bf16=True,
            gradient_checkpointing=True, save_strategy="no", logging_steps=1, report_to=[], seed=seed,
        ),
    )
    # wall time 只包围 trainer.train()，不含基座加载和最终保存。
    started = monotonic()
    result = trainer.train()
    wall_seconds = monotonic() - started
    # 输出 adapter_model.safetensors（A/B 权重）和 adapter_config.json（装配配置）；
    # 不是完整基座权重。下方 metrics 只打印 JSON，不产生训练 JSONL。
    model.save_pretrained(output, safe_serialization=True)
    metrics = {"adapter": args.adapter, "max_steps": args.max_steps, "learning_rate": args.learning_rate, "seed": seed, "logical_tokens": trainer.logical_tokens, "wall_seconds": wall_seconds, "logical_tokens_per_second": trainer.logical_tokens / wall_seconds, "trainer_metrics": result.metrics, "log_history": trainer.state.log_history}
    print(json.dumps(metrics, sort_keys=True))


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    generate_parser = commands.add_parser("generate")
    generate_parser.add_argument("--output-dir", required=True)
    generate_parser.add_argument("--seed", type=int, default=42)
    train_parser = commands.add_parser("train")
    train_parser.add_argument("--adapter", required=True, choices=ROLES)
    train_parser.add_argument("--dataset", required=True)
    train_parser.add_argument("--output-dir", required=True)
    train_parser.add_argument("--max-steps", required=True, type=int, choices=(1, 40, 80))
    train_parser.add_argument("--learning-rate", type=float, default=1e-4)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "generate":
        generate(args)
    else:
        if not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
            raise ValueError("--learning-rate must be finite and positive")
        train(args)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"lora_train.py: {exc}", file=sys.stderr)
        sys.exit(2)
