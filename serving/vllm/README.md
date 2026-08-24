# vLLM Docker Serving Lifecycle

This directory provides the reusable M1.2a lifecycle boundary for one
single-node vLLM server running in Docker. The scripts run on the host; the
benchmark client remains a separate process.

The intended sequence is:

```text
start-server.sh
    -> wait-ready.sh
    -> run requests
    -> stop-server.sh
```

This implementation is deliberately smaller than a process supervisor or
Kubernetes controller. It exists to make server startup, readiness, logging,
shutdown, and restart independently observable before Lab 3 benchmarking.

## Responsibilities

| File | Responsibility |
|---|---|
| `start-server.sh` | Validate fixed inputs, create a detached container, and retain command/container/start metadata. |
| `wait-ready.sh` | Poll health while the recorded container is running, stop early on a terminal state, and retain the result. |
| `stop-server.sh` | Send `SIGTERM`, retain Docker/server state, classify graceful shutdown, and remove only a successful container. |

The container runs `vllm serve` through an exec-form entrypoint. `--init`
forwards signals and reaps children. The host and container addresses are
different by design:

```text
client -> 127.0.0.1:<host-port> -> container 0.0.0.0:8000
```

## Example

Use a fresh evidence directory for every start. Initial and restart attempts
must not share a directory because raw evidence is never overwritten.

```bash
repo_root="$(git rev-parse --show-toplevel)"
run_dir="${repo_root}/artifacts/private/m1/$(date -u +%Y%m%dT%H%M%SZ)-m1.2a"

./serving/vllm/start-server.sh \
  --output-dir "${run_dir}" \
  --host 127.0.0.1 \
  --port 8042 \
  --name vllm-m1

./serving/vllm/wait-ready.sh \
  --output-dir "${run_dir}" \
  --timeout 300

# Run the Lab 2 smoke requests or the selected client here.

./serving/vllm/stop-server.sh \
  --output-dir "${run_dir}" \
  --timeout 60
```

After a successful stop, the container is removed and the same name can be
used with a new output directory for the restart attempt.

## Evidence contract

### Start

| Evidence | Meaning |
|---|---|
| `server-start-ns.txt`, `server-start-time.txt` | Timestamp captured immediately before `docker run`. |
| `server-command.txt` | Shell-escaped expanded Docker/vLLM command. |
| `container-name.txt`, `container-id.txt` | Exact lifecycle target. |
| `base-url.txt`, `image.txt` | Host endpoint and immutable image identity. |
| `container-start-inspect.json` | Docker state immediately after creation. |
| `start-result.env` | Machine-readable start command status. |

### Readiness

| Evidence | Meaning |
|---|---|
| `readiness-attempts.tsv` | Timestamp, curl exit, and HTTP status for every probe. |
| `readiness-container.stderr.log` | Docker inspect errors observed while waiting for readiness. |
| `ready-time.txt` | Process-start-to-readiness-decision duration; on success, this ends at the first HTTP 200. |
| `ready-result.env` | Machine-readable readiness result, failure reason, and last inspected container state. |

Readiness time is not TTFT. It includes container/process startup, model load,
engine initialization, and the polling interval. TTFT begins only after the
ready service receives an inference request. The readiness deadline applies
only while the recorded container can still become ready; `exited`, `dead`,
or unavailable containers end the wait immediately.

### Shutdown

| Evidence | Meaning |
|---|---|
| `server-stop-requested-*`, `server-stop-finished-*` | Shutdown timing boundary. |
| `server.log` | Complete Docker stdout/stderr captured after stop. |
| `container-post-stop-inspect.json` | State captured before container removal. |
| `graceful-shutdown.env` | Stop, final-state, evidence-capture, and removal results. |

Docker command stderr/stdout companions are retained rather than folded into
the server log.

## Graceful shutdown definition

`graceful_shutdown=true` is an observation that all of these held:

```text
container was running before stop
docker stop(SIGTERM) returned 0
container reached exited/running=false
container exit code was 0
OOMKilled was false
```

The classification is evidence, not a cleanup gate. The script captures logs
and inspect output, records their return codes, and then removes the container;
`lifecycle_success=true` means that removal succeeded. If shutdown or evidence
capture looks wrong, discard the run and rerun it from a fresh directory.

