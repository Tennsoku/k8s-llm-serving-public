#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: run-benchmark.sh --milestone ID --node-label LABEL [options]

Runs one complete single-node benchmark lifecycle from a versioned config.

Options:
  -c, --config FILE                 Benchmark configuration
  -o, --output-root DIR             Private run root (default: artifacts/private/<milestone>)
      --run-id ID                   Unique run ID (default includes <milestone>)
      --milestone ID                Lowercase milestone identifier (required)
      --node-label LABEL            Sanitized logical node label (required)
      --purpose TYPE                exploratory or canonical (default: exploratory)
      --host HOST                   Host bind address (default: 127.0.0.1)
      --port PORT                   Host port (default: 8000)
      --container-name NAME         Docker container name (default: vllm-<milestone>)
      --gpu-index INDEX             nvidia-smi GPU index (default: 0)
      --dry-run                     Validate and print the resolved plan
      --help                        Show this help

Model identity, runtime image/arguments, workload, sampling, lifecycle policy,
selection criteria, and pressure indicators come only from the config.
Criteria and indicators are copied into the summary as post-run annotations;
they never stop the sweep or choose C_eff/C_pressure. Only request or service
lifecycle failures stop a configured sweep. The client and collectors run on
the host; benchmark code is not mounted into the container.
HELP
}

SERVING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_DIR="${SERVING_DIR}/benchmark"
REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
CONFIG="${REPO_ROOT}/benchmarks/configs/vllm-single-node/benchmark-workload.yaml"
SCHEMA_DIR="${REPO_ROOT}/benchmarks/configs/vllm-single-node"
OUTPUT_ROOT=""
RUN_ID=""
MILESTONE=""
NODE_LABEL=""
PURPOSE="exploratory"
HOST="127.0.0.1"
PORT="8000"
CONTAINER_NAME=""
GPU_INDEX="0"
DRY_RUN=false
PYTHON_BIN="python3"

OPTS="$(getopt \
  -o c:o: \
  --long config:,output-root:,run-id:,milestone:,node-label:,purpose:,host:,port:,container-name:,gpu-index:,dry-run,help \
  -n 'run-benchmark.sh' -- "$@")" || {
  usage >&2
  exit 2
}
eval set -- "${OPTS}"

while true; do
  case "$1" in
    -c|--config) CONFIG="$2"; shift 2 ;;
    -o|--output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --milestone) MILESTONE="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --node-label) NODE_LABEL="$2"; shift 2 ;;
    --purpose) PURPOSE="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --container-name) CONTAINER_NAME="$2"; shift 2 ;;
    --gpu-index) GPU_INDEX="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help) usage; exit 0 ;;
    --) shift; break ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "${MILESTONE}" ]] || { echo "error: --milestone is required" >&2; exit 2; }
