#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${VENV_DIR:-.venv-vllm}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VLLM_SPEC="${VLLM_SPEC:-vllm}"

command -v "${PYTHON_BIN}" >/dev/null || { echo "error: ${PYTHON_BIN} is not on PATH" >&2; exit 1; }
if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install "${VLLM_SPEC}"
python -c 'import torch, vllm; print("torch", torch.__version__); print("vllm", vllm.__version__); print("CUDA", torch.cuda.is_available())'

echo "Activate with: source ${VENV_DIR}/bin/activate"