If readiness fails, still invoke `stop-server.sh` with that run directory. It
will capture the failed server's logs and state before cleanup. A container
that exited before the stop request is classified as non-graceful but removed.

## Boundaries

- This proves orderly teardown when no request is intentionally in flight.
- It does not yet prove request draining, admission shutdown, or a maximum
  graceful-termination budget. Those behaviors belong in later controlled
  failure/Kubernetes experiments.
- Docker sends `SIGKILL` after the configured timeout. A timeout fallback is
  therefore a failed graceful-shutdown result, even if the endpoint eventually
  disappears.
- The host bind defaults to `127.0.0.1`; use `0.0.0.0` only when remote access
  is intentional and separately controlled.
- Docker/vLLM flags and shutdown log messages are version-sensitive. The image
  digest and expanded command are part of every run's evidence.

## M1.2a acceptance

Before moving to Lab 3, retain at least one initial run and one restart run in
separate directories where:

```text
ready=true
graceful_shutdown=true
lifecycle_success=true
```

Both runs must use the same image, model, served name, memory setting, and
runtime arguments. Unexpected failures remain in their original run directory.

## M1.2b/M1.3 benchmark runner

The canonical host-side runner combines measurement hardening and the
single-node concurrency sweep:

```text
freeze config and capture planned run metadata
  -> start server
  -> wait ready
  -> record observed server metadata
  -> capture initial exposition
  -> warm-up
  -> wait idle
  -> start runtime/system samplers
  -> for every concurrency and repetition:
       wait idle
       capture metrics-before.prom
       run streaming requests
       wait idle
       capture metrics-after.prom
  -> stop samplers
  -> capture final exposition
  -> optionally capture and score the configured output-evaluation cases
  -> stop server
  -> validate raw JSONL and derive summaries
```

The per-repetition exposition boundary is required. A single exposition before
and after the complete sweep cannot attribute counter or histogram deltas to a
specific concurrency/repetition. The long-running samplers complement these
snapshots: gauges such as running requests, waiting requests, KV-cache usage,
container memory, host memory, and GPU utilization require a time series.

Install the host-side dependencies in the selected Python environment:

```bash
python3 -m pip install -r serving/vllm/benchmark/requirements-benchmark.txt
```

Validate the config and expanded sweep without starting Docker:

```bash
serving/vllm/run-benchmark.sh \
  --milestone m1 \
  --node-label spark-a \
  --purpose exploratory \
  --dry-run
```

The default workload is the measurement run: 1,000 requests for each of 6
concurrency levels and 3 repetitions, or 18,000 measured requests in total.
At C1, one repetition can take several minutes because requests are serialized.
The runner prints each phase and the active client reports
`completed/planned`, request throughput, and ETA every 10 seconds while also
retaining that output in the case client log.

Use the smoke workload to validate the complete lifecycle before a full run:

```bash
serving/vllm/run-benchmark.sh \
  --milestone m1 \
  --config benchmarks/configs/benchmark-smoke.yaml \
  --node-label spark-a \
  --purpose exploratory \
  --run-id "$(date -u +%Y%m%dT%H%M%SZ)-m1-smoke"
```

The smoke workload uses one concurrency point, four requests, and one
repetition. It validates orchestration and evidence production; its output is
not a substitute for the measurement workload. The copy under
`benchmarks/configs/benchmark-smoke.yaml` keeps the same rapid
pipeline/API contract beside the M1.4–M1.6 reference templates.

Run into a new private directory:

```bash
serving/vllm/run-benchmark.sh \
  --milestone m1 \
  --config benchmarks/configs/m1/m1.4/selection/short-short.yaml \
  --node-label spark-a \
  --purpose canonical \
  --run-id "$(date -u +%Y%m%dT%H%M%SZ)-m1-baseline"
```

Scientific controls are config-only: model identity and provenance, optional
vLLM revision selectors, image digest, dtype, generation config, structured
runtime arguments, workload, sampling, and lifecycle policy. Extra runtime
flags are YAML array elements and are retained in the expanded server command:

