#!/usr/bin/env bash
set -Eeuo pipefail

CUDA_HOME="$(readlink -f /usr/local/cuda)"
MPI_HOME="/usr/local/mpi"
NCCL_HOME="/usr"
TEST_DIR="$HOME/workspace/k8s-llm-serving/distributed/nccl-tests"

while getopts "c:m:n:" opt; do
  case $opt in
    c) CUDA_HOME="$OPTARG" ;;
    m) MPI_HOME="$OPTARG" ;;
    n) NCCL_HOME="$OPTARG" ;;
    t) TEST_DIR="$OPTARG" ;;
    *) echo "Usage: $0 [-c <cuda-home>] [-m <mpi-home>] [-n <nccl-home>] [-t <test-dir>]" >&2; exit 1 ;;
  esac
done

printf '%s\n' \
    "PATH Settings:" \
    "CUDA_HOME=$CUDA_HOME" \
    "MPI_HOME=$MPI_HOME" \
    "NCCL_HOME=$NCCL_HOME"

echo "###### Checking environment... ######"

mkdir -p $TEST_DIR/results/$(date +%Y%m%d)/environment

{
  echo "=== HOST ==="
  hostname
  uname -a

  echo "=== CUDA ==="
  nvcc --version

  echo "=== GPU ==="
  nvidia-smi

  echo "=== NCCL ==="
  ldconfig -p | grep -i nccl || true
  dpkg-query -W | grep -Ei 'nccl' || true

  echo "=== MPI ==="
  mpirun --version || true
  dpkg-query -W | grep -Ei 'openmpi' || true
} | tee "$TEST_DIR/results/$(date +%Y%m%d)/environment/$(hostname).txt"

echo "###### Building nccl-tests... ######"

make clean

make -j"$(nproc)" \
  MPI=1 \
  NAME_SUFFIX=_mpi \
  CUDA_HOME="$CUDA_HOME" \
  MPI_HOME="$MPI_HOME" \
  NCCL_HOME="$NCCL_HOME"

echo "###### nccl-tests build complete. ######"
