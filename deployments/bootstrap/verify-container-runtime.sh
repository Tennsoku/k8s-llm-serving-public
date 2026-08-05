#!/usr/bin/env bash
# Verify the non-GPU container runtime path. GPU execution belongs in verify-gpu-container.sh.
set -uo pipefail

RUNTIME_SMOKE_IMAGE="${RUNTIME_SMOKE_IMAGE:-hello-world:latest}"
OUTPUT_ROOT="${OUTPUT_ROOT:-./results/bootstrap}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
STAMP="$RUN_ID"
HOST="$(hostname -s 2>/dev/null || hostname)"
OUT_DIR="${OUTPUT_ROOT}/${STAMP}/${HOST}/container-runtime"
mkdir -p "$OUT_DIR"

failures=0; warnings=0
pass(){ printf '[PASS] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; warnings=$((warnings+1)); }
fail(){ printf '[FAIL] %s\n' "$*"; failures=$((failures+1)); }
have(){ command -v "$1" >/dev/null 2>&1; }

printf 'Container runtime verification: %s\nEvidence directory: %s\n\n' "$HOST" "$OUT_DIR"

if ! have docker; then
  fail 'docker CLI not found'
  printf '\nSummary: failures=%d warnings=%d\n' "$failures" "$warnings"
  exit 1
fi

docker version >"$OUT_DIR/docker-version.txt" 2>&1 || true
if docker info >"$OUT_DIR/docker-info.txt" 2>&1; then
  pass 'Docker client can reach the daemon'
else
  fail 'Docker daemon is unavailable or the current user lacks socket permission'
  ls -l /var/run/docker.sock >"$OUT_DIR/docker-socket.txt" 2>&1 || true
  id >"$OUT_DIR/user-groups.txt" 2>&1 || true
fi

if docker info --format '{{json .}}' >"$OUT_DIR/docker-info.json" 2>/dev/null; then
  docker info --format 'server_version={{.ServerVersion}}\nos={{.OperatingSystem}}\narch={{.Architecture}}\nstorage_driver={{.Driver}}\ncgroup_driver={{.CgroupDriver}}\ncgroup_version={{.CgroupVersion}}\nroot_dir={{.DockerRootDir}}\nsecurity_options={{json .SecurityOptions}}\nruntimes={{json .Runtimes}}\ndefault_runtime={{.DefaultRuntime}}' \
    >"$OUT_DIR/docker-summary.txt" 2>&1 || true
  pass 'Docker server configuration captured'
fi

if [[ -S /var/run/docker.sock ]]; then
  ls -l /var/run/docker.sock >"$OUT_DIR/docker-socket.txt"
  pass 'Docker socket exists'
else
  warn '/var/run/docker.sock does not exist; runtime may be rootless or use another endpoint'
fi

id >"$OUT_DIR/user-groups.txt"
if id -nG | tr ' ' '\n' | grep -qx docker; then
  pass 'Current user is in the docker group'
else
  warn 'Current user is not in the docker group; access may rely on rootless Docker or sudo'
fi

# Record NVIDIA container-toolkit components without claiming GPU execution works.
if have nvidia-ctk; then nvidia-ctk --version >"$OUT_DIR/nvidia-ctk-version.txt" 2>&1; pass 'nvidia-ctk found'; else warn 'nvidia-ctk not found'; fi
if have nvidia-container-cli; then nvidia-container-cli --version >"$OUT_DIR/nvidia-container-cli-version.txt" 2>&1; pass 'nvidia-container-cli found'; else warn 'nvidia-container-cli not found'; fi

# A plain container smoke test proves image pull/create/start/exit/remove, independent of GPU passthrough.
if docker run --rm "$RUNTIME_SMOKE_IMAGE" >"$OUT_DIR/runtime-smoke.txt" 2>&1; then
  pass "Plain container executed successfully: $RUNTIME_SMOKE_IMAGE"
  docker image inspect "$RUNTIME_SMOKE_IMAGE" >"$OUT_DIR/runtime-smoke-image-inspect.json" 2>&1 || true
else
  fail "Plain container failed: $RUNTIME_SMOKE_IMAGE"
fi

if docker buildx version >"$OUT_DIR/buildx-version.txt" 2>&1; then
  pass 'Docker Buildx is available for multi-architecture builds'
else
  warn 'Docker Buildx is unavailable'
fi

printf '\nSummary: failures=%d warnings=%d\nEvidence: %s\n' "$failures" "$warnings" "$OUT_DIR"
(( failures == 0 ))
