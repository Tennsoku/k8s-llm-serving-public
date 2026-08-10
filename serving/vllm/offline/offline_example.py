from __future__ import annotations

import argparse
import json
from pathlib import Path

from vllm import LLM, SamplingParams


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/offline-small.json"),
    )
    args = parser.parse_args()

    config = load_config(args.config)

    llm = LLM(model=config["model"])

    sampling = SamplingParams(
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
    )

    prompts = [
        "Briefly explain what an inference runtime does.",
        "Briefly explain why KV Cache is useful.",
    ]

    outputs = llm.generate(prompts, sampling)

    for output in outputs:
        print(f"Prompt: {output.prompt}")
        print(f"Output: {output.outputs[0].text}")
        print("---")


if __name__ == "__main__":
    main()