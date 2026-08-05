#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
readonly SCRIPT_DIR REPO_ROOT

cmd="${1:-}"
ENV_FILE="${M0_ENV_FILE:-$REPO_ROOT/.env.m0.local}"
PRIVATE_EVIDENCE_ROOT="${PRIVATE_EVIDENCE_ROOT:-artifacts/m0-private}"
PUBLIC_EVIDENCE_ROOT="${PUBLIC_EVIDENCE_ROOT:-benchmarks/raw-results/m0-platform-qualification}"
EXPECTED_PRIVATE_EVIDENCE_ROOT="artifacts/m0-private"
EXPECTED_PUBLIC_EVIDENCE_ROOT="benchmarks/raw-results/m0-platform-qualification"
readonly EXPECTED_PRIVATE_EVIDENCE_ROOT EXPECTED_PUBLIC_EVIDENCE_ROOT
PRIVATE_ENV_LOADED=0

# A public clone intentionally has no private environment file. Help and
# verify-public therefore use only explicit environment variables/defaults.
case "$cmd" in
  ""|-h|--help|help|verify-public)
    ;;
  *)
    if [[ ! -f "$ENV_FILE" ]]; then
      echo "Missing $ENV_FILE" >&2
      echo "Copy config/m0-evidence.env.example to .env.m0.local and edit it." >&2
      exit 2
    fi
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    PRIVATE_ENV_LOADED=1
    ;;
esac

RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
PRIVATE_ROOT="$REPO_ROOT/$PRIVATE_EVIDENCE_ROOT/$RUN_ID"
PUBLIC_ROOT="$REPO_ROOT/$PUBLIC_EVIDENCE_ROOT/$RUN_ID"
NIC_COUNTER_REGEX="${NIC_COUNTER_REGEX:-(^|_)(rx|tx)_(bytes|packets|errors|dropped|discard|crc|pause)|roce|rdma|ecn|cong|retrans|out_of_buffer}"

umask 077

