#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./run-network-test.sh \
    --test-id single-forward \
    --local-iface enp1s0f1np1 \
    --local-ip 192.0.2.1 \
    --remote-host spark-b \
    --remote-iface enp1s0f1np1 \
    --remote-ip 192.0.2.2 \
    [--streams 1] [--duration 30] [--omit 5] [--reverse]

Requirements:
  Local:  bash, ssh, iperf3, ethtool, ip, nstat, python3
  Remote: bash, sshd, iperf3, ethtool, ip, nstat

Assumptions:
  - SSH key authentication works from the local node to --remote-host.
  - The selected data IPs are already configured.
  - The remote user can run ethtool without sudo.
EOF
}

TEST_ID=""
LOCAL_IFACE=""
LOCAL_IP=""
REMOTE_HOST=""
REMOTE_IFACE=""
REMOTE_IP=""
STREAMS=1
DURATION=30
OMIT=5
REVERSE=0
RESULTS_ROOT="${RESULTS_ROOT:-../results/network}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --test-id)       TEST_ID="$2"; shift 2 ;;
    --local-iface)   LOCAL_IFACE="$2"; shift 2 ;;
    --local-ip)      LOCAL_IP="$2"; shift 2 ;;
    --remote-host)   REMOTE_HOST="$2"; shift 2 ;;
    --remote-iface)  REMOTE_IFACE="$2"; shift 2 ;;
    --remote-ip)     REMOTE_IP="$2"; shift 2 ;;
    --streams)       STREAMS="$2"; shift 2 ;;
    --duration)      DURATION="$2"; shift 2 ;;
    --omit)          OMIT="$2"; shift 2 ;;
    --reverse)       REVERSE=1; shift ;;
    --results-root)  RESULTS_ROOT="$2"; shift 2 ;;
    -h|--help)       usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

for value in TEST_ID LOCAL_IFACE LOCAL_IP REMOTE_HOST REMOTE_IFACE REMOTE_IP; do
  [[ -n "${!value}" ]] || { echo "Missing required argument: $value" >&2; usage; exit 2; }
done

for cmd in ssh iperf3 ethtool ip nstat python3 awk sort sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing local command: $cmd" >&2
    exit 1
  }
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SUMMARIZER="${SCRIPT_DIR}/summarize-network-test.py"
[[ -f "$SUMMARIZER" ]] || {
  echo "Missing summarizer: $SUMMARIZER" >&2
  exit 1
}

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${RESULTS_ROOT}/${TIMESTAMP}-${TEST_ID}"
mkdir -p "$RUN_DIR"/{local,remote}

SSH_OPTS=(
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=3
)

