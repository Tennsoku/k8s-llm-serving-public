#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: run-benchmark.sh --node-label LABEL [options]

Runs the complete single-node benchmark lifecycle.

Options:
  -c, --config FILE                 Workload contract
  -o, --output-root DIR             Private run root
      --run-id ID                   Unique run ID
      --node-label LABEL            Sanitized logical node label (required)
      --purpose TYPE                exploratory or canonical (default: exploratory)
      --host HOST                   Host bind address (default: 127.0.0.1)
      --port PORT                   Host port (default: 8000)
      --model PATH                  Container model path
      --model-revision REVISION     Immutable model revision/snapshot
      --served-model-name NAME      API and metric model name
      --container-name NAME         Docker container name (default: vllm-m1)
      --image IMAGE                 Immutable vLLM image
      --gpu-utilization N    vLLM KV-cache allocation fraction
      --dtype DTYPE                 vLLM dtype (default: auto)
      --gpu-index INDEX             nvidia-smi GPU index (default: 0)
      --ready-timeout SECONDS       Readiness timeout (default: 300)
      --idle-timeout SECONDS        Per-boundary idle timeout (default: 60)
      --stop-timeout SECONDS        Graceful stop timeout (default: 60)
      --vllm-arg ARG                Repeatable additional vLLM argument
      --dry-run                     Validate and print the plan without mutation
      --help                        Show this help

The client and collectors run on the host. No benchmark code is copied into or
mounted into the serving container.
HELP
}

SERVING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_DIR="${SERVING_DIR}/benchmark"
REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
CONFIG="${REPO_ROOT}/benchmarks/configs/vllm-single-node/benchmark-workload.yaml"
SCHEMA_DIR="${REPO_ROOT}/benchmarks/configs/vllm-single-node"
OUTPUT_ROOT="${REPO_ROOT}/artifacts/private/m1"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-m1-vllm-single-node"
NODE_LABEL=""
PURPOSE="exploratory"
HOST="127.0.0.1"
PORT="8000"
MODEL="/models/Qwen2.5-0.5B-Instruct"
MODEL_REVISION=""
SERVED_MODEL_NAME="qwen2.5-0.5b-instruct"
CONTAINER_NAME="vllm-m1"
IMAGE="nvcr.io/nvidia/vllm@sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2"
GPU_MEMORY_UTILIZATION="0.15"
DTYPE="auto"
GPU_INDEX="0"
READY_TIMEOUT="300"
IDLE_TIMEOUT="60"
STOP_TIMEOUT="60"
DRY_RUN=false
VLLM_EXTRA_ARGS=()
PYTHON_BIN="python3"

OPTS="$(getopt \
  -o c:o: \
  --long config:,output-root:,run-id:,node-label:,purpose:,host:,port:,model:,model-revision:,served-model-name:,container-name:,image:,gpu-memory-utilization:,dtype:,gpu-index:,ready-timeout:,idle-timeout:,stop-timeout:,vllm-arg:,dry-run,help \
  -n 'run-benchmark.sh' -- "$@")" || {
  usage >&2
  exit 2
}
eval set -- "${OPTS}"

while true; do
  case "$1" in
    -c|--config) CONFIG="$2"; shift 2 ;;
    -o|--output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --node-label) NODE_LABEL="$2"; shift 2 ;;
    --purpose) PURPOSE="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --model-revision) MODEL_REVISION="$2"; shift 2 ;;
    --served-model-name) SERVED_MODEL_NAME="$2"; shift 2 ;;
    --container-name) CONTAINER_NAME="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --gpu-memory-utilization) GPU_MEMORY_UTILIZATION="$2"; shift 2 ;;
    --dtype) DTYPE="$2"; shift 2 ;;
    --gpu-index) GPU_INDEX="$2"; shift 2 ;;
    --ready-timeout) READY_TIMEOUT="$2"; shift 2 ;;
    --idle-timeout) IDLE_TIMEOUT="$2"; shift 2 ;;
    --stop-timeout) STOP_TIMEOUT="$2"; shift 2 ;;
    --vllm-arg) VLLM_EXTRA_ARGS+=("$2"); shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help) usage; exit 0 ;;
    --) shift; break ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ $# -eq 0 ]] || { echo "error: unexpected positional arguments: $*" >&2; exit 2; }
