# Lab 3: Concurrent Request Baseline

## Outcome

Measure end-to-end request latency and request throughput at controlled client concurrency, retaining failures and raw aggregate CSV rows.

## Steps

1. Start the Lab 2 server. No extra client dependencies are required on Python 3.10+.
2. Smoke-test with `python lab3-concurrency/concurrent_client.py --requests 2 --warmup 1`.
3. Run at least three repetitions at each required level:

   ```bash
   for repetition in 1 2 3; do
     for concurrency in 1 2 4 8 16; do
       python lab3-concurrency/concurrent_client.py \
         --concurrency "${concurrency}" --requests 32 --warmup 2 \
         --max-tokens 64
     done
   done
   ```

4. Keep model, prompt, output limit, and server arguments fixed. Record server logs and GPU observations separately.
5. Inspect [results/baseline.csv](results/baseline.csv), preserve failed rows, and complete [results/observations.md](results/observations.md).

The client uses asynchronous task scheduling with a semaphore; blocking standard-library HTTP calls run in worker threads. Percentiles use linear interpolation. It appends UTC-stamped aggregate rows and returns nonzero if any measured request fails. Usage tokens are not part of this lab's CSV; Lab 4 adds them.

## Submission and review criteria

- Submit the unedited CSV, exact client/server commands, server log, and observations.
- **Pass:** levels 1/2/4/8/16 each have at least three measured rows; warm-ups are excluded; p50/p95/p99 are computed over successful measured requests; every failure is counted and diagnosed; reruns require no source edits.
- **Revise:** request count is lower than concurrency without justification, percentiles mix failures or warm-up, failed rows are deleted, or server/workload settings drift between levels.
- **Human review:** Explain why throughput and latency can rise together, what client concurrency represents, and why requests/second is not enough for LLM capacity planning.
