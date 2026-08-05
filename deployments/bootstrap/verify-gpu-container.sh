#!/usr/bin/env bash
# Verify NVIDIA GPU passthrough and a real CUDA/PyTorch kernel inside a pinned container image.
set -uo pipefail

GPU_IMAGE="${GPU_IMAGE:-${1:-}}"
EXPECTED_GPU_COUNT="${EXPECTED_GPU_COUNT:-1}"
OUTPUT_ROOT="${OUTPUT_ROOT:-./results/bootstrap}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
STAMP="$RUN_ID"
HOST="$(hostname -s 2>/dev/null || hostname)"
OUT_DIR="${OUTPUT_ROOT}/${STAMP}/${HOST}/gpu-container"
mkdir -p "$OUT_DIR"

failures=0; warnings=0
pass(){ printf '[PASS] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; warnings=$((warnings+1)); }
fail(){ printf '[FAIL] %s\n' "$*"; failures=$((failures+1)); }
have(){ command -v "$1" >/dev/null 2>&1; }

printf 'GPU container verification: %s\nEvidence directory: %s\n\n' "$HOST" "$OUT_DIR"

if [[ -z "$GPU_IMAGE" ]]; then
  fail 'Set GPU_IMAGE to a pinned PyTorch/CUDA image, preferably by digest'
  printf 'Example: GPU_IMAGE=nvcr.io/nvidia/pytorch@sha256:<digest> %s\n' "$0"
  exit 1
fi

if [[ "$GPU_IMAGE" != *@sha256:* ]]; then
  warn 'GPU_IMAGE is tag-based rather than digest-pinned; evidence may not be reproducible'
fi

if ! have docker || ! docker info >/dev/null 2>&1; then
  fail 'Docker is unavailable to the current user'
  exit 1
fi

if ! docker image inspect "$GPU_IMAGE" >"$OUT_DIR/image-inspect.json" 2>&1; then
  if docker pull "$GPU_IMAGE" >"$OUT_DIR/image-pull.txt" 2>&1; then pass 'GPU image pulled'; else fail 'GPU image pull failed'; exit 1; fi
fi

docker image inspect --format 'id={{.Id}}\narchitecture={{.Architecture}}\nos={{.Os}}\nrepo_digests={{json .RepoDigests}}' "$GPU_IMAGE" \
  >"$OUT_DIR/image-summary.txt" 2>&1 || true

if docker run --rm "$GPU_IMAGE" uname -m >"$OUT_DIR/container-architecture.txt" 2>&1; then
  pass "Container userspace architecture: $(tail -n 1 "$OUT_DIR/container-architecture.txt")"
else
  fail 'Container could not execute a basic architecture probe'
fi

if docker run --rm --gpus all "$GPU_IMAGE" nvidia-smi >"$OUT_DIR/container-nvidia-smi.txt" 2>&1; then
  pass 'nvidia-smi succeeded inside the container'
else
  fail 'GPU passthrough failed: container nvidia-smi did not succeed'
fi

# Real CUDA work catches cases where device enumeration succeeds but runtime/kernel execution does not.
if docker run --rm -i --gpus all "$GPU_IMAGE" python3 - <<'PY' >"$OUT_DIR/pytorch-cuda-smoke.txt" 2>&1
import json
import sys
import torch

result = {
    "torch": torch.__version__,
    "torch_cuda_runtime": torch.version.cuda,
    "cudnn": torch.backends.cudnn.version(),
    "cuda_available": torch.cuda.is_available(),
    "device_count": torch.cuda.device_count(),
}
if not torch.cuda.is_available():
    print(json.dumps(result, indent=2))
    sys.exit(2)

result["devices"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
result["compute_capability_0"] = torch.cuda.get_device_capability(0)

a = torch.randn((2048, 2048), device="cuda", dtype=torch.float16)
b = torch.randn((2048, 2048), device="cuda", dtype=torch.float16)
c = a @ b
torch.cuda.synchronize()
result["matmul_shape"] = list(c.shape)
result["result_finite"] = bool(torch.isfinite(c).all().item())
result["allocated_bytes"] = torch.cuda.memory_allocated(0)
result["reserved_bytes"] = torch.cuda.memory_reserved(0)
print(json.dumps(result, indent=2))
if not result["result_finite"]:
    sys.exit(3)
PY
then
  pass 'PyTorch CUDA allocation and matrix multiplication passed in container'
else
  fail 'PyTorch CUDA smoke test failed in container'
fi

GPU_COUNT_MARKER='__BOOTSTRAP_GPU_COUNT__='
GPU_COUNT_LOG="$OUT_DIR/container-gpu-count.txt"

if docker run --rm --gpus all "$GPU_IMAGE" \
    python3 -c \
    "import torch; print('${GPU_COUNT_MARKER}' + str(torch.cuda.device_count()))" \
    >"$GPU_COUNT_LOG" 2>&1; then

  actual_gpu_count="$(
    sed -n \
      "s/^${GPU_COUNT_MARKER}\([0-9][0-9]*\)\r\{0,1\}$/\1/p" \
      "$GPU_COUNT_LOG" |
      tail -n 1
  )"

  if [[ -z "$actual_gpu_count" ]]; then
    fail 'Container GPU count probe ran but no structured result marker was found'
  elif (( actual_gpu_count >= EXPECTED_GPU_COUNT )); then
    pass "Container sees expected GPU count (actual=$actual_gpu_count, expected>=$EXPECTED_GPU_COUNT)"
  else
    fail "Container GPU count is $actual_gpu_count; expected at least $EXPECTED_GPU_COUNT"
  fi
else
  fail 'Container GPU count probe failed to execute'
fi

printf '\nSummary: failures=%d warnings=%d\nEvidence: %s\n' "$failures" "$warnings" "$OUT_DIR"
(( failures == 0 ))
