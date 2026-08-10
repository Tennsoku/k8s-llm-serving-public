export MODEL=/models/Qwen2.5-0.5B-Instruct
export SERVED_MODEL_NAME=qwen2.5-0.5b-instruct
export HOST=0.0.0.0
export PORT=8000
export DTYPE=auto
export GPU_MEMORY_UTILIZATION=0.15

date +%s%N >"./results/server-start-ns.txt"
date --iso-8601=seconds >"./results/server-start-time.txt"
set -o pipefail
./lab/commands/start-server.sh \
  2>&1 | tee "./results/server.log"
server_rc=${PIPESTATUS[0]}
printf 'server_exit_code=%d\n' "${server_rc}" | \
  tee -a "./results/server.log"
