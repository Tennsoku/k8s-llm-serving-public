#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: start-server.sh [options]

Options:
  -o, --output-dir DIR              Evidence directory (default: current directory)
  -h, --host HOST                   Host bind address (default: 127.0.0.1)
  -p, --port PORT                   Host port mapped to container port 8000 (default: 8000)
  -m, --model MODEL                 Model path/name
  -n, --name NAME                   Docker container name (default: vllm-m1)
  -i, --image IMAGE                 Docker image (default: nvcr.io/nvidia/vllm@sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2)
  -g, --gpu-memory-utilization N    vLLM GPU memory utilization (default: 0.15)
      --served-model-name NAME      Model name exposed by the API
      --dtype DTYPE                 vLLM dtype (default: auto)
      --help                        Show this help
HELP
}

OPTS="$(getopt \
  -o o:h:p:m:n:i:g: \
  --long output-dir:,host:,port:,model:,name:,image:,gpu-memory-utilization:,served-model-name:,dtype:,help \
  -n 'start-server.sh' -- "$@")" || {
  usage >&2
  exit 2
}
eval set -- "${OPTS}"

OUTPUT_DIR="."
HOST="127.0.0.1"
PORT="8000"
MODEL="/models/Qwen2.5-0.5B-Instruct"
IMAGE="nvcr.io/nvidia/vllm@sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2"
CONTAINER_NAME="vllm-m1"
GPU_MEMORY_UTILIZATION="0.15"
SERVED_MODEL_NAME="qwen2.5-0.5b-instruct"
DTYPE="auto"

while true; do
  case "$1" in
    -o|--output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    -h|--host) HOST="$2"; shift 2 ;;
    -p|--port) PORT="$2"; shift 2 ;;
    -m|--model) MODEL="$2"; shift 2 ;;
    -n|--name) CONTAINER_NAME="$2"; shift 2 ;;
    -i|--image) IMAGE="$2"; shift 2 ;;
    -g|--gpu-memory-utilization) GPU_MEMORY_UTILIZATION="$2"; shift 2 ;;
    --served-model-name) SERVED_MODEL_NAME="$2"; shift 2 ;;
    --dtype) DTYPE="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    --) shift; break ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ $# -eq 0 ]] || { echo "error: unexpected positional arguments: $*" >&2; exit 2; }
command -v docker >/dev/null || { echo "error: docker is required" >&2; exit 1; }
[[ "${PORT}" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || {
  echo "error: port must be an integer from 1 to 65535" >&2
  exit 2
}
if [[ ! "${GPU_MEMORY_UTILIZATION}" =~ ^[0-9]+([.][0-9]+)?$ ]] \
  || ! awk -v value="${GPU_MEMORY_UTILIZATION}" 'BEGIN { exit !(value > 0 && value <= 1) }'; then
  echo "error: gpu-memory-utilization must be greater than 0 and no greater than 1" >&2
  exit 2
fi
[[ "${CONTAINER_NAME}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || {
  echo "error: invalid Docker container name: ${CONTAINER_NAME}" >&2
  exit 2
}

mkdir -p "${OUTPUT_DIR}"
OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd -P)"

for evidence_file in \
  server-start-ns.txt server-start-time.txt container-name.txt container-id.txt \
  base-url.txt image.txt server-command.txt start-result.env \
  container-start-inspect.json server.log graceful-shutdown.env; do
  if [[ -e "${OUTPUT_DIR}/${evidence_file}" ]]; then
    echo "error: output directory already contains ${evidence_file}; use a fresh run directory" >&2
    exit 1
  fi
done

if docker container inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  echo "error: container ${CONTAINER_NAME} already exists; preserve its evidence and remove it explicitly" >&2
  exit 1
fi

BASE_URL="http://${HOST}:${PORT}"
MODEL_DIR="${HOME}/models"

docker_cmd=(
  docker run --detach
  --name "${CONTAINER_NAME}"
  --init
  --stop-signal SIGTERM
  --stop-timeout 60
  --gpus all
  --ipc=host
  --memory 64g
  --label owner=tensoku
  -p "${HOST}:${PORT}:8000"
  -v "${MODEL_DIR}:/models:ro"
  --entrypoint vllm
  "${IMAGE}"
  serve "${MODEL}"
  --host 0.0.0.0
  --port 8000
  --dtype "${DTYPE}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
)

date +%s%N >"${OUTPUT_DIR}/server-start-ns.txt"
date --iso-8601=seconds >"${OUTPUT_DIR}/server-start-time.txt"
printf '%s\n' "${CONTAINER_NAME}" >"${OUTPUT_DIR}/container-name.txt"
printf '%s\n' "${BASE_URL}" >"${OUTPUT_DIR}/base-url.txt"
printf '%s\n' "${IMAGE}" >"${OUTPUT_DIR}/image.txt"
{
  printf 'command='
  printf '%q ' "${docker_cmd[@]}"
  printf '\n'
} >"${OUTPUT_DIR}/server-command.txt"

set +e
container_id="$("${docker_cmd[@]}" 2>"${OUTPUT_DIR}/docker-run.stderr.log")"
docker_run_rc=$?
set -e

printf 'docker_run_rc=%d\n' "${docker_run_rc}" >"${OUTPUT_DIR}/start-result.env"
if (( docker_run_rc != 0 )); then
  echo "error: docker run failed; see ${OUTPUT_DIR}/docker-run.stderr.log" >&2
  exit 1
fi

container_id="${container_id//$'\n'/}"
[[ -n "${container_id}" ]] || {
  echo "error: docker run returned an empty container ID" >&2
  exit 1
}
printf '%s\n' "${container_id}" >"${OUTPUT_DIR}/container-id.txt"

set +e
docker inspect "${CONTAINER_NAME}" \
  >"${OUTPUT_DIR}/container-start-inspect.json" \
  2>"${OUTPUT_DIR}/container-start-inspect.stderr.log"
inspect_rc=$?
set -e
printf 'container_start_inspect_rc=%d\n' "${inspect_rc}" >>"${OUTPUT_DIR}/start-result.env"

if (( inspect_rc != 0 )); then
  echo "error: container started but its initial state could not be captured" >&2
  exit 1
fi

printf 'container_id=%s\noutput_dir=%s\nbase_url=%s\n' \
  "${container_id}" "${OUTPUT_DIR}" "${BASE_URL}"
