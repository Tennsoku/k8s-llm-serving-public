#!/usr/bin/env bash
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
DTYPE="${DTYPE:-auto}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-${MODEL}}"

command -v vllm >/dev/null || { echo "error: vllm is not on PATH; complete Lab 0 first" >&2; exit 1; }
[[ "${PORT}" =~ ^[0-9]+$ ]] || { echo "error: PORT must be numeric" >&2; exit 2; }

cmd=(vllm serve "${MODEL}" --host "${HOST}" --port "${PORT}" --dtype "${DTYPE}" --served-model-name "${SERVED_MODEL_NAME}")
if [[ -n "${MODEL_REVISION:-}" ]]; then
  cmd+=(--revision "${MODEL_REVISION}")
fi
if [[ -n "${VLLM_EXTRA_ARGS:-}" ]]; then
  echo "error: VLLM_EXTRA_ARGS is intentionally unsupported; edit the array or invoke vllm directly to avoid unsafe word splitting" >&2
  exit 2
fi

printf 'Starting:'
printf ' %q' "${cmd[@]}"
printf '\n'
exec "${cmd[@]}"
