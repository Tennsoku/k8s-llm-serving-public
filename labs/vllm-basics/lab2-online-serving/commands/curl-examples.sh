#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
MODEL="${MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"

command -v curl >/dev/null || { echo "error: curl is required" >&2; exit 1; }

echo "== Models =="
curl --fail-with-body --silent --show-error "${BASE_URL}/v1/models"
printf '\n\n== Non-streaming chat completion ==\n'
curl --fail-with-body --silent --show-error \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"Explain KV cache in one sentence.\"}],\"temperature\":0,\"max_tokens\":32}" \
  "${BASE_URL}/v1/chat/completions"
printf '\n\n== Streaming chat completion (SSE) ==\n'
curl --no-buffer --fail-with-body --silent --show-error \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"Count from one to five.\"}],\"temperature\":0,\"max_tokens\":32,\"stream\":true}" \
  "${BASE_URL}/v1/chat/completions"

printf '\n\n== Expected failure: unknown model ==\n'
status="$(curl --silent --output /tmp/vllm-lab-error.json --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"model":"not-a-served-model","messages":[{"role":"user","content":"hello"}]}' \
  "${BASE_URL}/v1/chat/completions")"
printf 'HTTP %s\n' "${status}"
sed -n '1,20p' /tmp/vllm-lab-error.json
[[ "${status}" -ge 400 ]] || { echo "error: failure case unexpectedly succeeded" >&2; exit 1; }