validate_component() {
  local label="$1" value="$2"
  if [[ ! "$value" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || [[ "$value" == "." || "$value" == ".." ]]; then
    echo "Invalid $label: expected one safe path component" >&2
    return 1
  fi
}

validate_relative_root() {
  local label="$1" value="$2" part
  local -a parts=()
  if [[ -z "$value" || "$value" == /* || ! "$value" =~ ^[A-Za-z0-9._/-]+$ ]]; then
    echo "Invalid $label: expected a repository-relative path" >&2
    return 1
  fi
  IFS='/' read -r -a parts <<<"$value"
  for part in "${parts[@]}"; do
    if [[ -z "$part" || "$part" == "." || "$part" == ".." ]]; then
      echo "Invalid $label: empty, '.' and '..' segments are forbidden" >&2
      return 1
    fi
  done
}

validate_remote_absolute_root() {
  local value="$1" part
  local -a parts=()
  if [[ ! "$value" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
    echo "Invalid REMOTE_REPO_ROOT: expected a simple absolute path" >&2
    return 1
  fi
  IFS='/' read -r -a parts <<<"${value#/}"
  for part in "${parts[@]}"; do
    [[ -n "$part" && "$part" != "." && "$part" != ".." ]] || {
      echo "Invalid REMOTE_REPO_ROOT path segment" >&2
      return 1
    }
  done
}

validate_relative_root PRIVATE_EVIDENCE_ROOT "$PRIVATE_EVIDENCE_ROOT" || exit 2
validate_relative_root PUBLIC_EVIDENCE_ROOT "$PUBLIC_EVIDENCE_ROOT" || exit 2

if [[ "$PRIVATE_EVIDENCE_ROOT" != "$EXPECTED_PRIVATE_EVIDENCE_ROOT" ||
      "$PUBLIC_EVIDENCE_ROOT" != "$EXPECTED_PUBLIC_EVIDENCE_ROOT" ]]; then
  echo "Evidence roots are fixed to the dedicated private and public M0 directories" >&2
  exit 2
fi

private_base="$(realpath -m -- "$REPO_ROOT/$PRIVATE_EVIDENCE_ROOT")"
public_base="$(realpath -m -- "$REPO_ROOT/$PUBLIC_EVIDENCE_ROOT")"
repo_base="$(realpath -m -- "$REPO_ROOT")"
expected_private_base="$repo_base/$EXPECTED_PRIVATE_EVIDENCE_ROOT"
expected_public_base="$repo_base/$EXPECTED_PUBLIC_EVIDENCE_ROOT"
if [[ "$private_base" != "$expected_private_base" || "$public_base" != "$expected_public_base" ]]; then
  echo "Evidence roots must resolve to their dedicated repository directories without symlink indirection" >&2
  exit 2
fi

ensure_private_path() {
  local run_id="$1" target="${2%/}" run_root resolved_run resolved_target
  run_root="$private_base/$run_id"
  if [[ "$target" != "$run_root" && "$target" != "$run_root/"* ]]; then
    echo "Private evidence target escaped its run directory" >&2
    return 1
  fi
  if ! resolved_run="$(realpath -m -- "$run_root")" ||
     ! resolved_target="$(realpath -m -- "$target")"; then
    echo "Unable to resolve private evidence target" >&2
    return 1
  fi
  if [[ "$resolved_run" != "$run_root" || "$resolved_target" != "$target" ||
        -L "$run_root" || -L "$target" ]]; then
    echo "Private evidence target may not contain symlink indirection" >&2
    return 1
  fi
}

prepare_private_output_dir() {
  local run_id="$1" target="${2%/}" existing
  ensure_private_path "$run_id" "$target" || return 1
  if [[ -e "$target" || -L "$target" ]]; then
    [[ -d "$target" && ! -L "$target" ]] || {
      echo "Private evidence target exists but is not a regular directory" >&2
      return 1
    }
    if IFS= read -r -d '' existing < <(find "$target" -mindepth 1 -print0 -quit); then
      echo "Refusing to overwrite a non-empty private evidence capture" >&2
      return 1
    fi
  fi
  mkdir -p "$target"
  ensure_private_path "$run_id" "$target"
}

case "$cmd" in
  node|test|tcp|distributed)
    : "${NODE_LABEL:?NODE_LABEL is required}"
    : "${DATA_IFACE:?DATA_IFACE is required}"
    validate_component RUN_ID "$RUN_ID" || exit 2
    validate_component NODE_LABEL "$NODE_LABEL" || exit 2
    ;;
esac

usage() {
  cat <<'USAGE'
Usage:
  scripts/m0/m0-evidence.sh node
  scripts/m0/m0-evidence.sh test NAME -- COMMAND [ARG ...]
  scripts/m0/m0-evidence.sh tcp
  scripts/m0/m0-evidence.sh distributed NAME -- COMMAND [ARG ...]
  scripts/m0/m0-evidence.sh pull-remote [RUN_ID]
  scripts/m0/m0-evidence.sh publish [RUN_ID]
  scripts/m0/m0-evidence.sh verify-public RUN_ID

Examples:
  scripts/m0/m0-evidence.sh node
  scripts/m0/m0-evidence.sh test cuda-host -- bash -lc 'nvcc -O2 -std=c++17 vector_add.cu -o vector_add && ./vector_add'
  scripts/m0/m0-evidence.sh tcp
  scripts/m0/m0-evidence.sh distributed nccl-all-reduce -- mpirun ... ./all_reduce_perf ...
  scripts/m0/m0-evidence.sh pull-remote
  scripts/m0/m0-evidence.sh publish
USAGE
}

have() { command -v "$1" >/dev/null 2>&1; }

shell_join() {
  local out="" arg
  for arg in "$@"; do
    printf -v out '%s%q ' "$out" "$arg"
  done
  printf '%s\n' "${out% }"
}

section() {
  local file="$1" title="$2"
  shift 2
  {
    printf '\n===== %s =====\n' "$title"
    printf '$ '
    shell_join "$@"
    "$@"
    local rc=$?
    printf '\n[exit_code=%s]\n' "$rc"
    return 0
  } >>"$file" 2>&1 || true
}

section_shell() {
  local file="$1" title="$2" code="$3"
  section "$file" "$title" bash -lc "$code"
}

record_context() {
  local file="$1"
  {
    printf 'run_id=%s\n' "$RUN_ID"
    printf 'node_label=%s\n' "$NODE_LABEL"
    printf 'captured_at_utc=%s\n' "$(date -u +%FT%TZ)"
    printf 'data_iface=%s\n' "$DATA_IFACE"
    printf 'kernel=%s\n' "$(uname -srmo 2>/dev/null || true)"
    printf 'git_commit=%s\n' "$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo not-a-git-repository)"
    printf 'git_dirty=%s\n' "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null | { read -r _ && echo true || echo false; })"
  } >"$file"
}

nic_snapshot() {
  local iface="$1" output="$2"
  {
    printf '# captured_at_utc=%s\n' "$(date -u +%FT%TZ)"
    printf '# interface=%s\n' "$iface"
    if have ip; then
      printf '\n## ip -s link\n'
      ip -s link show dev "$iface" 2>&1 || true
    fi
    if have ethtool; then
      printf '\n## ethtool key counters\n'
      ethtool -S "$iface" 2>/dev/null | grep -Ei "$NIC_COUNTER_REGEX" || true
      if [[ "${COLLECT_FULL_NIC_STATS:-0}" == "1" ]]; then
        printf '\n## ethtool full counters\n'
        ethtool -S "$iface" 2>&1 || true
      fi
    fi
  } >"$output"
}

remote_nic_snapshot() {
  local output="$1"
  : "${REMOTE_HOST:?REMOTE_HOST is required}"
  : "${REMOTE_DATA_IFACE:?REMOTE_DATA_IFACE is required}"
  local -a ssh_opts=()
  if [[ -n "${SSH_OPTS:-}" ]]; then
    # Intentionally permit a locally controlled option string from the uncommitted env file.
    # shellcheck disable=SC2206
    ssh_opts=(${SSH_OPTS})
  fi
  local remote_cmd
  printf -v remote_cmd 'printf "# captured_at_utc=%%s\\n# interface=%%s\\n\\n## ip -s link\\n" "$(date -u +%%FT%%TZ)" %q; ip -s link show dev %q 2>&1 || true; if command -v ethtool >/dev/null 2>&1; then printf "\\n## ethtool key counters\\n"; ethtool -S %q 2>/dev/null | grep -Ei %q || true; fi' \
    "$REMOTE_DATA_IFACE" "$REMOTE_DATA_IFACE" "$REMOTE_DATA_IFACE" "$NIC_COUNTER_REGEX"
  local remote_rc=0
  if ssh "${ssh_opts[@]}" "$REMOTE_HOST" "bash -lc $(printf '%q' "$remote_cmd")" >"$output" 2>&1; then
    remote_rc=0
  else
    remote_rc=$?
  fi
  local remote_counter_count=0
  remote_counter_count="$(awk '/^[[:space:]]*[A-Za-z0-9_.-]+:[[:space:]]*[0-9]+[[:space:]]*$/ {count++} END {print count+0}' "$output")"
  printf '\n[remote_snapshot_exit_code=%s]\n[remote_ethtool_counter_count=%s]\n' \
    "$remote_rc" "$remote_counter_count" >>"$output"
  (( remote_rc == 0 )) || return "$remote_rc"
  (( remote_counter_count > 0 )) || return 6
}

extract_ethtool() {
  awk '
    /^## ethtool full counters/ {exit}
    /^[[:space:]]*[A-Za-z0-9_.-]+:[[:space:]]*[0-9]+[[:space:]]*$/ {
      line=$0
      sub(/^[[:space:]]*/, "", line)
      split(line, a, ":")
      key=a[1]
      value=a[2]
      gsub(/[[:space:]]/, "", value)
      if (value ~ /^[0-9]+$/) print key "\t" value
    }
  ' "$1"
}

nic_delta() {
  local before="$1" after="$2" output="$3"
  local btmp atmp
  btmp="$(mktemp)"; atmp="$(mktemp)"
  extract_ethtool "$before" >"$btmp"
  extract_ethtool "$after" >"$atmp"
  awk -F '\t' '
    NR==FNR {before[$1]=$2; next}
    ($1 in before) {
      delta=$2-before[$1]
      if (delta != 0) print $1 "\t" before[$1] "\t" $2 "\t" delta
    }
  ' "$btmp" "$atmp" | {
    printf 'counter\tbefore\tafter\tdelta\n'
    cat
  } >"$output"
  rm -f "$btmp" "$atmp"
}

collect_node() {
  local out="$PRIVATE_ROOT/$NODE_LABEL/node"
  prepare_private_output_dir "$RUN_ID" "$out" || exit 4
  record_context "$out/context.env"

  : >"$out/platform.txt"
  section "$out/platform.txt" "UTC timestamp" date -u +%FT%TZ
  section "$out/platform.txt" "OS release" cat /etc/os-release
  section "$out/platform.txt" "Kernel and architecture" uname -srmo
  if have lscpu; then
    section_shell "$out/platform.txt" "CPU summary" "lscpu | grep -E '^(Architecture|CPU\\(s\\)|Model name|Socket\\(s\\)|Core\\(s\\) per socket|Thread\\(s\\) per core|NUMA node\\(s\\)):'"
  fi
  section "$out/platform.txt" "Memory summary" free -h

  : >"$out/gpu-cuda.txt"
  if have nvidia-smi; then
    section "$out/gpu-cuda.txt" "GPU key fields" nvidia-smi --query-gpu=timestamp,name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw,pci.bus_id --format=csv,noheader
  else
    printf 'nvidia-smi: NOT INSTALLED\n' >>"$out/gpu-cuda.txt"
  fi
  if have nvcc; then section "$out/gpu-cuda.txt" "NVCC" nvcc --version; else printf 'nvcc: NOT INSTALLED\n' >>"$out/gpu-cuda.txt"; fi
  section_shell "$out/gpu-cuda.txt" "CUDA symlink" "readlink -f /usr/local/cuda 2>/dev/null || true"

  : >"$out/runtime-stack.txt"
  if have docker; then
    section_shell "$out/runtime-stack.txt" "Docker versions" "docker version --format 'client={{.Client.Version}} server={{.Server.Version}}' 2>&1"
    section_shell "$out/runtime-stack.txt" "Docker runtime names" "docker info --format '{{json .Runtimes}}' 2>&1"
  else
    printf 'docker: NOT INSTALLED\n' >>"$out/runtime-stack.txt"
  fi
  if have nvidia-ctk; then section "$out/runtime-stack.txt" "NVIDIA Container Toolkit" nvidia-ctk --version; fi
  if have python3; then
    section "$out/runtime-stack.txt" "Python" python3 --version
    section_shell "$out/runtime-stack.txt" "PyTorch/CUDA" "python3 -c 'import torch; print(\"torch=\" + torch.__version__); print(\"cuda_available=\" + str(torch.cuda.is_available())); print(\"torch_cuda=\" + str(torch.version.cuda))'"
    section_shell "$out/runtime-stack.txt" "vLLM" "python3 -c 'import vllm; print(\"vllm=\" + vllm.__version__)'"
  fi
  if have dpkg-query; then
    section_shell "$out/runtime-stack.txt" "Relevant packages" "dpkg-query -W -f='\${binary:Package}\\t\${Version}\\n' 2>/dev/null | grep -E '^(docker|containerd|nvidia-container|libnccl|rdma-core|ibverbs|openmpi|hpcx)' || true"
  fi
  if have mpirun; then section "$out/runtime-stack.txt" "MPI" mpirun --version; fi

  : >"$out/network-rdma.txt"
  if have ip; then
    section "$out/network-rdma.txt" "Interfaces" ip -br link show
    section "$out/network-rdma.txt" "Addresses" ip -br addr show
    section "$out/network-rdma.txt" "Routes" ip route show
  fi
  if have ethtool; then
    section "$out/network-rdma.txt" "Data interface link" ethtool "$DATA_IFACE"
    section "$out/network-rdma.txt" "Data interface driver" ethtool -i "$DATA_IFACE"
  fi
  if have lspci; then section_shell "$out/network-rdma.txt" "Relevant PCI devices" "lspci -nn | grep -Ei 'NVIDIA|Mellanox|Ethernet|Network' || true"; fi
  if have rdma; then section "$out/network-rdma.txt" "RDMA links" rdma link show; fi
  if have ibv_devices; then section "$out/network-rdma.txt" "IB verbs devices" ibv_devices; fi
  if have ibv_devinfo; then section "$out/network-rdma.txt" "IB verbs device summary" ibv_devinfo -l; fi
  if have show_gids; then section "$out/network-rdma.txt" "GID table" show_gids; fi
  if have ldconfig; then section_shell "$out/network-rdma.txt" "RDMA/NCCL libraries" "ldconfig -p | grep -E 'libnccl|libmlx5|libibverbs' || true"; fi
  section_shell "$out/network-rdma.txt" "mlx5 library target" "readlink -f /lib/aarch64-linux-gnu/libmlx5.so.1 2>/dev/null || true"
  nic_snapshot "$DATA_IFACE" "$out/nic-key-counters.txt"

  : >"$out/images.txt"
  local image
  for image in "${GPU_TEST_IMAGE:-}" "${VLLM_IMAGE:-}"; do
    [[ -z "$image" ]] && continue
    if have docker; then
      section "$out/images.txt" "Image $image" docker image inspect "$image" --format 'id={{.Id}} repo_digests={{json .RepoDigests}} arch={{.Architecture}} os={{.Os}}'
    fi
  done

  : >"$out/repository.txt"
  local repo_q
  printf -v repo_q '%q' "$REPO_ROOT"
  section_shell "$out/repository.txt" "Git revision" "git -C $repo_q rev-parse HEAD 2>/dev/null || true"
  section_shell "$out/repository.txt" "Git dirty flag" "test -z \"\$(git -C $repo_q status --porcelain 2>/dev/null)\" && echo false || echo true"
  section "$out/repository.txt" "Collector checksum" sha256sum "$0"

  (cd "$out" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
  echo "Collected node evidence: $out"
}

capture_test() {
  local name="$1"; shift
  validate_component "test name" "$name" || exit 2
  [[ "${1:-}" == "--" ]] && shift
  (($# > 0)) || { echo "No command supplied" >&2; exit 2; }
  local out="$PRIVATE_ROOT/$NODE_LABEL/tests/$name"
  prepare_private_output_dir "$RUN_ID" "$out" || exit 4
  record_context "$out/context.env"
  shell_join "$@" >"$out/command.txt"
  nic_snapshot "$DATA_IFACE" "$out/nic-before.txt"
  local start_epoch end_epoch rc
  start_epoch="$(date +%s)"
  printf 'started_at_utc=%s\n' "$(date -u +%FT%TZ)" >"$out/result.env"
  set +e
  "$@" > >(tee "$out/stdout.log") 2> >(tee "$out/stderr.log" >&2)
  rc=$?
  set -e
  end_epoch="$(date +%s)"
  nic_snapshot "$DATA_IFACE" "$out/nic-after.txt"
  nic_delta "$out/nic-before.txt" "$out/nic-after.txt" "$out/nic-delta.tsv"
  {
    printf 'finished_at_utc=%s\n' "$(date -u +%FT%TZ)"
    printf 'duration_seconds=%s\n' "$((end_epoch-start_epoch))"
    printf 'exit_code=%s\n' "$rc"
  } >>"$out/result.env"
  (cd "$out" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
  echo "Captured test evidence: $out"
  return "$rc"
}

capture_distributed() {
  local name="$1"; shift
  validate_component "distributed test name" "$name" || exit 2
  [[ "${1:-}" == "--" ]] && shift
  (($# > 0)) || { echo "No command supplied" >&2; exit 2; }
  : "${REMOTE_LABEL:?REMOTE_LABEL is required}"
  validate_component REMOTE_LABEL "$REMOTE_LABEL" || exit 2
  local out="$PRIVATE_ROOT/distributed/$name"
  prepare_private_output_dir "$RUN_ID" "$out" || exit 4
  mkdir -p "$out/local" "$out/remote"
  shell_join "$@" >"$out/command.txt"
  record_context "$out/context.env"
  nic_snapshot "$DATA_IFACE" "$out/local/nic-before.txt"
  local remote_before_rc remote_after_rc
  if remote_nic_snapshot "$out/remote/nic-before.txt"; then remote_before_rc=0; else remote_before_rc=$?; fi
  local start_epoch end_epoch rc
  start_epoch="$(date +%s)"
  printf 'started_at_utc=%s\n' "$(date -u +%FT%TZ)" >"$out/result.env"
  set +e
  "$@" > >(tee "$out/stdout.log") 2> >(tee "$out/stderr.log" >&2)
  rc=$?
  set -e
  end_epoch="$(date +%s)"
  nic_snapshot "$DATA_IFACE" "$out/local/nic-after.txt"
  if remote_nic_snapshot "$out/remote/nic-after.txt"; then remote_after_rc=0; else remote_after_rc=$?; fi
  nic_delta "$out/local/nic-before.txt" "$out/local/nic-after.txt" "$out/local/nic-delta.tsv"
  nic_delta "$out/remote/nic-before.txt" "$out/remote/nic-after.txt" "$out/remote/nic-delta.tsv"
  {
    printf 'finished_at_utc=%s\n' "$(date -u +%FT%TZ)"
    printf 'duration_seconds=%s\n' "$((end_epoch-start_epoch))"
    printf 'exit_code=%s\n' "$rc"
    printf 'remote_before_snapshot_exit_code=%s\n' "$remote_before_rc"
    printf 'remote_after_snapshot_exit_code=%s\n' "$remote_after_rc"
  } >>"$out/result.env"
  (cd "$out" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
  echo "Captured distributed evidence: $out"
  (( rc == 0 )) || return "$rc"
  (( remote_before_rc == 0 && remote_after_rc == 0 )) || return 6
}

capture_tcp() {
  : "${REMOTE_HOST:?REMOTE_HOST is required}"
  : "${PEER_DATA_IP:?PEER_DATA_IP is required}"
  : "${REMOTE_LABEL:?REMOTE_LABEL is required}"
  validate_component REMOTE_LABEL "$REMOTE_LABEL" || exit 2
  have iperf3 || { echo "iperf3 is required on both nodes" >&2; exit 3; }
  local out="$PRIVATE_ROOT/distributed/tcp-baseline"
  prepare_private_output_dir "$RUN_ID" "$out" || exit 4
  mkdir -p "$out/local" "$out/remote"
  shell_join "$0" tcp >"$out/command.txt"
  sha256sum "$0" >"$out/collector.sha256"
  record_context "$out/context.env"
  nic_snapshot "$DATA_IFACE" "$out/local/nic-before.txt"
  local remote_before_rc remote_after_rc
  if remote_nic_snapshot "$out/remote/nic-before.txt"; then remote_before_rc=0; else remote_before_rc=$?; fi

  local -a ssh_opts=()
  if [[ -n "${SSH_OPTS:-}" ]]; then
    # shellcheck disable=SC2206
    ssh_opts=(${SSH_OPTS})
  fi

  set +e
  ping -c "${PING_COUNT:-20}" -i 0.2 "$PEER_DATA_IP" >"$out/ping.stdout.log" 2>"$out/ping.stderr.log"
  local ping_rc=$?

  ssh "${ssh_opts[@]}" "$REMOTE_HOST" "iperf3 -s -1 -J" >"$out/iperf-server.json" 2>"$out/iperf-server.stderr.log" &
  local server_pid=$!
  sleep 2
  iperf3 -c "$PEER_DATA_IP" -P "${IPERF_PARALLEL:-4}" -t "${IPERF_SECONDS:-30}" -J >"$out/iperf-client.json" 2>"$out/iperf-client.stderr.log"
  local client_rc=$?
  wait "$server_pid"
  local server_rc=$?
  set -e

  nic_snapshot "$DATA_IFACE" "$out/local/nic-after.txt"
  if remote_nic_snapshot "$out/remote/nic-after.txt"; then remote_after_rc=0; else remote_after_rc=$?; fi
  nic_delta "$out/local/nic-before.txt" "$out/local/nic-after.txt" "$out/local/nic-delta.tsv"
  nic_delta "$out/remote/nic-before.txt" "$out/remote/nic-after.txt" "$out/remote/nic-delta.tsv"
  {
    printf 'captured_at_utc=%s\n' "$(date -u +%FT%TZ)"
    printf 'ping_exit_code=%s\n' "$ping_rc"
    printf 'iperf_client_exit_code=%s\n' "$client_rc"
    printf 'iperf_server_exit_code=%s\n' "$server_rc"
    printf 'remote_before_snapshot_exit_code=%s\n' "$remote_before_rc"
    printf 'remote_after_snapshot_exit_code=%s\n' "$remote_after_rc"
    printf 'parallel_streams=%s\n' "${IPERF_PARALLEL:-4}"
    printf 'duration_seconds=%s\n' "${IPERF_SECONDS:-30}"
  } >"$out/result.env"
  (cd "$out" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
  echo "Captured TCP evidence: $out"
  (( ping_rc == 0 )) || return "$ping_rc"
  (( client_rc == 0 )) || return "$client_rc"
  (( server_rc == 0 )) || return "$server_rc"
  (( remote_before_rc == 0 && remote_after_rc == 0 )) || return 6
}

pull_remote() {
  local requested_run="${1:-$RUN_ID}"
  : "${REMOTE_HOST:?REMOTE_HOST is required}"
  : "${REMOTE_LABEL:?REMOTE_LABEL is required}"
  : "${REMOTE_REPO_ROOT:?REMOTE_REPO_ROOT is required}"
  validate_component RUN_ID "$requested_run" || exit 2
  validate_component REMOTE_LABEL "$REMOTE_LABEL" || exit 2
  validate_remote_absolute_root "$REMOTE_REPO_ROOT" || exit 2
  [[ "$REMOTE_HOST" =~ ^([A-Za-z0-9._-]+@)?[A-Za-z0-9._-]+$ ]] || {
    echo "Invalid REMOTE_HOST" >&2
    exit 2
  }
  have rsync || { echo "rsync is required locally and remotely" >&2; exit 3; }
  local source_path="$REMOTE_REPO_ROOT/$PRIVATE_EVIDENCE_ROOT/$requested_run/$REMOTE_LABEL/"
  local target_path="$REPO_ROOT/$PRIVATE_EVIDENCE_ROOT/$requested_run/$REMOTE_LABEL/"
  local ssh_command="ssh ${SSH_OPTS:-}"
  ensure_private_path "$requested_run" "$target_path" || exit 4
  mkdir -p "$target_path"
  ensure_private_path "$requested_run" "$target_path" || exit 4
  rsync -a --delete -e "$ssh_command" "$REMOTE_HOST:$source_path" "$target_path"
  echo "Pulled remote node evidence into: $target_path"
}

literal_replace_tree() {
  local root="$1" literal="$2" replacement="$3" file
  [[ -z "$literal" ]] && return 0
  while IFS= read -r -d '' file; do
    LITERAL="$literal" REPLACEMENT="$replacement" \
      perl -pi -e '$l=$ENV{LITERAL}; $r=$ENV{REPLACEMENT}; s/\Q$l\E/$r/g' "$file"
  done < <(find "$root" -type f -print0)
}

declare -a PRIVATE_SCAN_LITERALS=()

trim_private_item() {
  local value="${1:-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

append_private_literal() {
  local literal
  literal="$(trim_private_item "${1:-}")"
  [[ -n "$literal" ]] || return 0
  [[ ${#literal} -ge 4 && "$literal" != "/" && "$literal" != "." && "$literal" != ".." && "$literal" != *$'\n'* && "$literal" != *$'\r'* ]] || {
    echo "Private literals must be at least four characters and may not be '/', '.', '..', or contain line breaks" >&2
    return 1
  }
  PRIVATE_SCAN_LITERALS+=("$literal")
}

append_private_identity() {
  local literal
  literal="$(trim_private_item "${1:-}")"
  local lowered="${literal,,}"
  [[ ${#literal} -ge 4 ]] || return 0
  case "$lowered" in root|user|admin|ubuntu|nvidia|runner|build|codex) return 0 ;; esac
  append_private_literal "$literal"
}

append_configured_private_identity() {
  local literal lowered
  literal="$(trim_private_item "${1:-}")"
  [[ -n "$literal" ]] || return 0
  lowered="${literal,,}"
  if [[ ${#literal} -lt 4 ]] || [[ "$lowered" =~ ^(root|user|admin|ubuntu|nvidia|runner|build|codex)$ ]]; then
    echo "Configured private usernames must be at least four characters and may not be generic identities" >&2
    return 1
  fi
  append_private_literal "$literal"
}

validate_private_list() {
  local label="$1" value="${2:-}"
  if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "$label may not contain line breaks" >&2
    return 1
  fi
}

sort_private_literals_longest_first() {
  local candidate existing duplicate index inserted
  local -a sorted=()
  for candidate in "${PRIVATE_SCAN_LITERALS[@]}"; do
    duplicate=0
    for existing in "${sorted[@]}"; do
      if [[ "$candidate" == "$existing" ]]; then duplicate=1; break; fi
    done
    (( duplicate == 0 )) || continue
    inserted=0
    for ((index=0; index<${#sorted[@]}; index++)); do
      if (( ${#candidate} > ${#sorted[index]} )); then
        sorted=("${sorted[@]:0:index}" "$candidate" "${sorted[@]:index}")
        inserted=1
        break
      fi
    done
    (( inserted == 1 )) || sorted+=("$candidate")
  done
  PRIVATE_SCAN_LITERALS=("${sorted[@]}")
}

build_private_literal_set() {
  PRIVATE_SCAN_LITERALS=()
  local short_host fqdn_host current_user remote_user item
  local -a values=()
  short_host="$(hostname 2>/dev/null || true)"
  fqdn_host="$(hostname -f 2>/dev/null || true)"
  current_user="$(id -un 2>/dev/null || true)"
  remote_user=""
  if [[ "${REMOTE_HOST:-}" == *@* ]]; then remote_user="${REMOTE_HOST%@*}"; fi

  if [[ "$PRIVATE_ENV_LOADED" == "1" ]]; then
    append_private_literal "$fqdn_host" || return 1
    append_private_literal "$short_host" || return 1
    append_private_literal "${HOME:-}" || return 1
    append_private_identity "$current_user" || return 1
  fi
  append_private_literal "${REMOTE_NODE_HOSTNAME:-}" || return 1
  append_private_literal "${REMOTE_HOST:-}" || return 1
  append_private_literal "${REMOTE_REPO_ROOT:-}" || return 1
  append_private_literal "${PEER_MGMT_IP:-}" || return 1
  append_private_literal "${LOCAL_DATA_IP:-}" || return 1
  append_private_literal "${PEER_DATA_IP:-}" || return 1
  append_private_literal "${PRIVATE_REGISTRY_PREFIX:-}" || return 1
  append_private_literal "${PRIVATE_MODEL_ID:-}" || return 1
  append_private_identity "$remote_user" || return 1

  validate_private_list PRIVATE_HOSTNAMES "${PRIVATE_HOSTNAMES:-}" || return 1
  validate_private_list PRIVATE_USERNAMES "${PRIVATE_USERNAMES:-}" || return 1
  validate_private_list PRIVATE_PATH_PREFIXES "${PRIVATE_PATH_PREFIXES:-}" || return 1
  validate_private_list PRIVATE_LITERALS "${PRIVATE_LITERALS:-}" || return 1

  IFS=',' read -r -a values <<<"${PRIVATE_HOSTNAMES:-}"
  for item in "${values[@]}"; do append_private_literal "$item" || return 1; done
  IFS=',' read -r -a values <<<"${PRIVATE_USERNAMES:-}"
  for item in "${values[@]}"; do append_configured_private_identity "$item" || return 1; done
  IFS=',' read -r -a values <<<"${PRIVATE_PATH_PREFIXES:-}"
  for item in "${values[@]}"; do append_private_literal "$item" || return 1; done
  IFS=',' read -r -a values <<<"${PRIVATE_LITERALS:-}"
  for item in "${values[@]}"; do append_private_literal "$item" || return 1; done
  sort_private_literals_longest_first
}

sanitize_tree() {
  local root="$1"
  local short_host fqdn_host current_user remote_user item replacement
  short_host="$(hostname 2>/dev/null || true)"
  fqdn_host="$(hostname -f 2>/dev/null || true)"
  current_user="$(id -un 2>/dev/null || true)"
  remote_user=""
  if [[ "${REMOTE_HOST:-}" == *@* ]]; then remote_user="${REMOTE_HOST%@*}"; fi
  build_private_literal_set || return 1

  # Always replace longer literals first. This prevents a short hostname or
  # home directory from exposing the suffix of an overlapping FQDN/path.
  for item in "${PRIVATE_SCAN_LITERALS[@]}"; do
    replacement="<PRIVATE_LITERAL>"
    if [[ -n "$fqdn_host" && "$item" == "$fqdn_host" ]] ||
       [[ -n "$short_host" && "$item" == "$short_host" ]]; then
      replacement="${NODE_LABEL:-<HOSTNAME>}"
    elif [[ -n "${REMOTE_NODE_HOSTNAME:-}" && "$item" == "$REMOTE_NODE_HOSTNAME" ]]; then
      replacement="${REMOTE_LABEL:-<REMOTE_HOSTNAME>}"
    elif [[ -n "${REMOTE_REPO_ROOT:-}" && "$item" == "$REMOTE_REPO_ROOT" ]]; then
      replacement="<REMOTE_REPO_ROOT>"
    elif [[ -n "${HOME:-}" && "$item" == "$HOME" ]]; then
      replacement="<HOME>"
    elif [[ -n "${REMOTE_HOST:-}" && "$item" == "$REMOTE_HOST" ]]; then
      replacement="<REMOTE_HOST>"
    elif [[ -n "${PEER_MGMT_IP:-}" && "$item" == "$PEER_MGMT_IP" ]]; then
      replacement="<PEER_MGMT_IP>"
    elif [[ -n "${LOCAL_DATA_IP:-}" && "$item" == "$LOCAL_DATA_IP" ]]; then
      replacement="<LOCAL_DATA_IP>"
    elif [[ -n "${PEER_DATA_IP:-}" && "$item" == "$PEER_DATA_IP" ]]; then
      replacement="<PEER_DATA_IP>"
    elif [[ -n "${PRIVATE_REGISTRY_PREFIX:-}" && "$item" == "$PRIVATE_REGISTRY_PREFIX" ]]; then
      replacement="<PRIVATE_REGISTRY>"
    elif [[ -n "${PRIVATE_MODEL_ID:-}" && "$item" == "$PRIVATE_MODEL_ID" ]]; then
      replacement="<PRIVATE_MODEL>"
    elif [[ -n "$current_user" && "$item" == "$current_user" ]]; then
      replacement="<USERNAME>"
    elif [[ -n "$remote_user" && "$item" == "$remote_user" ]]; then
      replacement="<REMOTE_USERNAME>"
    fi
    literal_replace_tree "$root" "$item" "$replacement"
  done

  # Validate candidates with inet_pton. Boundaries preserve dotted library
  # versions (for example libmlx5.so.1.24.50.0), PCI BDFs, and timestamps.
  while IFS= read -r -d '' item; do
    perl -MSocket=AF_INET,AF_INET6,inet_pton -pi -e '
      s{(\b(?:GID\s+\d+|NET/\d+-\d+)\s+\([^/\r\n]+/)[0-9A-Fa-f]+}{$1<RDMA_GUID>}gi;
      s{(^[ \t]*roce[A-Za-z0-9_.-]+[ \t]+)[0-9A-Fa-f]{16}[ \t]*$}{$1<RDMA_GUID>}gmi;
      s{(?<![A-Za-z0-9_.-])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![A-Za-z0-9_.-])}{<MAC>}g;
      s{(?<![A-Za-z0-9_.-])((?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?)(?![A-Za-z0-9_.-])}{
        my $candidate=$1; (my $address=$candidate)=~s{/\d{1,2}$}{};
        my $safe=($address eq "0.0.0.0" || $address =~ /^127\./ || $address =~ /^192\.0\.2\./ ||
          $address =~ /^198\.51\.100\./ || $address =~ /^203\.0\.113\./);
        defined(inet_pton(AF_INET, $address)) && !$safe ? "<IPV4>" : $candidate;
      }ge;
      s{(?<![A-Za-z0-9_.-])([0-9A-Fa-f:]*:[0-9A-Fa-f:]+(?:%[A-Za-z0-9_.-]+)?(?:/\d{1,3})?)(?![A-Za-z0-9_.-])}{
        my $candidate=$1; (my $address=$candidate)=~s{/\d{1,3}$}{}; $address=~s{%[A-Za-z0-9_.-]+$}{};
        my $safe=($address eq "::" || $address eq "::1" || $address =~ /^2001:0*db8(?::|$)/i);
        defined(inet_pton(AF_INET6, $address)) && !$safe ? "<IPV6>" : $candidate;
      }ge;
    ' "$item"
  done < <(find "$root" -type f -print0)
}

unsafe_public_path() {
  local path="${1,,}" base=""
  base="${path##*/}"
  case "$path" in
    *.private.md|.docker/*|*/.docker/*) return 0 ;;
  esac
  case "$base" in
    .env|.env.*|id_rsa|id_dsa|id_ecdsa|id_ed25519|*.pem|*.key|known_hosts|authorized_keys|.netrc|.npmrc|.pypirc|credentials|credentials.json|auth.json|docker-config.json) return 0 ;;
  esac
  return 1
}

reject_unsafe_tree() {
  local root="$1" item relative
  if IFS= read -r -d '' item < <(find "$root" -mindepth 1 ! -type f ! -type d -print0 -quit); then
    echo "Publication input contains a symlink or special file" >&2
    return 1
  fi
  while IFS= read -r -d '' item; do
    relative="${item#"$root"/}"
    if [[ "$relative" == *$'\n'* || "$relative" == *$'\r'* ]] || unsafe_public_path "$relative"; then
      echo "Publication input contains a forbidden or unsafe path" >&2
      return 1
    fi
    if [[ -f "$item" && -s "$item" ]] && ! LC_ALL=C grep -Iq '' "$item"; then
      echo "Publication input contains a binary file" >&2
      return 1
    fi
  done < <(find "$root" -mindepth 1 -print0)
}

verify_manifest_tree() {
  local root="$1" manifest found=0 computed file cursor covered
  while IFS= read -r -d '' manifest; do
    found=1
    if ! (cd "$(dirname "$manifest")" && sha256sum -c "$(basename "$manifest")" >/dev/null); then
      echo "Private evidence manifest validation failed" >&2
      return 1
    fi
    computed="$(mktemp)"
    (cd "$(dirname "$manifest")" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum) >"$computed"
    if ! cmp -s "$manifest" "$computed"; then
      rm -f "$computed"
      echo "Private evidence manifest does not cover its exact file set" >&2
      return 1
    fi
    rm -f "$computed"
  done < <(find "$root" -type f -name SHA256SUMS -print0)
  if (( found == 0 )); then
    echo "Private evidence contains no SHA256SUMS manifests" >&2
    return 1
  fi
  while IFS= read -r -d '' file; do
    cursor="$(dirname "$file")"
    covered=0
    while [[ "$cursor" == "$root" || "$cursor" == "$root/"* ]]; do
      if [[ -f "$cursor/SHA256SUMS" ]]; then covered=1; break; fi
      [[ "$cursor" == "$root" ]] && break
      cursor="$(dirname "$cursor")"
    done
    if (( covered == 0 )); then
      echo "Private evidence contains a file outside every manifest" >&2
      return 1
    fi
  done < <(find "$root" -type f ! -name SHA256SUMS -print0)
}

SECRET_PATTERN='(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|Authorization[[:space:]]*[:=][[:space:]]*(Basic|Bearer)[[:space:]]+[A-Za-z0-9._~+/-]{12,}|Bearer[[:space:]]+[A-Za-z0-9._~+/-]{16,}|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|https?://[^/@[:space:]]+:[^/@[:space:]]+@|(^|[^A-Za-z0-9_])(password|passwd|token|secret|api[_-]?key|aws_secret_access_key|auth|docker_auth_config|identitytoken|registrytoken)[^A-Za-z0-9_]*[:=][[:space:]]*[^[:space:],}]{8,})'

secret_scan() {
  local root="$1" report="$2"
  local matches rc=0 count=0 path_matches=0 item relative
  matches="$(mktemp)"
  if grep -RIlEi -e "$SECRET_PATTERN" -- "$root" >"$matches" 2>/dev/null; then rc=0; else rc=$?; fi
  if (( rc > 1 )); then
    printf 'SECRET_MATCHED_FILES=0\nSECRET_MATCHED_PATHS=0\nSCAN_ERRORS=1\nRESULT=ERROR\n' >"$report"
    rm -f "$matches"
    return 1
  fi
  count="$(wc -l <"$matches")"
  rm -f "$matches"
  while IFS= read -r -d '' item; do
    relative="${item#"$root"/}"
    if printf '%s\n' "$relative" | grep -Eiq -e "$SECRET_PATTERN"; then
      path_matches=$((path_matches+1))
    fi
  done < <(find "$root" -mindepth 1 -print0)
  if (( count > 0 || path_matches > 0 )); then
    printf 'SECRET_MATCHED_FILES=%s\nSECRET_MATCHED_PATHS=%s\nSCAN_ERRORS=0\nRESULT=REVIEW_REQUIRED\n' \
      "$count" "$path_matches" >"$report"
    return 1
  fi
  printf 'SECRET_MATCHED_FILES=0\nSECRET_MATCHED_PATHS=0\nSCAN_ERRORS=0\nRESULT=PASS_WITH_MANUAL_REVIEW\n' >"$report"
}

count_network_identifiers() {
  local file="$1"
  perl -MSocket=AF_INET,AF_INET6,inet_pton -ne '
    while (/(?<![A-Za-z0-9_.-])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![A-Za-z0-9_.-])/g) { $count++ }
    while (/(?<![A-Za-z0-9_.-])((?:\d{1,3}\.){3}\d{1,3}(?:\/\d{1,2})?)(?![A-Za-z0-9_.-])/g) {
      $candidate=$1; $candidate=~s{/\d{1,2}$}{};
      $safe=($candidate eq "0.0.0.0" || $candidate =~ /^127\./ || $candidate =~ /^192\.0\.2\./ ||
        $candidate =~ /^198\.51\.100\./ || $candidate =~ /^203\.0\.113\./);
      $count++ if defined(inet_pton(AF_INET, $candidate)) && !$safe;
    }
    while (/(?<![A-Za-z0-9_.-])([0-9A-Fa-f:]*:[0-9A-Fa-f:]+(?:%[A-Za-z0-9_.-]+)?(?:\/\d{1,3})?)(?![A-Za-z0-9_.-])/g) {
      $candidate=$1; $candidate=~s{/\d{1,3}$}{}; $candidate=~s{%[A-Za-z0-9_.-]+$}{};
      $safe=($candidate eq "::" || $candidate eq "::1" || $candidate =~ /^2001:0*db8(?::|$)/i);
      $count++ if defined(inet_pton(AF_INET6, $candidate)) && !$safe;
    }
    END { print(($count // 0), "\n") }
  ' "$file"
}

count_hardware_identifiers() {
  local file="$1"
  perl -ne '
    while (/(\b(?:GID\s+\d+|NET\/\d+-\d+)\s+\([^\/\r\n]+\/)[0-9A-Fa-f]+/gi) { $count++ }
    while (/^[ \t]*roce[A-Za-z0-9_.-]+[ \t]+[0-9A-Fa-f]{16}[ \t]*$/gmi) { $count++ }
    END { print(($count // 0), "\n") }
  ' "$file"
}

privacy_scan() {
  local root="$1" report="$2" literal item relative matches rc count
  local literal_matches=0 network_matches=0 hardware_matches=0 scan_errors=0
  build_private_literal_set || return 1
  for literal in "${PRIVATE_SCAN_LITERALS[@]}"; do
    matches="$(mktemp)"
    if grep -RIlF -e "$literal" -- "$root" >"$matches" 2>/dev/null; then rc=0; else rc=$?; fi
    if (( rc > 1 )); then
      scan_errors=$((scan_errors+1))
    else
      count="$(wc -l <"$matches")"
      literal_matches=$((literal_matches+count))
    fi
    rm -f "$matches"
    while IFS= read -r -d '' item; do
      relative="${item#"$root"/}"
      [[ "$relative" == *"$literal"* ]] && literal_matches=$((literal_matches+1))
    done < <(find "$root" -mindepth 1 -print0)
  done
  while IFS= read -r -d '' item; do
    count="$(count_network_identifiers "$item")" || { scan_errors=$((scan_errors+1)); continue; }
    network_matches=$((network_matches+count))
    count="$(count_hardware_identifiers "$item")" || { scan_errors=$((scan_errors+1)); continue; }
    hardware_matches=$((hardware_matches+count))
  done < <(find "$root" -type f -print0)
  while IFS= read -r -d '' item; do
    relative="${item#"$root"/}"
    count="$(printf '%s\n' "$relative" | count_network_identifiers /dev/stdin)" || {
      scan_errors=$((scan_errors+1))
      continue
    }
    network_matches=$((network_matches+count))
  done < <(find "$root" -mindepth 1 -print0)
  printf 'UNRESOLVED_CONFIGURED_LITERALS=%s\nUNREDACTED_NETWORK_IDENTIFIERS=%s\nUNREDACTED_RDMA_GUIDS=%s\nSCAN_ERRORS=%s\n' \
    "$literal_matches" "$network_matches" "$hardware_matches" "$scan_errors" >"$report"
  if (( literal_matches > 0 || network_matches > 0 || hardware_matches > 0 || scan_errors > 0 )); then
    printf 'RESULT=REVIEW_REQUIRED\n' >>"$report"
    return 1
  fi
  printf 'RESULT=PASS_WITH_MANUAL_REVIEW\n' >>"$report"
}

tracked_repo_scan() {
  local report="$1" path lower mode literal matches rc count blob
  local forbidden=0 unsafe_types=0 secret_paths=0 network_paths=0 scan_errors=0
  local binaries=0 secrets=0 private_literals=0 network_ids=0 hardware_ids=0
  local index_binaries=0 index_secrets=0 index_private_literals=0 index_network_ids=0 index_hardware_ids=0
  if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'RESULT=ERROR_NOT_A_GIT_WORKTREE\n' >"$report"
    return 1
  fi
  while IFS= read -r -d '' path; do
    lower="${path,,}"
    case "$lower" in
      artifacts/m0-private/*|deployments/bootstrap/out/*|helper/*|*.private.md|.env.m0.local|benchmarks/raw-results/m0-platform-qualification/.*.staging.*/*|benchmarks/raw-results/m0-platform-qualification/.*.previous.*/*) forbidden=$((forbidden+1)) ;;
    esac
    unsafe_public_path "$lower" && forbidden=$((forbidden+1))
    if printf '%s\n' "$path" | grep -Eiq -e "$SECRET_PATTERN"; then secret_paths=$((secret_paths+1)); fi
    count="$(printf '%s\n' "$path" | count_network_identifiers /dev/stdin)" || {
      scan_errors=$((scan_errors+1))
      count=0
    }
    network_paths=$((network_paths+count))
    mode="$(git -C "$REPO_ROOT" ls-files -s -- "$path" | awk 'NR==1 {print $1}')"
    [[ "$mode" == "120000" || "$mode" == "160000" ]] && unsafe_types=$((unsafe_types+1))
    if [[ -f "$REPO_ROOT/$path" ]]; then
      if [[ -s "$REPO_ROOT/$path" ]] && ! LC_ALL=C grep -Iq '' "$REPO_ROOT/$path"; then
        binaries=$((binaries+1))
      else
        count="$(count_network_identifiers "$REPO_ROOT/$path")" || { scan_errors=$((scan_errors+1)); count=0; }
        network_ids=$((network_ids+count))
        count="$(count_hardware_identifiers "$REPO_ROOT/$path")" || { scan_errors=$((scan_errors+1)); count=0; }
        hardware_ids=$((hardware_ids+count))
      fi
    fi
    if [[ "$mode" != "160000" ]]; then
      blob="$(mktemp)"
      if git -C "$REPO_ROOT" cat-file blob ":$path" >"$blob" 2>/dev/null; then
        if [[ -s "$blob" ]] && ! LC_ALL=C grep -Iq '' "$blob"; then
          index_binaries=$((index_binaries+1))
        else
          count="$(count_network_identifiers "$blob")" || { scan_errors=$((scan_errors+1)); count=0; }
          index_network_ids=$((index_network_ids+count))
          count="$(count_hardware_identifiers "$blob")" || { scan_errors=$((scan_errors+1)); count=0; }
          index_hardware_ids=$((index_hardware_ids+count))
        fi
      else
        scan_errors=$((scan_errors+1))
      fi
      rm -f "$blob"
    fi
  done < <(git -C "$REPO_ROOT" ls-files -z)

  matches="$(mktemp)"
  if git -C "$REPO_ROOT" grep -IlEi -e "$SECRET_PATTERN" -- . >"$matches" 2>/dev/null; then rc=0; else rc=$?; fi
  if (( rc > 1 )); then scan_errors=$((scan_errors+1)); else secrets="$(wc -l <"$matches")"; fi
  rm -f "$matches"

  matches="$(mktemp)"
  if git -C "$REPO_ROOT" grep --cached -IlEi -e "$SECRET_PATTERN" -- . >"$matches" 2>/dev/null; then rc=0; else rc=$?; fi
  if (( rc > 1 )); then scan_errors=$((scan_errors+1)); else index_secrets="$(wc -l <"$matches")"; fi
  rm -f "$matches"

  build_private_literal_set || return 1
  for literal in "${PRIVATE_SCAN_LITERALS[@]}"; do
    matches="$(mktemp)"
    if git -C "$REPO_ROOT" grep -IlF -e "$literal" -- . >"$matches" 2>/dev/null; then rc=0; else rc=$?; fi
    if (( rc > 1 )); then
      scan_errors=$((scan_errors+1))
    else
      count="$(wc -l <"$matches")"
      private_literals=$((private_literals+count))
    fi
    rm -f "$matches"

    matches="$(mktemp)"
    if git -C "$REPO_ROOT" grep --cached -IlF -e "$literal" -- . >"$matches" 2>/dev/null; then rc=0; else rc=$?; fi
    if (( rc > 1 )); then
      scan_errors=$((scan_errors+1))
    else
      count="$(wc -l <"$matches")"
      index_private_literals=$((index_private_literals+count))
    fi
    rm -f "$matches"
    while IFS= read -r -d '' path; do
      if [[ "$path" == *"$literal"* ]]; then
        private_literals=$((private_literals+1))
        index_private_literals=$((index_private_literals+1))
      fi
    done < <(git -C "$REPO_ROOT" ls-files -z)
  done

  printf 'TRACKED_FORBIDDEN_PATHS=%s\nTRACKED_SYMLINKS_OR_SUBMODULES=%s\nTRACKED_BINARIES=%s\nTRACKED_SECRET_MATCHED_FILES=%s\nTRACKED_SECRET_MATCHED_PATHS=%s\nTRACKED_PRIVATE_LITERAL_MATCHES=%s\nTRACKED_NETWORK_IDENTIFIERS_IN_PATHS=%s\nTRACKED_PRIVATE_NETWORK_IDENTIFIERS=%s\nTRACKED_RDMA_GUIDS=%s\nINDEX_BINARIES=%s\nINDEX_SECRET_MATCHED_FILES=%s\nINDEX_SECRET_MATCHED_PATHS=%s\nINDEX_PRIVATE_LITERAL_MATCHES=%s\nINDEX_PRIVATE_NETWORK_IDENTIFIERS=%s\nINDEX_RDMA_GUIDS=%s\nSCAN_ERRORS=%s\n' \
    "$forbidden" "$unsafe_types" "$binaries" "$secrets" "$secret_paths" "$private_literals" "$network_paths" "$network_ids" "$hardware_ids" \
    "$index_binaries" "$index_secrets" "$secret_paths" "$index_private_literals" "$index_network_ids" "$index_hardware_ids" "$scan_errors" >"$report"
  if (( forbidden > 0 || unsafe_types > 0 || binaries > 0 || secrets > 0 || secret_paths > 0 || private_literals > 0 || network_paths > 0 || network_ids > 0 || hardware_ids > 0 ||
        index_binaries > 0 || index_secrets > 0 || index_private_literals > 0 || index_network_ids > 0 || index_hardware_ids > 0 || scan_errors > 0 )); then
    printf 'RESULT=REVIEW_REQUIRED\n' >>"$report"
    return 1
  fi
  printf 'RESULT=PASS_WITH_MANUAL_REVIEW\n' >>"$report"
}

generate_public_manifest() {
  local root="$1"
  (cd "$root" && find . -type f ! -name SHA256SUMS ! -path ./PUBLICATION-CHECKLIST.md -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS)
}

verify_public_manifest() {
  local root="$1" computed
  [[ -f "$root/SHA256SUMS" ]] || { echo "Missing public SHA256SUMS" >&2; return 1; }
  (cd "$root" && sha256sum -c SHA256SUMS >/dev/null) || {
    echo "Public evidence checksum validation failed" >&2
    return 1
  }
  computed="$(mktemp)"
  (cd "$root" && find . -type f ! -name SHA256SUMS ! -path ./PUBLICATION-CHECKLIST.md -print0 | sort -z | xargs -0 sha256sum) >"$computed"
  if ! cmp -s "$root/SHA256SUMS" "$computed"; then
    rm -f "$computed"
    echo "Public manifest does not cover the exact sealed file set" >&2
    return 1
  fi
  rm -f "$computed"
}

publish_run() (
  local requested_run="${1:-$RUN_ID}"
  local source="$REPO_ROOT/$PRIVATE_EVIDENCE_ROOT/$requested_run"
  local target="$REPO_ROOT/$PUBLIC_EVIDENCE_ROOT/$requested_run"
  local parent staging reports backup=""
  validate_component RUN_ID "$requested_run" || exit 2
  [[ -d "$source" ]] || { echo "Private run not found: $source" >&2; exit 4; }
  [[ ! -L "$source" && ! -L "$target" ]] || { echo "Evidence roots may not be symlinks" >&2; exit 4; }
  reject_unsafe_tree "$source" || exit 5
  verify_manifest_tree "$source" || exit 5

  parent="$(dirname "$target")"
  mkdir -p "$parent"
  staging="$(mktemp -d "$parent/.${requested_run}.staging.XXXXXX")"
  reports="$(mktemp -d)"
  cleanup_publish() {
    [[ -n "${staging:-}" && -d "$staging" ]] && rm -rf -- "$staging"
    [[ -n "${reports:-}" && -d "$reports" ]] && rm -rf -- "$reports"
  }
  trap cleanup_publish EXIT

  cp -a "$source/." "$staging/"
  find "$staging" -name SHA256SUMS -type f -delete
  reject_unsafe_tree "$staging" || exit 5
  sanitize_tree "$staging"
  if ! privacy_scan "$staging" "$reports/privacy-scan.txt"; then
    echo "Privacy scan requires review; the previous public export was preserved" >&2
    exit 5
  fi
  if ! secret_scan "$staging" "$reports/publication-scan.txt"; then
    echo "Secret scan requires review; the previous public export was preserved" >&2
    exit 5
  fi
  if ! tracked_repo_scan "$reports/repo-publication-scan.txt"; then
    echo "Tracked repository publication gate failed; the previous public export was preserved" >&2
    exit 5
  fi
  cp "$reports/privacy-scan.txt" "$staging/privacy-scan.txt"
  cp "$reports/publication-scan.txt" "$staging/publication-scan.txt"
  cp "$reports/repo-publication-scan.txt" "$staging/repo-publication-scan.txt"
  cat >"$staging/PUBLICATION-CHECKLIST.md" <<'CHECKLIST'
# Publication Checklist

- [ ] No `.env.m0.local`, credentials, tokens, SSH keys, or Docker auth files are present.
- [ ] No tracked private/local content or interrupted publisher staging/backup directory is present.
- [ ] No binary file is present in the evidence export or tracked repository.
- [ ] Hostnames/FQDNs are replaced with stable labels such as `spark-a` and `spark-b`.
- [ ] Management/data IP addresses, subnets, gateways, and SSH endpoints are redacted.
- [ ] MAC addresses are redacted.
- [ ] RDMA node GUIDs and compact NCCL GID/GUID fragments are redacted.
- [ ] Usernames and private home/mount paths are redacted.
- [ ] Private registry, model repository, and organization names are redacted where required.
- [ ] Command lines do not contain inline tokens or passwords.
- [ ] Image digests, driver/CUDA versions, interface names, test parameters, exit codes, and benchmark values remain intact.
- [ ] No retained failure is relabeled as success; any deliberately excluded run is documented.
- [ ] `publication-scan.txt` has been reviewed manually even when it reports PASS.
- [ ] `privacy-scan.txt` and `repo-publication-scan.txt` have been reviewed manually.
CHECKLIST
  generate_public_manifest "$staging"
  verify_public_manifest "$staging"

  if [[ -e "$target" ]]; then
    backup="$parent/.${requested_run}.previous.$$"
    [[ ! -e "$backup" ]] || { echo "Unexpected publication backup collision" >&2; exit 5; }
    mv "$target" "$backup"
  fi
  if mv "$staging" "$target"; then
    staging=""
    [[ -z "$backup" ]] || rm -rf -- "$backup"
  else
    [[ -z "$backup" || -e "$target" ]] || mv "$backup" "$target"
    exit 5
  fi
  echo "Sanitized export ready: $target"
)

verify_public() (
  local requested_run="${1:-}" report_dir checked_items
  [[ -n "$requested_run" ]] || { echo "verify-public requires an explicit RUN_ID" >&2; exit 2; }
  validate_component RUN_ID "$requested_run" || exit 2
  local target="$REPO_ROOT/$PUBLIC_EVIDENCE_ROOT/$requested_run"
  [[ -d "$target" && ! -L "$target" ]] || { echo "Public run not found or is a symlink: $target" >&2; exit 4; }
  reject_unsafe_tree "$target" || exit 5
  verify_public_manifest "$target" || exit 5
  report_dir="$(mktemp -d)"
  cleanup_verify() { rm -rf -- "$report_dir"; }
  trap cleanup_verify EXIT
  secret_scan "$target" "$report_dir/publication-scan.txt" || exit 5
  privacy_scan "$target" "$report_dir/privacy-scan.txt" || exit 5
  tracked_repo_scan "$report_dir/repo-publication-scan.txt" || exit 5
  [[ -f "$target/PUBLICATION-CHECKLIST.md" ]] || { echo "Missing publication checklist" >&2; exit 5; }
  if grep -q '^- \[ \]' "$target/PUBLICATION-CHECKLIST.md"; then
    echo "Publication checklist still has unchecked items" >&2
    exit 5
  fi
  checked_items="$(grep -Ec '^- \[[xX]\] ' "$target/PUBLICATION-CHECKLIST.md" || true)"
  [[ "$checked_items" -eq 14 ]] || {
    echo "Publication checklist is incomplete or has an unexpected shape" >&2
    exit 5
  }
  echo "Public evidence verified without modifying it: $target"
)

case "$cmd" in
  node)
    collect_node
    ;;
  test)
    (($# >= 4)) || { usage; exit 2; }
    shift
    name="$1"; shift
    capture_test "$name" "$@"
    ;;
  tcp)
    capture_tcp
    ;;
  distributed)
    (($# >= 4)) || { usage; exit 2; }
    shift
    name="$1"; shift
    capture_distributed "$name" "$@"
    ;;
  pull-remote)
    pull_remote "${2:-$RUN_ID}"
    ;;
  publish)
    publish_run "${2:-$RUN_ID}"
    ;;
  verify-public)
    verify_public "${2:-}"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 2
    ;;
esac
