# Lab 4: Workload Shape Analysis

## Outcome

Compare prefill-heavy, decode-heavy, mixed, and lightweight traffic while measuring request/token throughput, latency, GPU utilization, memory, and failures.

## Steps

1. Read [workload_cases.md](workload_cases.md) and start the same server configuration used in Lab 3.
2. Smoke-test a single case at low cost:

   ```bash
   python lab4-workload-analysis/run_workloads.py \
     --case short-short --concurrency 1 --requests 2
   ```

3. Run the four-case comparison (then repeat it 3–5 times):

   ```bash
   python lab4-workload-analysis/run_workloads.py \
     --case all --concurrency 8 --requests 16 --warmup 1
   ```

4. Confirm actual input/output tokens in [results/workload-results.csv](results/workload-results.csv). `max_tokens` is a ceiling, so output tokens can be lower when an end token is generated.
5. Correlate each run with server logs. Add OOM/recovery evidence and complete [results/observations.md](results/observations.md).

The runner samples the selected GPU with `nvidia-smi`; absent/unparseable GPU telemetry is left blank, never changed to zero. HTTP `usage` supplies token counts. Cases run sequentially, requests within each case run concurrently. Long prompts use repeated controlled text and should exceed 2,000 model tokens; verify rather than assume this.

## Submission and review criteria

- Submit unedited CSV, fixed server config, logs, telemetry method, and observations.
- **Pass:** all four cases have 3–5 measured rows; token counts validate intended shapes; failures/OOMs remain recorded; GPU telemetry is present or its absence explained; every case has an evidence-linked bottleneck hypothesis; the useful-throughput saturation point is identified or bounded.
- **Revise:** max-token limits are reported as actual output tokens, approximate words are claimed as tokenizer counts, blank GPU samples are treated as 0%, or different server settings invalidate comparison.
- **Human review:** Defend which case most stresses TTFT, total latency, KV cache, compute, and memory bandwidth, and name the next metric/experiment needed for a capacity decision.
