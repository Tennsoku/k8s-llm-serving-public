#!/usr/bin/env bash
set -Eeuo pipefail

export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=INIT,BOOTSTRAP,NET,GRAPH,ENV
export NCCL_SOCKET_FAMILY=AF_INET
export NCCL_SOCKET_IFNAME="${DATA_IFACE:-}"
export RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"

if [[ -z "${LOCAL_DATA_IP:-}" || -z "${PEER_DATA_IP:-}" || -z "${DATA_IFACE:-}" || -z "${NODE_LABEL:-}" ]]; then
  echo "Error: LOCAL_DATA_IP, PEER_DATA_IP, DATA_IFACE, and NODE_LABEL must be set. Please source the proper root env file." >&2
  exit 1
fi

mkdir -p "$HOME/workspace/k8s-llm-serving/artifacts/m0-private/$RUN_ID/$NODE_LABEL/tests/nccl-smoke"
TEST_RESULT_DIR="$HOME/workspace/k8s-llm-serving/artifacts/m0-private/$RUN_ID/$NODE_LABEL/tests/nccl-smoke"

while getopts "a:b:r:" opt; do
  case $opt in
    a) SPARK_A="$OPTARG" ;;
    b) SPARK_B="$OPTARG" ;;
    r) TEST_RESULT_DIR="$OPTARG" ;;
    *) echo "Usage: $0 [-a <spark-a-hostname>] [-b <spark-b-hostname>] [-r <result-dir>]" >&2; exit 1 ;;
  esac
done

mpirun \
  --host "$LOCAL_DATA_IP:1,$PEER_DATA_IP:1" \
  -np 2 \
  -N 1 \
  -x PATH \
  -x LD_LIBRARY_PATH \
  -x NCCL_DEBUG \
  -x NCCL_DEBUG_SUBSYS \
  -x NCCL_SOCKET_FAMILY \
  -x NCCL_SOCKET_IFNAME \
  ./build/all_gather_perf_mpi \
    -b 8 \
    -e 512M \
    -f 2 \
    -g 1 \
    -w 5 \
    -n 20 \
    -c 1 \
    -T 120 \
  2>&1 | tee "$TEST_RESULT_DIR/all-gather.log"
  