[[ "${MILESTONE}" =~ ^[a-z][a-z0-9-]*$ ]] || {
  echo "error: --milestone must be a lowercase safe identifier" >&2
  exit 2
}
[[ $# -eq 0 ]] || { echo "error: unexpected positional arguments: $*" >&2; exit 2; }
[[ -n "${NODE_LABEL}" ]] || { echo "error: --node-label is required" >&2; exit 2; }
[[ "${NODE_LABEL}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
  echo "error: --node-label must be a sanitized logical label" >&2
  exit 2
}
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/artifacts/private/${MILESTONE}}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-${MILESTONE}-vllm-single-node}"
CONTAINER_NAME="${CONTAINER_NAME:-vllm-${MILESTONE}}"
[[ "${RUN_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
  echo "error: unsafe --run-id" >&2
  exit 2
}
[[ "${PURPOSE}" == exploratory || "${PURPOSE}" == canonical ]] || {
  echo "error: --purpose must be exploratory or canonical" >&2
  exit 2
}
[[ "${PORT}" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || {
  echo "error: --port must be an integer from 1 to 65535" >&2
  exit 2
}
[[ "${GPU_INDEX}" =~ ^[0-9]+$ ]] || {
  echo "error: --gpu-index must be a non-negative integer" >&2
  exit 2
}
[[ "${CONTAINER_NAME}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
  echo "error: invalid --container-name" >&2
  exit 2
}
[[ -r "${CONFIG}" ]] || { echo "error: unreadable config: ${CONFIG}" >&2; exit 1; }
CONFIG="$(cd "$(dirname "${CONFIG}")" && pwd -P)/$(basename "${CONFIG}")"
SOURCE_CONFIG="${CONFIG}"
FROZEN_CONFIG_TEMP=""
if [[ "${DRY_RUN}" == false ]]; then
  FROZEN_CONFIG_TEMP="$(mktemp "/tmp/${MILESTONE}-benchmark-config.XXXXXX")"
  trap '[[ -z "${FROZEN_CONFIG_TEMP}" ]] || rm -f -- "${FROZEN_CONFIG_TEMP}"' EXIT
  cp "${SOURCE_CONFIG}" "${FROZEN_CONFIG_TEMP}"
  CONFIG="${FROZEN_CONFIG_TEMP}"
fi
command -v "${PYTHON_BIN}" >/dev/null || { echo "error: python3 is required" >&2; exit 1; }

"${PYTHON_BIN}" -c 'import jsonschema, yaml' || {
  echo "error: install serving/vllm/requirements-benchmark.txt" >&2
  exit 1
}

config_get() {
  "${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" \
    --config "${CONFIG}" get "$1"
}

"${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" --config "${CONFIG}" validate
mapfile -t CONCURRENCIES < <(
  "${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" \
    --config "${CONFIG}" concurrency
)
mapfile -t VLLM_EXTRA_ARGS < <(
  "${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" \
    --config "${CONFIG}" extra-args
)

CONFIG_ID="$(config_get config-id)"
CONFIG_STATUS="$(config_get config-status)"
EXPERIMENT_STEP="$(config_get experiment-step)"
EXPERIMENT_KIND="$(config_get experiment-kind)"
COMPARISON_GROUP="$(config_get comparison-group)"
VARIANT="$(config_get variant)"
AXIS="$(config_get axis)"
IMAGE="$(config_get image)"
MODEL="$(config_get model-path)"
MODEL_ARTIFACT_REVISION="$(config_get model-artifact-revision)"
MODEL_RUNTIME_REVISION="$(config_get model-runtime-revision)"
TOKENIZER_REVISION="$(config_get tokenizer-revision)"
SERVED_MODEL_NAME="$(config_get served-model-name)"
DTYPE="$(config_get dtype)"
QUANTIZATION="$(config_get quantization)"
GENERATION_CONFIG="$(config_get generation-config)"
MAX_MODEL_LEN="$(config_get max-model-len)"
MAX_NUM_SEQS="$(config_get max-num-seqs)"
GPU_MEMORY_UTILIZATION="$(config_get gpu-memory-utilization)"
CONTAINER_MEMORY_LIMIT="$(config_get container-memory-limit)"
REQUEST_COUNT="$(config_get request-count)"
WARMUP_REQUESTS="$(config_get warmup-requests)"
WARMUP_CONCURRENCY="$(config_get warmup-concurrency)"
REPETITIONS="$(config_get repetitions)"
SAMPLE_INTERVAL="$(config_get sample-interval)"
READY_TIMEOUT="$(config_get ready-timeout)"
IDLE_TIMEOUT="$(config_get idle-timeout)"
STOP_TIMEOUT="$(config_get stop-timeout)"
STOP_ON_FAILURE="$(config_get stop-on-failure)"
OUTPUT_EVALUATION_CASES="$(config_get output-evaluation-cases)"
EVALUATION_CASES_SOURCE=""
if [[ -n "${OUTPUT_EVALUATION_CASES}" ]]; then
  case "${OUTPUT_EVALUATION_CASES}" in
    /*) EVALUATION_CASES_SOURCE="${OUTPUT_EVALUATION_CASES}" ;;
    *) EVALUATION_CASES_SOURCE="$(dirname "${SOURCE_CONFIG}")/${OUTPUT_EVALUATION_CASES}" ;;
  esac
  [[ -f "${EVALUATION_CASES_SOURCE}" && -r "${EVALUATION_CASES_SOURCE}" ]] || {
    echo "error: unreadable output evaluation cases: ${EVALUATION_CASES_SOURCE}" >&2
    exit 1
  }
  EVALUATION_CASES_SOURCE="$(cd "$(dirname "${EVALUATION_CASES_SOURCE}")" && pwd -P)/$(basename "${EVALUATION_CASES_SOURCE}")"
fi
CONFIG_FINGERPRINT="$(
  "${PYTHON_BIN}" "${SCRIPT_DIR}/benchmark_config.py" \
    --config "${CONFIG}" fingerprint
)"
TOTAL_CASES=$(( ${#CONCURRENCIES[@]} * REPETITIONS ))
TOTAL_REQUESTS=$(( TOTAL_CASES * REQUEST_COUNT ))
if [[ "${CONFIG_STATUS}" != ready ]]; then
  echo "warning: config ${CONFIG_ID} is marked ${CONFIG_STATUS}; status is descriptive and the run will continue" >&2
fi


if [[ "${DRY_RUN}" == true ]]; then
  printf 'milestone=%s\nrun_id=%s\nnode_label=%s\npurpose=%s\nconfig=%s\n' \
    "${MILESTONE}" "${RUN_ID}" "${NODE_LABEL}" "${PURPOSE}" "${SOURCE_CONFIG}"
  printf 'output_root=%s\ncontainer_name=%s\n' "${OUTPUT_ROOT}" "${CONTAINER_NAME}"
  printf 'config_id=%s\nconfig_status=%s\nconfig_fingerprint=%s\n' \
    "${CONFIG_ID}" "${CONFIG_STATUS}" "${CONFIG_FINGERPRINT}"
  printf 'experiment_step=%s\nexperiment_kind=%s\ncomparison_group=%s\nvariant=%s\naxis=%s\n' \
    "${EXPERIMENT_STEP}" "${EXPERIMENT_KIND}" "${COMPARISON_GROUP}" \
    "${VARIANT}" "${AXIS}"
  printf 'image=%s\nmodel=%s\nmodel_artifact_revision=%s\nmodel_runtime_revision=%s\ntokenizer_revision=%s\nserved_model_name=%s\n' \
    "${IMAGE}" "${MODEL}" "${MODEL_ARTIFACT_REVISION}" \
    "${MODEL_RUNTIME_REVISION}" "${TOKENIZER_REVISION}" "${SERVED_MODEL_NAME}"
  printf 'dtype=%s\nquantization=%s\ngeneration_config=%s\nmax_model_len=%s\nmax_num_seqs=%s\ngpu_memory_utilization=%s\ncontainer_memory_limit=%s\n' \
    "${DTYPE}" "${QUANTIZATION}" "${GENERATION_CONFIG}" \
    "${MAX_MODEL_LEN}" "${MAX_NUM_SEQS}" "${GPU_MEMORY_UTILIZATION}" \
    "${CONTAINER_MEMORY_LIMIT}"
  printf 'concurrency=%s\nrepetitions=%s\nrequests_per_repetition=%s\n' \
    "${CONCURRENCIES[*]}" "${REPETITIONS}" "${REQUEST_COUNT}"
  printf 'warmup_requests=%s\nsample_interval_seconds=%s\nready_timeout_seconds=%s\nidle_timeout_seconds=%s\nstop_timeout_seconds=%s\nstop_on_failure=%s\n' \
    "${WARMUP_REQUESTS}" "${SAMPLE_INTERVAL}" "${READY_TIMEOUT}" \
    "${IDLE_TIMEOUT}" "${STOP_TIMEOUT}" "${STOP_ON_FAILURE}"
  printf 'total_cases=%s\ntotal_measured_requests=%s\n' \
    "${TOTAL_CASES}" "${TOTAL_REQUESTS}"
  printf 'output_evaluation_cases=%s\n' "${EVALUATION_CASES_SOURCE:-none}"
  printf 'extra_args='
  if (( ${#VLLM_EXTRA_ARGS[@]} > 0 )); then
    printf '%q ' "${VLLM_EXTRA_ARGS[@]}"
  fi
  printf '\n'
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
mv "${FROZEN_CONFIG_TEMP}" "${RUN_DIR}/raw/benchmark-config.yaml"
FROZEN_CONFIG_TEMP=""
trap - EXIT
CONFIG="${RUN_DIR}/raw/benchmark-config.yaml"
EVALUATION_CASES_FROZEN=""
if [[ -n "${EVALUATION_CASES_SOURCE}" ]]; then
  EVALUATION_CASES_FROZEN="${RUN_DIR}/raw/output-evaluation-cases.jsonl"
  cp "${EVALUATION_CASES_SOURCE}" "${EVALUATION_CASES_FROZEN}"
fi

SERVER_DIR="${RUN_DIR}/raw/server"
BASE_URL=""
SERVER_STARTED=false
SERVER_READY=false
RUNTIME_SAMPLER_PID=""
SYSTEM_SAMPLER_PID=""
SAMPLERS_STOPPED=true
CURRENT_PHASE="initialize_metadata"
FAILURE_PHASE=""
RUN_WARNINGS=()
ABORTED=false
STOP_REASON=""
LAST_SUPPORTED_CASE=""
FIRST_UNSUPPORTED_CASE=""

"${PYTHON_BIN}" "${SCRIPT_DIR}/run_metadata.py" capture \
  --run-dir "${RUN_DIR}" \
  --run-id "${RUN_ID}" \
  --milestone "${MILESTONE}" \
  --node-label "${NODE_LABEL}" \
  --purpose "${PURPOSE}" \
  --config "${CONFIG}" \
  --repo-root "${REPO_ROOT}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --container-name "${CONTAINER_NAME}" \
  --gpu-index "${GPU_INDEX}"

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

finalize_metadata() {
  local outcome="$1" failure_phase="$2"
  local args=(
    finalize
    --run-yaml "${RUN_DIR}/run.yaml"
    --server-dir "${SERVER_DIR}"
    --outcome "${outcome}"
  )
  [[ -n "${failure_phase}" ]] && args+=(--failure-phase "${failure_phase}")
  [[ -n "${STOP_REASON}" ]] && args+=(--stop-reason "${STOP_REASON}")
  [[ -n "${LAST_SUPPORTED_CASE}" ]] && args+=(--last-supported-case "${LAST_SUPPORTED_CASE}")
  [[ -n "${FIRST_UNSUPPORTED_CASE}" ]] && args+=(--first-unsupported-case "${FIRST_UNSUPPORTED_CASE}")
  for warning in "${RUN_WARNINGS[@]}"; do
    args+=(--warning "${warning}")
  done
  "${PYTHON_BIN}" "${SCRIPT_DIR}/run_metadata.py" "${args[@]}"
}

cleanup() {
  local original_rc=$?
  local failed_phase="${FAILURE_PHASE:-${CURRENT_PHASE}}"
  local cleanup_outcome="failed"
  local sampler_cleanup_rc=0 capture_cleanup_rc=0 stop_cleanup_rc=0
  trap - EXIT INT TERM
  set +e
  stop_samplers
  sampler_cleanup_rc=$?
  if (( sampler_cleanup_rc != 0 )); then
    RUN_WARNINGS+=("stop_samplers")
  fi
  if [[ "${SERVER_READY}" == true && ! -e "${RUN_DIR}/raw/exposition/run-after.prom" ]]; then
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
      --base-url "${BASE_URL}" \
      --output "${RUN_DIR}/raw/exposition/run-after.prom"
    capture_cleanup_rc=$?
    if (( capture_cleanup_rc != 0 )); then
      RUN_WARNINGS+=("final_metrics")
    fi
  fi
  if [[ "${SERVER_STARTED}" == true ]]; then
    "${SERVING_DIR}/stop-server.sh" \
      --output-dir "${SERVER_DIR}" --timeout "${STOP_TIMEOUT}"
    stop_cleanup_rc=$?
    if (( stop_cleanup_rc != 0 )); then
      RUN_WARNINGS+=("stop_server")
    fi
    SERVER_STARTED=false
  fi
  STOP_REASON="${STOP_REASON:-unexpected_exit}"
  if [[ "${ABORTED}" == true ]]; then
    cleanup_outcome="aborted"
  fi
  finalize_metadata "${cleanup_outcome}" "${failed_phase}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/summarize_metrics.py" \
    --run-dir "${RUN_DIR}" --schema-dir "${SCHEMA_DIR}" --force
  exit "$(( original_rc == 0 ? 1 : original_rc ))"
}

abort_run() {
  local signal_name="$1"
  local exit_code="$2"
  ABORTED=true
  STOP_REASON="signal:${signal_name}"
  exit "${exit_code}"
}
trap cleanup EXIT
trap 'abort_run INT 130' INT
trap 'abort_run TERM 143' TERM

start_args=(
  --output-dir "${SERVER_DIR}"
  --run-id "${RUN_ID}"
  --host "${HOST}"
  --port "${PORT}"
  --model "${MODEL}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --name "${CONTAINER_NAME}"
  --image "${IMAGE}"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
  --dtype "${DTYPE}"
  --generation-config "${GENERATION_CONFIG}"
  --max-model-len "${MAX_MODEL_LEN}"
  --max-num-seqs "${MAX_NUM_SEQS}"
  --container-memory-limit "${CONTAINER_MEMORY_LIMIT}"
  --enable-request-id-headers
)
[[ -n "${MODEL_RUNTIME_REVISION}" ]] && start_args+=(--revision "${MODEL_RUNTIME_REVISION}")
[[ -n "${TOKENIZER_REVISION}" ]] && start_args+=(--tokenizer-revision "${TOKENIZER_REVISION}")
[[ -n "${QUANTIZATION}" ]] && start_args+=(--quantization "${QUANTIZATION}")
for argument in "${VLLM_EXTRA_ARGS[@]}"; do
  start_args+=("--vllm-arg=${argument}")
done

printf 'phase=benchmark_plan cases=%s requests_per_case=%s total_requests=%s\n' \
  "${TOTAL_CASES}" "${REQUEST_COUNT}" "${TOTAL_REQUESTS}" >&2
CURRENT_PHASE="start_server"
printf 'phase=%s\n' "${CURRENT_PHASE}" >&2
start_server_rc=0
"${SERVING_DIR}/start-server.sh" "${start_args[@]}" \
  >"${RUN_DIR}/raw/start-server.stdout.log" \
  2>"${RUN_DIR}/raw/start-server.stderr.log" || start_server_rc=$?
printf '%d\n' "${start_server_rc}" >"${RUN_DIR}/raw/start-server-exit-code.txt"
if [[ -s "${SERVER_DIR}/container-id.txt" ]]; then
  SERVER_STARTED=true
fi
if (( start_server_rc != 0 )); then
  exit "${start_server_rc}"
fi
[[ "${SERVER_STARTED}" == true ]] || {
  echo "error: start-server succeeded without a container ID" >&2
  exit 1
}
"${PYTHON_BIN}" "${SCRIPT_DIR}/run_metadata.py" observe \
  --run-yaml "${RUN_DIR}/run.yaml" --server-dir "${SERVER_DIR}" \
  --phase server_started

CURRENT_PHASE="wait_ready"
printf 'phase=%s\n' "${CURRENT_PHASE}" >&2
ready_rc=0
"${SERVING_DIR}/wait-ready.sh" \
  --output-dir "${SERVER_DIR}" --timeout "${READY_TIMEOUT}" \
  >"${RUN_DIR}/raw/wait-ready.stdout.log" \
  2>"${RUN_DIR}/raw/wait-ready.stderr.log" || ready_rc=$?
if (( ready_rc != 0 )); then
  FAILURE_PHASE="wait_ready"
  STOP_REASON="readiness_loss"
  exit "${ready_rc}"
fi
SERVER_READY=true
BASE_URL="$(sed -n '1p' "${SERVER_DIR}/base-url.txt")"
"${PYTHON_BIN}" "${SCRIPT_DIR}/run_metadata.py" observe \
  --run-yaml "${RUN_DIR}/run.yaml" --server-dir "${SERVER_DIR}" \
  --phase ready

CURRENT_PHASE="initial_metrics"
initial_metrics_rc=0
"${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
  --base-url "${BASE_URL}" \
  --output "${RUN_DIR}/raw/exposition/run-initial.prom" || initial_metrics_rc=$?
if (( initial_metrics_rc != 0 )); then
  echo "warning: initial runtime metrics capture failed; benchmark will continue" >&2
  RUN_WARNINGS+=("initial_metrics")
fi

CURRENT_PHASE="warmup"
warmup_rc=0
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
  2>"${RUN_DIR}/raw/warmup.stderr.log" || warmup_rc=$?
if (( warmup_rc != 0 )); then
  FAILURE_PHASE="warmup"
  if (( warmup_rc == 2 )); then
    STOP_REASON="request_timeout:warmup"
  else
    STOP_REASON="client_failure:warmup"
  fi
  exit "${warmup_rc}"
fi

warmup_idle_rc=0
"${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" wait-idle \
  --base-url "${BASE_URL}" --run-id "${RUN_ID}" \
  --model-name "${SERVED_MODEL_NAME}" \
  --timeout "${IDLE_TIMEOUT}" \
  --output "${RUN_DIR}/raw/warmup-idle.jsonl" || warmup_idle_rc=$?
if (( warmup_idle_rc != 0 )); then
  FAILURE_PHASE="warmup_idle"
  STOP_REASON="idle_failure:warmup"
  exit "${warmup_idle_rc}"
fi

CURRENT_PHASE="start_samplers"
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
if ! kill -0 "${RUNTIME_SAMPLER_PID}" 2>/dev/null; then
  echo "warning: runtime sampler exited during startup; client benchmark will continue" >&2
  RUN_WARNINGS+=("runtime_sampler_startup")
fi
if ! kill -0 "${SYSTEM_SAMPLER_PID}" 2>/dev/null; then
  echo "warning: system sampler exited during startup; client benchmark will continue" >&2
  RUN_WARNINGS+=("system_sampler_startup")
fi

benchmark_failed=false
abort_sweep=false
CURRENT_PHASE="measured_cases"
for concurrency in "${CONCURRENCIES[@]}"; do
  for repetition in $(seq 1 "${REPETITIONS}"); do
    case_id="$(printf 'c%03d-r%02d' "${concurrency}" "${repetition}")"
    case_dir="${RUN_DIR}/raw/cases/${case_id}"
    mkdir -p "${case_dir}"

    printf 'phase=wait_idle_before case_id=%s\n' "${case_id}" >&2
    idle_before_rc=0
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" wait-idle \
      --base-url "${BASE_URL}" --run-id "${RUN_ID}" \
      --model-name "${SERVED_MODEL_NAME}" \
      --timeout "${IDLE_TIMEOUT}" \
      --output "${case_dir}/idle-before.jsonl" || idle_before_rc=$?
    if (( idle_before_rc != 0 )); then
      printf '%d\n' "${idle_before_rc}" >"${case_dir}/idle-before-exit-code.txt"
      benchmark_failed=true
      abort_sweep=true
      FAILURE_PHASE="${FAILURE_PHASE:-wait_idle_before}"
      STOP_REASON="idle_failure:${case_id}"
      FIRST_UNSUPPORTED_CASE="${FIRST_UNSUPPORTED_CASE:-${case_id}}"
      break
    fi

    capture_before_rc=0
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
      --base-url "${BASE_URL}" \
      --output "${case_dir}/metrics-before.prom" || capture_before_rc=$?
    if (( capture_before_rc != 0 )); then
      echo "warning: runtime metrics-before capture failed for ${case_id}; client case will continue" >&2
      RUN_WARNINGS+=("metrics_before:${case_id}")
    fi

    printf 'phase=run_case case_id=%s concurrency=%s requests=%s\n' \
      "${case_id}" "${concurrency}" "${REQUEST_COUNT}" >&2
    client_rc=0
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
      2> >(tee "${case_dir}/client.stderr.log" >&2) || client_rc=$?
    printf '%d\n' "${client_rc}" >"${case_dir}/client-exit-code.txt"
    if (( client_rc != 0 )); then
      benchmark_failed=true
      FAILURE_PHASE="${FAILURE_PHASE:-run_case}"
      if [[ -z "${STOP_REASON}" ]]; then
        if (( client_rc == 2 )); then
          STOP_REASON="request_timeout:${case_id}"
        else
          STOP_REASON="client_failure:${case_id}"
        fi
      fi
      FIRST_UNSUPPORTED_CASE="${FIRST_UNSUPPORTED_CASE:-${case_id}}"
    fi

    printf 'phase=wait_idle_after case_id=%s client_rc=%s\n' "${case_id}" "${client_rc}" >&2
    idle_after_rc=0
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" wait-idle \
      --base-url "${BASE_URL}" --run-id "${RUN_ID}" \
      --model-name "${SERVED_MODEL_NAME}" \
      --timeout "${IDLE_TIMEOUT}" \
      --output "${case_dir}/idle-after.jsonl" || idle_after_rc=$?
    printf '%d\n' "${idle_after_rc}" >"${case_dir}/idle-after-exit-code.txt"

    capture_after_rc=0
    "${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
      --base-url "${BASE_URL}" \
      --output "${case_dir}/metrics-after.prom" || capture_after_rc=$?
    printf '%d\n' "${capture_after_rc}" >"${case_dir}/metrics-after-exit-code.txt"
    if (( capture_after_rc != 0 )); then
      echo "warning: runtime metrics-after capture failed for ${case_id}" >&2
      RUN_WARNINGS+=("metrics_after:${case_id}")
    fi
    if (( idle_after_rc != 0 )); then
      benchmark_failed=true
      abort_sweep=true
      FAILURE_PHASE="${FAILURE_PHASE:-wait_idle_after}"
      STOP_REASON="${STOP_REASON:-idle_failure:${case_id}}"
      FIRST_UNSUPPORTED_CASE="${FIRST_UNSUPPORTED_CASE:-${case_id}}"
      break
    fi
    if (( client_rc == 0 )); then
      LAST_SUPPORTED_CASE="${case_id}"
    elif [[ "${STOP_ON_FAILURE}" == true ]]; then
      abort_sweep=true
    fi
    printf 'phase=case_complete case_id=%s\n' "${case_id}" >&2
    if [[ "${abort_sweep}" == true ]]; then
      break
    fi
  done
  if [[ "${abort_sweep}" == true ]]; then
    break
  fi
done
STOP_REASON="${STOP_REASON:-sweep_completed}"

CURRENT_PHASE="stop_samplers"
sampler_rc=0
stop_samplers || sampler_rc=$?
if (( sampler_rc != 0 )); then
  echo "warning: one or more telemetry samplers exited non-zero" >&2
  RUN_WARNINGS+=("stop_samplers")
fi

CURRENT_PHASE="final_metrics"
final_metrics_rc=0
"${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_metrics.py" capture \
  --base-url "${BASE_URL}" \
  --output "${RUN_DIR}/raw/exposition/run-after.prom" || final_metrics_rc=$?
if (( final_metrics_rc != 0 )); then
  echo "warning: final runtime metrics capture failed" >&2
  RUN_WARNINGS+=("final_metrics")
fi

if [[ -n "${EVALUATION_CASES_FROZEN}" && "${benchmark_failed}" == false ]]; then
  CURRENT_PHASE="output_evaluation"
  printf 'phase=%s\n' "${CURRENT_PHASE}" >&2
  evaluation_rc=0
  "${PYTHON_BIN}" "${SCRIPT_DIR}/output_evaluator.py" capture \
    --config "${CONFIG}" \
    --cases "${EVALUATION_CASES_FROZEN}" \
    --base-url "${BASE_URL}" \
    --model "${SERVED_MODEL_NAME}" \
    --raw-output "${RUN_DIR}/raw/output-evaluation.jsonl" \
    --summary-output "${RUN_DIR}/derived/output-evaluation-summary.json" \
    >"${RUN_DIR}/raw/output-evaluation.stdout.log" \
    2>"${RUN_DIR}/raw/output-evaluation.stderr.log" || evaluation_rc=$?
  if (( evaluation_rc != 0 )); then
    benchmark_failed=true
    FAILURE_PHASE="${FAILURE_PHASE:-output_evaluation}"
    [[ "${STOP_REASON}" != sweep_completed ]] || STOP_REASON="output_evaluation_failed"
  fi
fi

CURRENT_PHASE="stop_server"
stop_rc=0
"${SERVING_DIR}/stop-server.sh" \
  --output-dir "${SERVER_DIR}" --timeout "${STOP_TIMEOUT}" \
  >"${RUN_DIR}/raw/stop-server.stdout.log" \
  2>"${RUN_DIR}/raw/stop-server.stderr.log" || stop_rc=$?
SERVER_STARTED=false
if (( stop_rc != 0 )); then
  benchmark_failed=true
  FAILURE_PHASE="${FAILURE_PHASE:-stop_server}"
  RUN_WARNINGS+=("stop_server")
fi

shutdown_evidence="${SERVER_DIR}/graceful-shutdown.env"
if [[ -r "${shutdown_evidence}" ]]; then
  oom_killed="$(sed -n 's/^oom_killed=//p' "${shutdown_evidence}" | head -n 1)"
  restart_count="$(sed -n 's/^restart_count=//p' "${shutdown_evidence}" | head -n 1)"
  if [[ "${oom_killed}" == true ]]; then
    benchmark_failed=true
    FAILURE_PHASE="${FAILURE_PHASE:-server_lifecycle}"
    [[ "${STOP_REASON}" != sweep_completed ]] || STOP_REASON="oom"
  elif [[ "${restart_count}" =~ ^[0-9]+$ ]] && (( restart_count > 0 )); then
    benchmark_failed=true
    FAILURE_PHASE="${FAILURE_PHASE:-server_lifecycle}"
    [[ "${STOP_REASON}" != sweep_completed ]] || STOP_REASON="restart"
  fi
fi

outcome=success
exit_code=0
if [[ "${benchmark_failed}" == true ]]; then
  outcome=failed
  exit_code=1
fi
finalize_metadata "${outcome}" "${FAILURE_PHASE}"

CURRENT_PHASE="summarize"
summary_rc=0
"${PYTHON_BIN}" "${SCRIPT_DIR}/summarize_metrics.py" \
  --run-dir "${RUN_DIR}" --schema-dir "${SCHEMA_DIR}" || summary_rc=$?
if (( summary_rc != 0 )); then
  echo "warning: benchmark completed but derived summary generation failed" >&2
  RUN_WARNINGS+=("summarize")
  finalize_metadata "${outcome}" "${FAILURE_PHASE}"
  exit_code=1
fi

trap - EXIT INT TERM
printf 'run_dir=%s\noutcome=%s\nstop_reason=%s\n' \
  "${RUN_DIR}" "${outcome}" "${STOP_REASON}"
exit "${exit_code}"
