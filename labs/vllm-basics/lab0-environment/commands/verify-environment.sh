#!/usr/bin/env bash
set -euo pipefail

command -v python >/dev/null || { echo "error: python is not on PATH" >&2; exit 1; }

echo "== Operating system =="
uname -a
if [[ -r /etc/os-release ]]; then
  sed -n '1,8p' /etc/os-release
fi

echo "== CPU and memory =="
command -v lscpu >/dev/null && lscpu | sed -n '1,16p'
command -v free >/dev/null && free -h

echo "== Python =="
python --version
python - <<'PY'
from importlib import import_module

for name in ("torch", "vllm"):
    try:
        module = import_module(name)
        print(f"{name}: {getattr(module, '__version__', 'unknown')}")
    except Exception as exc:
        print(f"{name}: unavailable ({exc})")

try:
    import torch
    print(f"torch CUDA runtime: {torch.version.cuda}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"CUDA device count: {torch.cuda.device_count()}")
    for index in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(index)
        print(f"GPU {index}: {props.name}; VRAM={props.total_memory / 2**30:.2f} GiB")
except Exception as exc:
    print(f"PyTorch GPU check failed: {exc}")
PY

echo "== NVIDIA driver =="
if command -v nvidia-smi >/dev/null; then
  nvidia-smi
else
  echo "nvidia-smi unavailable (expected on a non-NVIDIA host)"
fi
