# Lab 2: OpenAI-Compatible Serving

## Outcome

Operate one persistent vLLM endpoint, verify its advertised model, exercise streaming and non-streaming chat completions, and preserve startup, success, failure, shutdown, and memory evidence.

Run every command below from `labs/vllm-basics/`. Use the same model, revision, container, dtype, and memory setting recorded in Lab 1.

## 1. Fix the server configuration

In the server shell:

```bash
export MODEL=/models/Qwen2.5-0.5B-Instruct
export SERVED_MODEL_NAME=qwen2.5-0.5b-instruct
export HOST=127.0.0.1
export PORT=8000
export DTYPE=auto
export GPU_MEMORY_UTILIZATION=0.15
export VLLM_LABS_REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB2_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-lab2"
export LAB2_RUN_DIR="${VLLM_LABS_REPO_ROOT}/artifacts/private/m1/${LAB2_RUN_ID}"
mkdir -p "${LAB2_RUN_DIR}"
```

If the model is loaded from the Hugging Face Hub, also set the immutable `MODEL_REVISION`. A local model directory still requires its source revision/checksum in [observations.md](observations.md).

`GPU_MEMORY_UTILIZATION=0.15` is the current DGX Spark exploratory setting, not a universal recommendation. Keep it fixed while comparing Lab 2 behavior. The launcher also accepts explicit `MAX_MODEL_LEN` and `MAX_NUM_SEQS`; leave them unset unless the run records and explains the change. Arbitrary `VLLM_EXTRA_ARGS` remain unsupported so the printed command is unambiguous.

Confirm that the intended port is not already serving another process:

```bash
if curl --silent --fail "http://${HOST}:${PORT}/health" >/dev/null; then
  echo "error: an endpoint is already healthy on ${HOST}:${PORT}" >&2
  exit 1
fi
```

## 2. Start the server and retain its exit code

Keep the server in the foreground. Capture the launch timestamp immediately before invoking it:

```bash
date +%s%N >"${LAB2_RUN_DIR}/server-start-ns.txt"
date --iso-8601=seconds >"${LAB2_RUN_DIR}/server-start-time.txt"
set -o pipefail
./lab2-online-serving/commands/start-server.sh \
  2>&1 | tee "${LAB2_RUN_DIR}/server.log"
server_rc=${PIPESTATUS[0]}
printf 'server_exit_code=%d\n' "${server_rc}" | \
  tee -a "${LAB2_RUN_DIR}/server.log"
```

The launcher prints the fully expanded `vllm serve` command before loading. Do not count image pull/model download time as server startup unless that is the explicit experiment.

## 3. Measure readiness

Immediately after starting the command, use a second shell with the same `HOST`, `PORT`, `SERVED_MODEL_NAME`, and `LAB2_RUN_DIR` values:

```bash
base_url="http://${HOST}:${PORT}"
ready_started_ns="$(sed -n '1p' "${LAB2_RUN_DIR}/server-start-ns.txt")"
ready=false

for attempt in $(seq 1 1200); do
  if curl --silent --fail "${base_url}/health" \
      >"${LAB2_RUN_DIR}/health.json"; then
    ready=true
    break
  fi
  sleep 0.25
done

ready_finished_ns="$(date +%s%N)"
awk -v start="${ready_started_ns}" -v finish="${ready_finished_ns}" \
  'BEGIN { printf "server_ready_seconds=%.3f\n", (finish-start)/1000000000 }' | \
  tee "${LAB2_RUN_DIR}/ready-time.txt"

[[ "${ready}" == true ]] || {
  echo "error: server did not become ready within 300 seconds" >&2
  exit 1
}
```

This is process-start-to-health readiness time. It is not request TTFT. Record the model-loading stages from `server.log` alongside it.

## 4. Verify model identity and request behavior

The API request's `model` field must equal the served name, not necessarily the filesystem path used by `MODEL`:

```bash
export BASE_URL="http://${HOST}:${PORT}"
export MODEL="${SERVED_MODEL_NAME}"

set -o pipefail
./lab2-online-serving/commands/curl-examples.sh \
  2>&1 | tee "${LAB2_RUN_DIR}/curl-examples.log"
printf 'client_exit_code=%d\n' "${PIPESTATUS[0]}" | \
  tee -a "${LAB2_RUN_DIR}/curl-examples.log"
```

From the retained output, record:

- the exact model `id` returned by `GET /v1/models`;
- HTTP success for the non-streaming response and its final usage block;
- incremental server-sent events for the streaming response and the terminal completion marker;
- the unknown-model status/body, which must be 4xx.

