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
| `wait-ready.sh` | Poll the host endpoint, retain every attempt, and measure process-start-to-observed-health time. |
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
| `ready-time.txt` | Process-start-to-first-observed-HTTP-200 duration. |
| `ready-result.env` | Machine-readable readiness result and final status. |

Readiness time is not TTFT. It includes container/process startup, model load,
engine initialization, and the polling interval. TTFT begins only after the
ready service receives an inference request.

### Shutdown

| Evidence | Meaning |
|---|---|
| `server-stop-requested-*`, `server-stop-finished-*` | Shutdown timing boundary. |
| `server.log` | Complete Docker stdout/stderr captured after stop. |
| `container-post-stop-inspect.json` | State captured before container removal. |
| `container-exit-code.txt` | Exit code independently returned by `docker wait`. |
| `post-stop-health.txt` | HTTP status after shutdown; `000` plus nonzero curl exit means no endpoint. |
| `graceful-shutdown.env` | Classification inputs and final lifecycle result. |

Docker command stderr/stdout companions are retained rather than folded into
the server log.

## Graceful shutdown definition

For this M1.2a idle-server test, `graceful_shutdown=true` requires all of:

```text
container was running before stop
docker stop(SIGTERM) returned 0
container reached exited/running=false
container exit code was 0
docker wait independently returned exit code 0
OOMKilled was false
the post-stop endpoint was unreachable
```

An exit code of `137`, `OOMKilled=true`, a still-reachable endpoint, an
unexpected pre-stopped container, or a nonzero application exit fails the
classification. Shutdown log markers are recorded as supporting evidence but
are not a hard gate because their wording is vLLM/Uvicorn-version-sensitive.

`lifecycle_success=true` additionally requires complete log/inspect capture
and successful removal of the stopped container. On failure, the script keeps
the container so an operator can inspect it; it does not silently delete the
failure state.

If readiness fails, still invoke `stop-server.sh` with that run directory. It
will capture the failed server's logs and state. A container that exited before
the stop request is deliberately classified as non-graceful and is preserved.

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