[[ -n "${NODE_LABEL}" ]] || { echo "error: --node-label is required" >&2; exit 2; }
[[ "${NODE_LABEL}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
  echo "error: --node-label must be a sanitized logical label" >&2
  exit 2
}
[[ "${RUN_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
  echo "error: unsafe --run-id" >&2
  exit 2
}
[[ "${PURPOSE}" == exploratory || "${PURPOSE}" == canonical ]] || {
  echo "error: --purpose must be exploratory or canonical" >&2
  exit 2
}
if [[ "${PURPOSE}" == canonical && -z "${MODEL_REVISION}" ]]; then
  echo "error: --model-revision is required for canonical runs" >&2
  exit 2
fi
MODEL_REVISION="${MODEL_REVISION:-unrecorded}"
for value in "${GPU_INDEX}" "${READY_TIMEOUT}" "${IDLE_TIMEOUT}" "${STOP_TIMEOUT}"; do
  [[ "${value}" =~ ^[0-9]+$ ]] || {
    echo "error: GPU index and timeouts must be non-negative integers" >&2
    exit 2
  }
done
(( READY_TIMEOUT > 0 && IDLE_TIMEOUT > 0 && STOP_TIMEOUT > 0 )) || {
  echo "error: timeouts must be positive" >&2
  exit 2
}
[[ -r "${CONFIG}" ]] || { echo "error: unreadable config: ${CONFIG}" >&2; exit 1; }
CONFIG="$(cd "$(dirname "${CONFIG}")" && pwd -P)/$(basename "${CONFIG}")"
command -v "${PYTHON_BIN}" >/dev/null || { echo "error: python3 is required" >&2; exit 1; }

"${PYTHON_BIN}" -c 'import jsonschema, yaml' || {
  echo "error: install serving/vllm/requirements-benchmark.txt" >&2
  exit 1
}

"${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" --config "${CONFIG}" validate
mapfile -t CONCURRENCIES < <(
  "${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" \
    --config "${CONFIG}" concurrency
)

REQUEST_COUNT="$("${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" --config "${CONFIG}" get request-count)"
WARMUP_REQUESTS="$("${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" --config "${CONFIG}" get warmup-requests)"
WARMUP_CONCURRENCY="$("${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" --config "${CONFIG}" get warmup-concurrency)"
REPETITIONS="$("${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" --config "${CONFIG}" get repetitions)"
SAMPLE_INTERVAL="$("${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" --config "${CONFIG}" get sample-interval)"
TOTAL_CASES=$(( ${#CONCURRENCIES[@]} * REPETITIONS ))
TOTAL_REQUESTS=$(( TOTAL_CASES * REQUEST_COUNT ))

if [[ "${DRY_RUN}" == true ]]; then
  printf 'run_id=%s\nnode_label=%s\npurpose=%s\nconfig=%s\n' \
    "${RUN_ID}" "${NODE_LABEL}" "${PURPOSE}" "${CONFIG}"
  printf 'model_revision=%s\n' "${MODEL_REVISION}"
  printf 'concurrency=%s\nrepetitions=%s\nrequests_per_repetition=%s\n' \
    "${CONCURRENCIES[*]}" "${REPETITIONS}" "${REQUEST_COUNT}"
  printf 'warmup_requests=%s\nsample_interval_seconds=%s\n' \
    "${WARMUP_REQUESTS}" "${SAMPLE_INTERVAL}"
  printf 'total_cases=%s\ntotal_measured_requests=%s\n' \
    "${TOTAL_CASES}" "${TOTAL_REQUESTS}"
  exit 0
fi

"${PYTHON_BIN}" -c 'import aiohttp' || {
  echo "error: install serving/vllm/requirements-benchmark.txt" >&2
  exit 1
}

RUN_DIR="${OUTPUT_ROOT}/${RUN_ID}"
[[ ! -e "${RUN_DIR}" ]] || {
  echo "error: run directory already exists: ${RUN_DIR}" >&2
  exit 1
}

mkdir -p "${RUN_DIR}/raw/server" "${RUN_DIR}/raw/exposition" \
  "${RUN_DIR}/raw/cases" "${RUN_DIR}/derived"
cp --no-clobber "${CONFIG}" "${RUN_DIR}/raw/workload.yaml"

SERVER_DIR="${RUN_DIR}/raw/server"
BASE_URL=""
SERVER_STARTED=false
SERVER_READY=false
RUNTIME_SAMPLER_PID=""
SYSTEM_SAMPLER_PID=""
SAMPLERS_STOPPED=true
NORMAL_FINISH=false

stop_samplers() {
  local runtime_rc=0 system_rc=0
  if [[ "${SAMPLERS_STOPPED}" == true ]]; then
    return 0
  fi
  if [[ -n "${RUNTIME_SAMPLER_PID}" ]] && kill -0 "${RUNTIME_SAMPLER_PID}" 2>/dev/null; then
    kill -TERM "${RUNTIME_SAMPLER_PID}" 2>/dev/null || true
  fi
  if [[ -n "${SYSTEM_SAMPLER_PID}" ]] && kill -0 "${SYSTEM_SAMPLER_PID}" 2>/dev/null; then
    kill -TERM "${SYSTEM_SAMPLER_PID}" 2>/dev/null || true
  fi
  if [[ -n "${RUNTIME_SAMPLER_PID}" ]]; then
    if wait "${RUNTIME_SAMPLER_PID}"; then runtime_rc=0; else runtime_rc=$?; fi
  fi
  if [[ -n "${SYSTEM_SAMPLER_PID}" ]]; then
    if wait "${SYSTEM_SAMPLER_PID}"; then system_rc=0; else system_rc=$?; fi
  fi
  printf 'runtime_sampler_rc=%d\nsystem_sampler_rc=%d\n' \
    "${runtime_rc}" "${system_rc}" >"${RUN_DIR}/raw/sampler-result.env"
  SAMPLERS_STOPPED=true
  (( runtime_rc == 0 && system_rc == 0 ))
}

cleanup() {
  local original_rc=$?
  trap - EXIT INT TERM
  set +e
  stop_samplers
  if [[ "${SERVER_READY}" == true && ! -e "${RUN_DIR}/raw/exposition/run-after.prom" ]]; then
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
      --base-url "${BASE_URL}" \
      --output "${RUN_DIR}/raw/exposition/run-after.prom"
  fi
  if [[ "${SERVER_STARTED}" == true ]]; then
    "${SERVING_DIR}/stop-server.sh" \
      --output-dir "${SERVER_DIR}" --timeout "${STOP_TIMEOUT}"
    SERVER_STARTED=false
  fi
  if [[ -e "${RUN_DIR}/run.yaml" ]]; then
    if [[ -e "${RUN_DIR}/raw/requests.jsonl" ]]; then
      "${PYTHON_BIN}" "${SCRIPT_DIR}/summarize_metrics.py" \
        --run-dir "${RUN_DIR}" --schema-dir "${SCHEMA_DIR}" --force
    fi
    "${PYTHON_BIN}" "${SCRIPT_DIR}/run_metadata.py" finalize \
      --run-yaml "${RUN_DIR}/run.yaml" --outcome failed
  fi
  if [[ "${NORMAL_FINISH}" == true ]]; then
    exit "${original_rc}"
  fi
  exit "$(( original_rc == 0 ? 1 : original_rc ))"
}
trap cleanup EXIT INT TERM

start_args=(
  --output-dir "${SERVER_DIR}"
  --host "${HOST}"
  --port "${PORT}"
  --model "${MODEL}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --name "${CONTAINER_NAME}"
  --image "${IMAGE}"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
  --dtype "${DTYPE}"
  --enable-request-id-headers
)

for argument in "${VLLM_EXTRA_ARGS[@]}"; do
  start_args+=("--vllm-arg=${argument}")
done

# Main execution flow
printf 'phase=benchmark_plan cases=%s requests_per_case=%s total_requests=%s\n' \
  "${TOTAL_CASES}" "${REQUEST_COUNT}" "${TOTAL_REQUESTS}" >&2
printf 'phase=start_server\n' >&2
"${SERVING_DIR}/start-server.sh" "${start_args[@]}" \
  >"${RUN_DIR}/raw/start-server.stdout.log" \
  2>"${RUN_DIR}/raw/start-server.stderr.log"
SERVER_STARTED=true

"${SERVING_DIR}/wait-ready.sh" \
  --output-dir "${SERVER_DIR}" --timeout "${READY_TIMEOUT}" \
  >"${RUN_DIR}/raw/wait-ready.stdout.log" \
  2>"${RUN_DIR}/raw/wait-ready.stderr.log"
SERVER_READY=true
BASE_URL="$(sed -n '1p' "${SERVER_DIR}/base-url.txt")"

"${PYTHON_BIN}" "${SCRIPT_DIR}/run_metadata.py" capture \
  --run-dir "${RUN_DIR}" \
  --run-id "${RUN_ID}" \
  --node-label "${NODE_LABEL}" \
  --purpose "${PURPOSE}" \
  --config "${CONFIG}" \
  --server-dir "${SERVER_DIR}" \
  --repo-root "${REPO_ROOT}" \
  --model-path "${MODEL}" \
  --model-revision "${MODEL_REVISION}" \
  --served-model-name "${SERVED_MODEL_NAME}" \
  --sample-interval "${SAMPLE_INTERVAL}"

"${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
  --base-url "${BASE_URL}" \
  --output "${RUN_DIR}/raw/exposition/run-initial.prom"

"${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_client.py" \
  --config "${CONFIG}" \
  --base-url "${BASE_URL}" \
  --model "${SERVED_MODEL_NAME}" \
  --run-id "${RUN_ID}" \
  --case-id warmup \
  --concurrency "${WARMUP_CONCURRENCY}" \
  --repetition 0 \
  --requests "${WARMUP_REQUESTS}" \
  --output "${RUN_DIR}/raw/warmup-requests.jsonl" \
  --case-events "${RUN_DIR}/raw/warmup-case-events.jsonl" \
  --warmup \
  >"${RUN_DIR}/raw/warmup.stdout.log" \
  2>"${RUN_DIR}/raw/warmup.stderr.log"

"${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" wait-idle \
  --base-url "${BASE_URL}" --run-id "${RUN_ID}" \
  --model-name "${SERVED_MODEL_NAME}" \
  --timeout "${IDLE_TIMEOUT}" \
  --output "${RUN_DIR}/raw/warmup-idle.jsonl"

SAMPLERS_STOPPED=false
"${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" sample \
  --base-url "${BASE_URL}" --run-id "${RUN_ID}" \
  --model-name "${SERVED_MODEL_NAME}" \
  --interval "${SAMPLE_INTERVAL}" \
  --output "${RUN_DIR}/raw/runtime-samples.jsonl" \
  >"${RUN_DIR}/raw/runtime-sampler.stdout.log" \
  2>"${RUN_DIR}/raw/runtime-sampler.stderr.log" &
RUNTIME_SAMPLER_PID=$!

"${PYTHON_BIN}" "${SCRIPT_DIR}/system_metrics.py" \
  --run-id "${RUN_ID}" --container "${CONTAINER_NAME}" \
  --gpu-index "${GPU_INDEX}" --interval "${SAMPLE_INTERVAL}" \
  --output "${RUN_DIR}/raw/system-samples.jsonl" \
  >"${RUN_DIR}/raw/system-sampler.stdout.log" \
  2>"${RUN_DIR}/raw/system-sampler.stderr.log" &
SYSTEM_SAMPLER_PID=$!

sleep 1
kill -0 "${RUNTIME_SAMPLER_PID}" 2>/dev/null || {
  echo "error: runtime sampler exited during startup" >&2
  exit 1
}
kill -0 "${SYSTEM_SAMPLER_PID}" 2>/dev/null || {
  echo "error: system sampler exited during startup" >&2
  exit 1
}

benchmark_failed=false
abort_sweep=false
for concurrency in "${CONCURRENCIES[@]}"; do
  for repetition in $(seq 1 "${REPETITIONS}"); do
    case_id="$(printf 'c%03d-r%02d' "${concurrency}" "${repetition}")"
    case_dir="${RUN_DIR}/raw/cases/${case_id}"
    mkdir -p "${case_dir}"

    printf 'phase=wait_idle_before case_id=%s\n' "${case_id}" >&2
    set +e
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" wait-idle \
      --base-url "${BASE_URL}" --run-id "${RUN_ID}" \
      --model-name "${SERVED_MODEL_NAME}" \
      --timeout "${IDLE_TIMEOUT}" \
      --output "${case_dir}/idle-before.jsonl"
    idle_before_rc=$?
    set -e
    if (( idle_before_rc != 0 )); then
      printf '%d\n' "${idle_before_rc}" >"${case_dir}/idle-before-exit-code.txt"
      benchmark_failed=true
      abort_sweep=true
      break
    fi

    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
      --base-url "${BASE_URL}" \
      --output "${case_dir}/metrics-before.prom"

    printf 'phase=run_case case_id=%s concurrency=%s requests=%s\n' \
      "${case_id}" "${concurrency}" "${REQUEST_COUNT}" >&2
    set +e
    "${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_client.py" \
      --config "${CONFIG}" \
      --base-url "${BASE_URL}" \
      --model "${SERVED_MODEL_NAME}" \
      --run-id "${RUN_ID}" \
      --case-id "${case_id}" \
      --concurrency "${concurrency}" \
      --repetition "${repetition}" \
      --requests "${REQUEST_COUNT}" \
      --output "${RUN_DIR}/raw/requests.jsonl" \
      --case-events "${RUN_DIR}/raw/case-events.jsonl" \
      --measured \
      >"${case_dir}/client.stdout.log" \
      2> >(tee "${case_dir}/client.stderr.log" >&2)
    client_rc=$?
    set -e
    printf '%d\n' "${client_rc}" >"${case_dir}/client-exit-code.txt"
    if (( client_rc != 0 )); then
      benchmark_failed=true
    fi

    printf 'phase=wait_idle_after case_id=%s client_rc=%s\n' "${case_id}" "${client_rc}" >&2
    set +e
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" wait-idle \
      --base-url "${BASE_URL}" --run-id "${RUN_ID}" \
      --model-name "${SERVED_MODEL_NAME}" \
      --timeout "${IDLE_TIMEOUT}" \
      --output "${case_dir}/idle-after.jsonl"
    idle_after_rc=$?
    set -e
    printf '%d\n' "${idle_after_rc}" >"${case_dir}/idle-after-exit-code.txt"

    set +e
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
      --base-url "${BASE_URL}" \
      --output "${case_dir}/metrics-after.prom"
    capture_after_rc=$?
    set -e
    printf '%d\n' "${capture_after_rc}" >"${case_dir}/metrics-after-exit-code.txt"
    if (( idle_after_rc != 0 || capture_after_rc != 0 )); then
      benchmark_failed=true
      abort_sweep=true
      break
    fi
    printf 'phase=case_complete case_id=%s\n' "${case_id}" >&2
  done
  if [[ "${abort_sweep}" == true ]]; then
    break
  fi
done

set +e
stop_samplers
sampler_rc=$?
set -e
if (( sampler_rc != 0 )); then
  benchmark_failed=true
fi

"${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
  --base-url "${BASE_URL}" \
  --output "${RUN_DIR}/raw/exposition/run-after.prom"

set +e
"${SERVING_DIR}/stop-server.sh" \
  --output-dir "${SERVER_DIR}" --timeout "${STOP_TIMEOUT}" \
  >"${RUN_DIR}/raw/stop-server.stdout.log" \
  2>"${RUN_DIR}/raw/stop-server.stderr.log"
stop_rc=$?
set -e
SERVER_STARTED=false
if (( stop_rc != 0 )); then
  benchmark_failed=true
fi

set +e
"${PYTHON_BIN}" "${SCRIPT_DIR}/summarize_metrics.py" \
  --run-dir "${RUN_DIR}" --schema-dir "${SCHEMA_DIR}"
summary_rc=$?
set -e
if (( summary_rc != 0 )); then
  benchmark_failed=true
fi

outcome=success
exit_code=0
if [[ "${benchmark_failed}" == true ]]; then
  outcome=failed
  exit_code=1
fi
"${PYTHON_BIN}" "${SCRIPT_DIR}/run_metadata.py" finalize \
  --run-yaml "${RUN_DIR}/run.yaml" --outcome "${outcome}"

NORMAL_FINISH=true
trap - EXIT INT TERM
printf 'run_dir=%s\noutcome=%s\n' "${RUN_DIR}" "${outcome}"
exit "${exit_code}"