`model.artifact_revision` is provenance used to group and compare summaries;
the runner does not inspect the local model checkout or block a run when it has
changed. `model.runtime_revision` and `model.tokenizer_revision` are optional
vLLM selectors and are passed only when configured. The summary keeps both the
configured provenance and observed server selectors for later comparison.

```yaml
runtime:
  extra_args:
    - --disable-prefix-caching
```

Managed flags such as `--max-num-seqs`, `--max-model-len`, and
`--gpu-memory-utilization` must use their structured config fields and cannot
be duplicated in `extra_args`. Use a new run ID when changing runtime fields.
Do not combine repetitions from different server configurations.

### Raw and derived contract

```text
<run-dir>/
├── run.yaml
├── raw/
│   ├── benchmark-config.yaml
│   ├── requests.jsonl
│   ├── case-events.jsonl
│   ├── runtime-samples.jsonl
│   ├── system-samples.jsonl
│   ├── exposition/
│   │   ├── run-initial.prom
│   │   └── run-after.prom
│   ├── cases/<case-id>/
│   │   ├── metrics-before.prom
│   │   ├── metrics-after.prom
│   │   ├── idle-before.jsonl
│   │   ├── idle-after.jsonl
│   │   └── client logs and exit codes
│   └── server/
└── derived/
    ├── summary.json
    ├── cases.jsonl
    └── concurrency-summary.jsonl
```

`requests.jsonl` records client-observed TTFT, E2E, derived TPOT, final server
usage, request IDs, the deterministic request-unique cache salt, and every
failure. First generated content is the TTFT boundary; HTTP chunk intervals
are not called token-level ITL. TPOT is
`(last_content - first_content) / (output_tokens - 1)` and is null when fewer
than two output tokens are observed.

Runtime counters and histograms are derived from each case's before/after raw
Prometheus exposition. `num_preemptions` is reported as an event delta, not as
a count of unique preempted requests. vLLM average-throughput gauges are
supporting telemetry; canonical token throughput is derived from request token
counts and the measured client wall time.

The schema-v2 summary keeps its top-level version so the existing single-run
viewer remains compatible, while adding a self-contained `context`, normalized
comparison dimensions, and config/model/runtime/workload/measurement
fingerprints. These identifiers are comparison metadata, not validity or trust
gates: mismatches appear as `context_warnings`, and raw-schema/completeness
problems appear under `data_quality`, without suppressing the summary or
changing the benchmark outcome.

For M1.4 selection runs, configured criteria and pressure indicators are
evaluated after the run into `selection_analysis`. They are annotations only:
the runner does not stop on a metric threshold or automatically assign
`C_eff` / `C_pressure`. Lifecycle failures can still produce a valid
zero-case summary instead of disappearing from the evidence.

`boundary_policy.stop_conditions` is a reporting vocabulary, not a plug-in
rule engine. The client distinguishes request timeout from other request
failures; idle/readiness checks stop an unsafe or ambiguous next case; final
Docker state records OOM and restart evidence. Per-case `/metrics` snapshot
failures only mark telemetry incomplete and do not stop the sweep.
`orchestration.stop_on_failure` controls whether a completed client-failure
case ends the remaining sweep; the supplied evidence templates set it to
`true`.

The runtime and system collectors intentionally run on the host. `/metrics` is
already exposed by the API server, and the host can resolve the container
cgroup and NVIDIA telemetry. No Dockerfile, collector mount, or file copy into
the serving image is required. This keeps the digest-pinned runtime independent
from the benchmark implementation.

On DGX Spark, `gpu_memory_used_mib` may be null because aggregate framebuffer
memory reporting is unsupported. `gpu_fb_memory_status` distinguishes that
expected `unsupported` result from a query `error`. The collector separately
sums NVML per-process memory only for host PIDs in the serving container's
cgroup as `container_nvml_process_gpu_memory_used_bytes`. This is a
driver-reported, container-attributed allocation signal, not dedicated VRAM.
Correlate it with KV-cache usage, container cgroup memory, host
`MemAvailable`, reclaim/swap counters, and failures; do not reinterpret the
aggregate framebuffer null as zero.