cleanup() {
  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "pkill -f 'iperf3 -s -1' >/dev/null 2>&1 || true" \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT

capture_ethtool_stats_local() {
  local output="$1"
  ethtool -S "$LOCAL_IFACE" 2>&1 |
    awk '
      /^[[:space:]]*[A-Za-z0-9_]+:/ {
        key=$1
        sub(/:$/, "", key)
        print key, $2
      }
    ' | sort > "$output"
}

capture_ethtool_stats_remote() {
  local output="$1"
  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "ethtool -S '$REMOTE_IFACE' 2>&1 |
     awk '/^[[:space:]]*[A-Za-z0-9_]+:/ {
       key=\$1
       sub(/:$/, \"\", key)
       print key, \$2
     }' | sort" > "$output"
}

capture_local() {
  local phase="$1"
  local dir="$RUN_DIR/local"

  date -u --iso-8601=seconds > "$dir/${phase}-timestamp.txt"
  hostnamectl > "$dir/${phase}-hostnamectl.txt" 2>&1 || true
  ip -brief address show dev "$LOCAL_IFACE" > "$dir/${phase}-address.txt" 2>&1
  ip -details link show dev "$LOCAL_IFACE" > "$dir/${phase}-link.txt" 2>&1
  ip -s link show dev "$LOCAL_IFACE" > "$dir/${phase}-ip-link-stats.txt" 2>&1
  ip route get "$REMOTE_IP" > "$dir/${phase}-route.txt" 2>&1
  ethtool "$LOCAL_IFACE" > "$dir/${phase}-ethtool-link.txt" 2>&1
  nstat -az > "$dir/${phase}-nstat.txt" 2>&1
  capture_ethtool_stats_local "$dir/${phase}-ethtool.stats"
}

capture_remote() {
  local phase="$1"
  local dir="$RUN_DIR/remote"

  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "date -u --iso-8601=seconds" > "$dir/${phase}-timestamp.txt"

  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "hostnamectl" > "$dir/${phase}-hostnamectl.txt" 2>&1 || true

  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "ip -brief address show dev '$REMOTE_IFACE'" \
    > "$dir/${phase}-address.txt" 2>&1

  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "ip -details link show dev '$REMOTE_IFACE'" \
    > "$dir/${phase}-link.txt" 2>&1

  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "ip -s link show dev '$REMOTE_IFACE'" \
    > "$dir/${phase}-ip-link-stats.txt" 2>&1

  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "ip route get '$LOCAL_IP'" \
    > "$dir/${phase}-route.txt" 2>&1

  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "ethtool '$REMOTE_IFACE'" \
    > "$dir/${phase}-ethtool-link.txt" 2>&1

  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
    "nstat -az" > "$dir/${phase}-nstat.txt" 2>&1

  capture_ethtool_stats_remote "$dir/${phase}-ethtool.stats"
}

cat > "$RUN_DIR/metadata.env" <<EOF
TEST_ID=$TEST_ID
TIMESTAMP_UTC=$TIMESTAMP
LOCAL_HOST=$(hostname)
LOCAL_IFACE=$LOCAL_IFACE
LOCAL_IP=$LOCAL_IP
REMOTE_HOST=$REMOTE_HOST
REMOTE_IFACE=$REMOTE_IFACE
REMOTE_IP=$REMOTE_IP
STREAMS=$STREAMS
DURATION_SECONDS=$DURATION
OMIT_SECONDS=$OMIT
REVERSE=$REVERSE
EOF

{
  printf 'iperf3 -c %q -B %q -P %q -t %q -O %q --get-server-output --json' \
    "$REMOTE_IP" "$LOCAL_IP" "$STREAMS" "$DURATION" "$OMIT"
  [[ "$REVERSE" -eq 1 ]] && printf ' -R'
  printf '\n'
} > "$RUN_DIR/command.txt"

echo "[1/6] Validating SSH and route"
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "true"
ip route get "$REMOTE_IP" | tee "$RUN_DIR/local/route-validation.txt"
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
  "ip route get '$LOCAL_IP'" | tee "$RUN_DIR/remote/route-validation.txt"

echo "[2/6] Capturing before-state on both nodes"
capture_local before
capture_remote before

echo "[3/6] Starting one-shot iperf3 server on $REMOTE_HOST"
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
  "nohup iperf3 -s -1 > /tmp/iperf3-${TEST_ID}.server.log 2>&1 &"
sleep 2

echo "[4/6] Running iperf3 test"
IPERF_ARGS=(
  -c "$REMOTE_IP"
  -B "$LOCAL_IP"
  -P "$STREAMS"
  -t "$DURATION"
  -O "$OMIT"
  --get-server-output
  --json
)

if [[ "$REVERSE" -eq 1 ]]; then
  IPERF_ARGS+=(-R)
fi

set +e
iperf3 "${IPERF_ARGS[@]}" > "$RUN_DIR/iperf3.json" 2> "$RUN_DIR/iperf3.stderr"
IPERF_EXIT=$?
set -e

echo "$IPERF_EXIT" > "$RUN_DIR/iperf3.exit-code"

ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" \
  "cat /tmp/iperf3-${TEST_ID}.server.log 2>/dev/null || true" \
  > "$RUN_DIR/remote/iperf3-server.log"

echo "[5/6] Capturing after-state on both nodes"
capture_local after
capture_remote after

echo "[6/6] Generating machine-readable and Markdown summaries"
python3 "$SUMMARIZER" "$RUN_DIR"

(
  cd "$RUN_DIR"
  find . -type f ! -name SHA256SUMS -print0 |
    sort -z |
    xargs -0 sha256sum > SHA256SUMS
)

echo
echo "Test directory: $RUN_DIR"
echo "Summary:        $RUN_DIR/summary.md"
echo "JSON summary:   $RUN_DIR/summary.json"

if [[ "$IPERF_EXIT" -ne 0 ]]; then
  echo "iperf3 failed with exit code $IPERF_EXIT" >&2
  exit "$IPERF_EXIT"
fi
