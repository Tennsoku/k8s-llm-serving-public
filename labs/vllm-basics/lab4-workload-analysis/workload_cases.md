# Workload Cases

| Case | Runner name | Intended input | Output ceiling | Dominant concern |
|---|---|---:|---:|---|
| A | `short-short` | 32–64 tokens | 32 | request overhead/light baseline |
| B | `short-long` | 32–64 tokens | 512 | decode duration and bandwidth |
| C | `long-short` | >2,000 tokens | 32 | prefill / TTFT hypothesis |
| D | `long-long` | >2,000 tokens | 512 | prefill, decode, and KV-cache pressure |

The source prompts are deterministic, but token counts depend on the model tokenizer. The runner changes request cache identity through a vLLM `cache_salt`, not by editing the prompt. Treat the intended ranges as hypotheses until the response `usage.prompt_tokens` confirms them. If a short case exceeds its range, shorten only that case, document the change, and start a new comparison group and rerun the shape check and measured comparison. If a long case is below 2,000 tokens, increase its repeated context and document the new source revision.

For a fair shape comparison keep model/revision, vLLM arguments, concurrency, request count, warm-up, GPU, and background load fixed. Case B/D responses may terminate before 512 tokens; record actual completion tokens and consider a prompt that explicitly requires a fixed-length format if decode separation is too weak.
