#!/usr/bin/env bash

CASE_NAME="A"
MAX_TOKENS=32
GENERATION_REPEATS=1

while getopts "c:t:r:" opt; do
  case "$opt" in
    c) CASE_NAME="$OPTARG" ;;
    t) MAX_TOKENS="$OPTARG" ;;
    r) GENERATION_REPEATS="$OPTARG" ;;
    *)
      echo "Usage: $0 [-c case_name] [-t max_tokens] [-r generation_repeats]" >&2
      exit 1
      ;;
  esac
done

date --iso-8601=seconds | tee "/workspace/results/pre-load-time-case${CASE_NAME}-max${MAX_TOKENS}-repeat${GENERATION_REPEATS}.txt"
nvidia-smi | tee "/workspace/results/pre-load-nvidia-smi-case${CASE_NAME}-max${MAX_TOKENS}-repeat${GENERATION_REPEATS}.txt"
free -b | tee "/workspace/results/pre-load-system-memory-case${CASE_NAME}-max${MAX_TOKENS}-repeat${GENERATION_REPEATS}.txt"

run_lab1_case() {
  local case_name="$1"
  local max_tokens="$2"
  local generation_repeats="$3"
  local log="/workspace/results/case${case_name}-max${max_tokens}-repeat${generation_repeats}.log"

  set -o pipefail
  python /workspace/lab/offline_inference.py \
    --case "${case_name}" \
    --max-tokens "${max_tokens}" \
    --gpu-memory-utilization 0.15 \
    --generation-repeats "${generation_repeats}" \
    --revision "7ae557604adf67be50417f59c2c2f167def9a775" \
    2>&1 | tee "${log}"
  local rc=${PIPESTATUS[0]}
  printf 'exit_code=%d\n' "${rc}" | tee -a "${log}"
  return "${rc}"
}

run_lab1_case "$CASE_NAME" "$MAX_TOKENS" "$GENERATION_REPEATS"