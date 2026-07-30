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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--revision", default=os.getenv("MODEL_REVISION"))
    parser.add_argument("--prompt", action="append", dest="prompts", help="repeat for multiple prompts")
    parser.add_argument("--max-tokens", type=int, default=64)
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
    prompts = args.prompts or DEFAULT_PROMPTS

    try:
        from vllm import LLM, SamplingParams
    except ImportError as exc:
        print("error: vLLM is not installed; complete Lab 0 first", file=sys.stderr)
        return 2

    print(f"model={args.model} revision={args.revision or 'default'} dtype={args.dtype}")
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
    started = time.perf_counter()
    try:
        outputs = llm.generate(prompts, sampling)
    except Exception as exc:
        print(f"error: generation failed: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    for index, output in enumerate(outputs, start=1):
        generated = output.outputs[0]
        print(f"\n--- result {index} ---")
        print(f"prompt: {output.prompt}")
        print(f"output: {generated.text}")
        print(f"output_tokens: {len(generated.token_ids)}")
    print(f"\ngeneration_seconds={elapsed:.3f} prompts={len(prompts)}")
    print(f"GPU memory after generation: {gpu_memory()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