Run the separate malformed-body case and preserve both status and body:

```bash
malformed_status="$(
  curl --silent --show-error \
    --output "${LAB2_RUN_DIR}/malformed-response.json" \
    --write-out '%{http_code}' \
    -H 'Content-Type: application/json' \
    --data '{"model":' \
    "${BASE_URL}/v1/chat/completions"
)"
printf 'malformed_http_status=%s\n' "${malformed_status}" | \
  tee "${LAB2_RUN_DIR}/malformed-status.txt"
sed -n '1,40p' "${LAB2_RUN_DIR}/malformed-response.json"
[[ "${malformed_status}" -ge 400 ]]
```

An expected 4xx is a passed negative test, not a failed server. Unexpected 2xx, 5xx, transport failure, or timeout must be recorded separately.

## 5. Observe idle memory and shut down

While the healthy server is idle, retain timestamped system, cgroup, and NVIDIA observations:

```bash
date --iso-8601=seconds | tee "${LAB2_RUN_DIR}/idle-time.txt"
free -b | tee "${LAB2_RUN_DIR}/idle-system-memory.txt"
if [[ -r /sys/fs/cgroup/memory.current ]]; then
  sed -n '1p' /sys/fs/cgroup/memory.current | \
    tee "${LAB2_RUN_DIR}/idle-cgroup-memory-current.txt"
fi
nvidia-smi | tee "${LAB2_RUN_DIR}/idle-nvidia-smi.txt"
```

On DGX Spark, unsupported framebuffer-memory fields are evidence of the unified-memory telemetry boundary; do not convert `N/A` to zero or call it discrete VRAM.

Return to the server shell, press Ctrl-C once, wait for the launcher/pipeline to return, and retain `server_exit_code`. Then verify that the endpoint stopped and capture memory again with a timestamp:

```bash
if curl --silent --fail "${BASE_URL}/health" >/dev/null; then
  echo "error: endpoint is still healthy after shutdown" >&2
else
  echo "endpoint_stopped=true"
fi

date --iso-8601=seconds | tee "${LAB2_RUN_DIR}/post-stop-time.txt"
free -b | tee "${LAB2_RUN_DIR}/post-stop-system-memory.txt"
nvidia-smi | tee "${LAB2_RUN_DIR}/post-stop-nvidia-smi.txt"
```

Record shutdown signals and tracebacks as lifecycle evidence. A complete response before teardown does not erase a nonzero server exit or leaked process.

## 6. Restart test

Start the server again using the unchanged exported variables, repeat the readiness probe, verify `GET /v1/models`, and stop it once more. Record whether the same command, served name, readiness behavior, and clean shutdown are reproducible. Do not overwrite the first startup log; use `server-restart.log` and `ready-time-restart.txt`.

## Expected result and errors

- `/health` becomes successful only after the runtime is ready.
- `/v1/models` exposes `SERVED_MODEL_NAME`.
- The non-stream response is one JSON document.
- The stream is a sequence of SSE records ending in a completion marker.
- Unknown-model and malformed-JSON cases return documented 4xx responses.
- Ctrl-C stops the endpoint and the post-stop probe fails.
- Missing binary, occupied port, model-load/OOM, API 5xx, timeout, signal, nonzero exit, and teardown traceback remain in their raw logs.

CLI flags are version-sensitive. When adaptation is necessary, preserve `vllm serve --help`, change one explicit launcher variable/argument, and document it rather than silently editing the captured command.

## Submission and review criteria

Submit:

- both expanded server commands and startup logs;
- initial and restart readiness measurements;
- model-list, non-stream, stream, unknown-model, and malformed-body evidence;
- idle/post-stop memory evidence with timestamps and methods;
- shutdown signal/exit code and endpoint-stopped check;
- completed [observations.md](observations.md).

**Pass:** documented start/restart/stop work; readiness is distinguished from TTFT; model identity is verified from the API; both completion modes succeed; both expected 4xx cases are explained; idle and post-stop memory are measured; unexpected failures and nonzero exits remain visible.

**Revise:** startup time starts only after the server is already ready; the local model path is assumed to be the API model ID; only HTTP 200 bodies are retained; expected and unexpected failures are mixed; or unified-memory fields are reported as discrete VRAM.

**Human review:** Assign model execution, auth, rate limiting, routing, tenant isolation, readiness, and graceful termination to vLLM or an external platform component, with reasons.
