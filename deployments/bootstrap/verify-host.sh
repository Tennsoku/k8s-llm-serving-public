#!/usr/bin/env bash
# Read-only host qualification for DGX Spark / Linux GPU nodes.
set -uo pipefail

EXPECTED_ARCH="${EXPECTED_ARCH:-aarch64}"
MIN_ROOT_FREE_GIB="${MIN_ROOT_FREE_GIB:-20}"
OUTPUT_ROOT="${OUTPUT_ROOT:-./results/bootstrap}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
STAMP="$RUN_ID"
HOST="$(hostname -s 2>/dev/null || hostname)"
OUT_DIR="${OUTPUT_ROOT}/${STAMP}/${HOST}/host"
mkdir -p "$OUT_DIR"

failures=0
warnings=0

pass() { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf '[FAIL] %s\n' "$*"; failures=$((failures + 1)); }
info() { printf '[INFO] %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

capture() {
  local file="$1"; shift
  "$@" >"$OUT_DIR/$file" 2>&1
}

printf 'Host verification: %s\nEvidence directory: %s\n\n' "$HOST" "$OUT_DIR"

# 1. Host identity and operating system
capture uname.txt uname -a
if [[ "$(uname -s)" == "Linux" ]]; then pass 'Operating system is Linux'; else fail "Expected Linux, found $(uname -s)"; fi

arch="$(uname -m)"
printf '%s\n' "$arch" >"$OUT_DIR/architecture.txt"
if [[ "$arch" == "$EXPECTED_ARCH" ]]; then
  pass "Architecture is $arch"
else
  fail "Architecture is $arch; expected $EXPECTED_ARCH"
fi

if [[ -r /etc/os-release ]]; then
  cp /etc/os-release "$OUT_DIR/os-release.txt"
  # shellcheck disable=SC1091
  . /etc/os-release
  pass "OS release detected: ${PRETTY_NAME:-unknown}"
else
  fail '/etc/os-release is not readable'
fi

kernel="$(uname -r)"
info "Kernel: $kernel"

# 2. CPU, memory, NUMA, and storage inventory
if have lscpu; then capture lscpu.txt lscpu; pass 'CPU topology captured'; else warn 'lscpu not installed'; fi
if have free; then capture memory.txt free -h; pass 'System memory captured'; else fail 'free command not installed'; fi
if have numactl; then capture numa.txt numactl --hardware; else warn 'numactl not installed; NUMA topology not captured'; fi
if have lsblk; then capture block-devices.txt lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,MODEL; else warn 'lsblk not installed'; fi
capture filesystem.txt df -hT

root_free_kib="$(df -Pk / | awk 'NR==2 {print $4}')"
min_root_free_kib=$((MIN_ROOT_FREE_GIB * 1024 * 1024))
if [[ "$root_free_kib" =~ ^[0-9]+$ ]] && (( root_free_kib >= min_root_free_kib )); then
  pass "Root filesystem has at least ${MIN_ROOT_FREE_GIB} GiB free"
else
  warn "Root filesystem has less than ${MIN_ROOT_FREE_GIB} GiB free"
fi

# 3. Time synchronization: important for correlating two-node evidence.
if have timedatectl; then
  capture time-status.txt timedatectl status
  ntp_sync="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)"
  if [[ "$ntp_sync" == "yes" ]]; then pass 'System clock is NTP-synchronized'; else warn 'NTP synchronization is not confirmed'; fi
else
  warn 'timedatectl unavailable; clock synchronization not checked'
fi

# 4. NVIDIA driver, GPU visibility, device nodes, and kernel modules.
if ! have nvidia-smi; then
  fail 'nvidia-smi not found'
else
  capture nvidia-smi.txt nvidia-smi
  capture gpu-query.csv nvidia-smi --query-gpu=index,name,uuid,driver_version,memory.total,compute_cap --format=csv,noheader
  if nvidia-smi -L >"$OUT_DIR/gpu-list.txt" 2>&1 && [[ -s "$OUT_DIR/gpu-list.txt" ]]; then
    gpu_count="$(wc -l <"$OUT_DIR/gpu-list.txt" | tr -d ' ')"
    pass "NVIDIA GPU visible to host (count=$gpu_count)"
  else
    fail 'nvidia-smi is installed but no GPU was enumerated'
  fi
fi

if [[ -e /dev/nvidiactl ]]; then pass '/dev/nvidiactl exists'; else fail '/dev/nvidiactl is missing'; fi
if compgen -G '/dev/nvidia[0-9]*' >/dev/null; then
  ls -l /dev/nvidia* >"$OUT_DIR/nvidia-device-nodes.txt" 2>&1
  pass 'NVIDIA GPU device node exists'
else
  fail 'No /dev/nvidia[0-9]* device node found'
fi

if have lsmod; then
  capture nvidia-modules.txt bash -c "lsmod | grep -E '^nvidia|^nvidia_' || true"
  if grep -q '^nvidia' "$OUT_DIR/nvidia-modules.txt"; then pass 'NVIDIA kernel module is loaded'; else warn 'NVIDIA kernel module not visible in lsmod output'; fi
fi

# 5. CUDA toolkit inventory. Driver-reported CUDA and nvcc toolkit versions are recorded separately.
if have nvcc; then
  capture nvcc-version.txt nvcc --version
  nvcc_path="$(readlink -f "$(command -v nvcc)")"
  printf '%s\n' "$nvcc_path" >"$OUT_DIR/nvcc-path.txt"
  pass "CUDA compiler found: $nvcc_path"
else
  fail 'nvcc not found; host CUDA smoke test cannot be rebuilt'
fi

if [[ -e /usr/local/cuda ]]; then
  readlink -f /usr/local/cuda >"$OUT_DIR/cuda-symlink-target.txt"
  pass '/usr/local/cuda exists'
else
  warn '/usr/local/cuda is missing'
fi

if have ldconfig; then
  ldconfig -p 2>/dev/null | grep -E 'libcudart\.so' >"$OUT_DIR/libcudart.txt" || true
  [[ -s "$OUT_DIR/libcudart.txt" ]] && pass 'CUDA runtime library found by ldconfig' || warn 'libcudart not found by ldconfig'
fi

# 6. Host Python/PyTorch is useful evidence, but container-first workflows may intentionally omit it.
if have python3; then
  capture python-version.txt python3 --version
  pass 'python3 found'
  if python3 - <<'PY' >"$OUT_DIR/pytorch-host.txt" 2>&1
import torch
print(f"torch={torch.__version__}")
print(f"torch_cuda_runtime={torch.version.cuda}")
print(f"cuda_available={torch.cuda.is_available()}")
print(f"device_count={torch.cuda.device_count()}")
if torch.cuda.is_available():
    print(f"device_0={torch.cuda.get_device_name(0)}")
PY
  then
    if grep -q 'cuda_available=True' "$OUT_DIR/pytorch-host.txt"; then
      pass 'Host PyTorch can access CUDA'
    else
      warn 'Host PyTorch is installed but CUDA is unavailable'
    fi
  else
    warn 'Host PyTorch is not installed or could not be imported'
  fi
else
  warn 'python3 not found'
fi

# 7. Optional host CUDA execution smoke test supplied by the repository/user.
# Set CUDA_SMOKE_BIN=/path/to/vector_add to enable it.
if [[ -n "${CUDA_SMOKE_BIN:-}" ]]; then
  if [[ -x "$CUDA_SMOKE_BIN" ]]; then
    if "$CUDA_SMOKE_BIN" >"$OUT_DIR/cuda-smoke.txt" 2>&1; then pass 'Host CUDA smoke binary passed'; else fail 'Host CUDA smoke binary failed'; fi
  else
    fail "CUDA_SMOKE_BIN is not executable: $CUDA_SMOKE_BIN"
  fi
else
  warn 'CUDA_SMOKE_BIN not set; host CUDA kernel execution was not tested by this script'
fi

# 8. Minimal environment fingerprint for comparison across nodes/runs.
{
  printf 'timestamp_utc=%s\n' "$STAMP"
  printf 'hostname=%s\n' "$HOST"
  printf 'architecture=%s\n' "$arch"
  printf 'kernel=%s\n' "$kernel"
  printf 'os=%s\n' "${PRETTY_NAME:-unknown}"
  printf 'git_commit=%s\n' "$(git rev-parse HEAD 2>/dev/null || echo not-a-git-repository)"
} >"$OUT_DIR/fingerprint.env"

printf '\nSummary: failures=%d warnings=%d\n' "$failures" "$warnings"
printf 'Evidence: %s\n' "$OUT_DIR"
(( failures == 0 ))
