# Lab 1 Observations

| Item | Evidence |
|---|---|
| Model and immutable revision | Qwen2.5-0.5B-Instruct `7ae557604adf67be50417f59c2c2f167def9a775` |
| Runtime/container identity | `nvcr.io/nvidia/vllm@sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2` |
| Exact command and vLLM/PyTorch version | `cd /workspace/lab && ./run.sh -c A -t 32 -r 1`, PyTorch `2.13.0a0+9186a08b2c.nv26.07` |
| Fixed prompt source | `offline_inference.py:CASE_PROMPTS` at `37b5420d83390018b34485d4331144da4e0dae14` commit |
| Sampling parameters | `temperature=0`, `seed=42`; deviations: N/A |
| Initialization time | 34.420s |
| First same-engine generation | 0.210s |
| Subsequent same-engine generation | 0.161s |
| CUDA-visible memory before/after load | free=23.44 GiB / free=3.10 GiB |
| Peak system/cgroup memory during generation | 3320725504, /sys/fs/cgroup/memory.current every 2 seconds |
| Supplemental `nvidia-smi` evidence | N/A fields retained |
| Process exit and teardown behavior | Occasional `UnicodeDecodeError` in PyTorch cleanup, but no crash or hang. Exit code 0 |

## Experiment matrix

| Case | Prompt count | Prompt tokens per request | Total prompt tokens | Max output tokens/request | Elapsed seconds | Notes |
|---|---:|---|---:|---:|---:|---|
| A | 1 | [8] | 8 | 32 | 0.287s | Container冷启动，model initialization time 34.420s, way longer than others |
| B | 4 | [8, 11, 11, 9] | 39 | 32 | 0.271s | N/A |
| C | 8 | [8, 11, 11, 9, 8, 7, 9, 6] | 69 | 64 | 0.364s | N/A |
| D | 4 | [59, 59, 63, 67] | 248 | 128 | 0.678s | 在pytorch cleanup 有UnicodeDecodeError |
`
## Controlled comparisons

| Comparison | Fixed variables | Changed variable | Evidence/result |
|---|---|---|---|
| A vs B | model, short-prompt source, max output, sampling | prompt count | Almost same on time/mem, prompt tokens ↑↑↑ |
| B vs B-max128 companion | model, four short prompts, sampling | output ceiling | Elapsed time ↑↑↑: 0.271s → 0.683s, CGROUP peak memory ~; host memory 有较大变化 79.34 GB -> 96.58 GB ** |
| generation 1 vs 2 | loaded engine, Case B prompts, sampling | first/subsequent call | Elapsed time ↓: 0.210s → 0.161s, prompt token = |

**: 后续发现host mem的最大采样值还是在96GB左右，只是cgroup peak和host peak的峰值点有偏置。

## Command

```bash
docker exec vllm-experiment bash -c "cd /workspace/lab && ./run.sh -c A -t 32 -r 1"
```

## Interpretation

- Evidence that prompts were submitted through one `generate` call: See case-specific logs 
- Effect of prompt count, limited to A/B evidence: Almost no impact on time/memory, just total prompt tokens.
- Effect of `max_tokens`, limited to B/B-max128 evidence: Elapsed time greatly increased, peak memory not significantly affected, total prompt tokens unchanged.
- First-run versus same-engine repeat behavior: Elapsed time decreased, probably because of prompt cache hit.
- Unified-memory interpretation and measurement limitation: 
    - nvidia-smi reporting N/A, so cgroup_memory_current is one of the reliable metrics for peak memory usage of the container.
- Errors/deviations, including exit code and teardown: 
  - `UnicodeDecodeError` in PyTorch cleanup, but no crash or hang.
  - Exit code 0, no core dump, no zombie process.
