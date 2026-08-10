#!/usr/bin/env python3
"""Run repeatable offline vLLM inference without an HTTP server."""

from __future__ import annotations

import argparse
import os
import sys
import time


DEFAULT_MODEL = os.getenv("MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
DEFAULT_PROMPTS = [
    "Explain continuous batching in two sentences.",
    "What does a KV cache store during LLM inference?",
    "Contrast prefill and decode in one concise paragraph.",
    "Why can tail latency rise when concurrency increases?",
]

EXTRA_SHORT_PROMPTS = [
    "Define PagedAttention in one sentence.",
    "What is time to first token?",
    "Why does decode repeatedly read the KV cache?",
    "What does request throughput measure?",
]

MEDIUM_PROMPTS = [
    (
        "An inference service receives requests with different prompt lengths and "
        "output limits. Explain how continuous batching can admit new prefill work "
        "while existing sequences remain in decode. Discuss why this can improve GPU "
        "utilization, and identify one way long prefills can still increase time to "
        "first token for short requests sharing the engine."
    ),
    (
        "A platform engineer observes that request throughput rises as concurrency "
        "increases, but p95 latency eventually grows much faster than the median. "
        "Explain the roles of queueing, active batch size, decode duration, and KV "
        "cache pressure. State which additional measurements would help distinguish "
        "a compute bottleneck from a capacity boundary."
    ),
    (
        "Describe the execution path of an offline language-model request after the "
        "model has loaded. Cover tokenization, prefill, KV cache creation, iterative "
        "decode, sampling, and detokenization. For each stage, identify whether input "
        "length, output length, or concurrent sequence count is the main workload "
        "dimension that changes its cost."
    ),
    (
        "A Grace Blackwell system exposes CPU and GPU access to a unified memory pool. "
        "Explain why a reported CUDA memory value should not automatically be called "
        "independent discrete-GPU VRAM. Propose a minimal observation plan that "
        "correlates runtime KV-cache allocation, system memory, cgroup memory, request "
        "latency, and any OOM or preemption event."
    ),
]

CASE_PROMPTS = {
    "A": DEFAULT_PROMPTS[:1],
    "B": DEFAULT_PROMPTS,
    "C": DEFAULT_PROMPTS + EXTRA_SHORT_PROMPTS,
    "D": MEDIUM_PROMPTS,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--revision", default=os.getenv("MODEL_REVISION"))
    parser.add_argument("--case", choices=CASE_PROMPTS, help="use the fixed Lab 1 prompt set")
    parser.add_argument("--prompt", action="append", dest="prompts", help="repeat for multiple prompts")
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument(
        "--generation-repeats",
        type=int,
        default=1,
        help="repeat generate calls against the same loaded engine",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dtype", default="auto")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    return parser.parse_args()


def gpu_memory() -> str:
    try:
        import torch
        free, total = torch.cuda.mem_get_info()
        return f"free={free / 2**30:.2f} GiB total={total / 2**30:.2f} GiB"
    except Exception as exc:
        return f"unavailable ({exc})"


def main() -> int:
    args = parse_args()
    if args.max_tokens < 1:
        raise SystemExit("--max-tokens must be positive")
    if args.generation_repeats < 1:
        raise SystemExit("--generation-repeats must be positive")
    if args.case and args.prompts:
        raise SystemExit("--case and --prompt cannot be used together")
    prompts = args.prompts or CASE_PROMPTS.get(args.case, DEFAULT_PROMPTS)

    try:
        from vllm import LLM, SamplingParams
    except ImportError as exc:
        print("error: vLLM is not installed; complete Lab 0 first", file=sys.stderr)
        return 2

    print(
        f"model={args.model} revision={args.revision or 'default'} "
        f"dtype={args.dtype} case={args.case or 'custom/default'}"
    )
    print(f"GPU memory before load: {gpu_memory()}")
    started = time.perf_counter()
    try:
        llm = LLM(
            model=args.model,
            revision=args.revision,
            dtype=args.dtype,
            gpu_memory_utilization=args.gpu_memory_utilization,
        )
    except Exception as exc:
        print(f"error: model initialization failed: {exc}", file=sys.stderr)
        return 1
    print(f"model_initialization_seconds={time.perf_counter() - started:.3f}")
    print(f"GPU memory after load: {gpu_memory()}")

    sampling = SamplingParams(temperature=0.0, max_tokens=args.max_tokens, seed=args.seed)
    for generation_index in range(1, args.generation_repeats + 1):
        started = time.perf_counter()
        try:
            outputs = llm.generate(prompts, sampling)
        except Exception as exc:
            print(
                f"error: generation {generation_index} failed: {exc}",
                file=sys.stderr,
            )
            return 1
        elapsed = time.perf_counter() - started

        prompt_token_counts = []
        output_token_counts = []

        for index, output in enumerate(outputs, start=1):
            generated = output.outputs[0]

            prompt_tokens = len(output.prompt_token_ids or [])
            output_tokens = len(generated.token_ids)

            prompt_token_counts.append(prompt_tokens)
            output_token_counts.append(output_tokens)

            print(f"\n--- generation {generation_index} result {index} ---")
            print(f"prompt: {output.prompt}")
            print(f"output: {generated.text}")
            print(f"prompt_tokens: {prompt_tokens}, output_tokens: {output_tokens}")

        print(f"\ngeneration_index={generation_index}")
        print(f"prompt_tokens_total={sum(prompt_token_counts)}")
        print(f"prompt_tokens_per_prompt={prompt_token_counts}")
        print(f"output_tokens_total={sum(output_token_counts)}")
        print(f"generation_seconds={elapsed:.3f} prompts={len(prompts)}")
        print(f"GPU memory after generation: {gpu_memory()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
