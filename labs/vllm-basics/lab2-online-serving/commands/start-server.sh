#!/usr/bin/env bash
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
DTYPE="${DTYPE:-auto}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-${MODEL}}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-}"

command -v vllm >/dev/null || { echo "error: vllm is not on PATH; complete Lab 0 first" >&2; exit 1; }
[[ "${PORT}" =~ ^[0-9]+$ ]] || { echo "error: PORT must be numeric" >&2; exit 2; }

cmd=(vllm serve "${MODEL}" --host "${HOST}" --port "${PORT}" --dtype "${DTYPE}" --served-model-name "${SERVED_MODEL_NAME}")
if [[ -n "${MODEL_REVISION:-}" ]]; then
  cmd+=(--revision "${MODEL_REVISION}")
fi
if [[ -n "${GPU_MEMORY_UTILIZATION}" ]]; then
  cmd+=(--gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}")
fi
if [[ -n "${MAX_MODEL_LEN}" ]]; then
  [[ "${MAX_MODEL_LEN}" =~ ^[0-9]+$ ]] || { echo "error: MAX_MODEL_LEN must be numeric" >&2; exit 2; }
  cmd+=(--max-model-len "${MAX_MODEL_LEN}")
fi
if [[ -n "${MAX_NUM_SEQS}" ]]; then
  [[ "${MAX_NUM_SEQS}" =~ ^[0-9]+$ ]] || { echo "error: MAX_NUM_SEQS must be numeric" >&2; exit 2; }
  cmd+=(--max-num-seqs "${MAX_NUM_SEQS}")
fi
if [[ -n "${VLLM_EXTRA_ARGS:-}" ]]; then
  echo "error: VLLM_EXTRA_ARGS is intentionally unsupported; edit the array or invoke vllm directly to avoid unsafe word splitting" >&2
  exit 2
fi

printf 'Starting:'
printf ' %q' "${cmd[@]}"
printf '\n'
exec "${cmd[@]}"
