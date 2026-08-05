#!/usr/bin/env bash
# Verify management/data interfaces, peer reachability, NIC/RDMA mapping, and optional TCP baseline.
set -uo pipefail

MGMT_IFACE="${MGMT_IFACE:-}"
DATA_IFACE="${DATA_IFACE:-}"
PEER_MGMT_IP="${PEER_MGMT_IP:-}"
PEER_DATA_IP="${PEER_DATA_IP:-}"
REQUIRE_RDMA="${REQUIRE_RDMA:-0}"
RUN_IPERF="${RUN_IPERF:-0}"
IPERF_SECONDS="${IPERF_SECONDS:-15}"
OUTPUT_ROOT="${OUTPUT_ROOT:-./results/bootstrap}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
STAMP="$RUN_ID"
HOST="$(hostname -s 2>/dev/null || hostname)"
OUT_DIR="${OUTPUT_ROOT}/${STAMP}/${HOST}/network"
mkdir -p "$OUT_DIR"

failures=0; warnings=0
pass(){ printf '[PASS] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; warnings=$((warnings+1)); }
fail(){ printf '[FAIL] %s\n' "$*"; failures=$((failures+1)); }
have(){ command -v "$1" >/dev/null 2>&1; }

printf 'Network verification: %s\nEvidence directory: %s\n\n' "$HOST" "$OUT_DIR"

if ! have ip; then fail 'iproute2 is required'; exit 1; fi
ip -brief link >"$OUT_DIR/ip-link-brief.txt" 2>&1
ip -brief address >"$OUT_DIR/ip-address-brief.txt" 2>&1
ip route show table all >"$OUT_DIR/ip-routes.txt" 2>&1
ip -s link >"$OUT_DIR/ip-link-counters.txt" 2>&1

check_iface() {
  local role="$1" iface="$2"
  if [[ -z "$iface" ]]; then warn "$role interface is not configured"; return; fi
  if [[ ! -d "/sys/class/net/$iface" ]]; then fail "$role interface does not exist: $iface"; return; fi

  local state carrier mtu
  state="$(cat "/sys/class/net/$iface/operstate" 2>/dev/null || echo unknown)"
  carrier="$(cat "/sys/class/net/$iface/carrier" 2>/dev/null || echo unknown)"
  mtu="$(cat "/sys/class/net/$iface/mtu" 2>/dev/null || echo unknown)"
  printf 'interface=%s\nrole=%s\nstate=%s\ncarrier=%s\nmtu=%s\n' "$iface" "$role" "$state" "$carrier" "$mtu" \
    >"$OUT_DIR/${role}-interface-summary.txt"

  if [[ "$state" == "up" && "$carrier" == "1" ]]; then pass "$role interface is up with carrier: $iface"; else fail "$role interface is not operational: $iface (state=$state carrier=$carrier)"; fi

  ip -details link show dev "$iface" >"$OUT_DIR/${role}-ip-link.txt" 2>&1 || true
  ip address show dev "$iface" >"$OUT_DIR/${role}-ip-address.txt" 2>&1 || true
  ip -s link show dev "$iface" >"$OUT_DIR/${role}-ip-counters.txt" 2>&1 || true

  if have ethtool; then
    ethtool "$iface" >"$OUT_DIR/${role}-ethtool.txt" 2>&1 || true
    ethtool -i "$iface" >"$OUT_DIR/${role}-driver-firmware.txt" 2>&1 || true
    ethtool --show-fec "$iface" >"$OUT_DIR/${role}-fec.txt" 2>&1 || true
    ethtool -S "$iface" >"$OUT_DIR/${role}-ethtool-stats-raw.txt" 2>&1 || true
    grep -Ei '(^|_)(rx|tx).*(bytes|packets|errors|error|drop|dropped|discard|crc|pause|timeout|retry)|out_of_buffer|buffer.*error' \
      "$OUT_DIR/${role}-ethtool-stats-raw.txt" >"$OUT_DIR/${role}-ethtool-stats-summary.txt" || true
    pass "$role NIC driver, firmware, link and counters captured"
  else
    warn 'ethtool is not installed'
  fi
}

check_iface management "$MGMT_IFACE"
check_iface data "$DATA_IFACE"

check_peer() {
  local role="$1" iface="$2" peer="$3"
  if [[ -z "$peer" ]]; then warn "$role peer IP is not configured"; return; fi
  ip route get "$peer" >"$OUT_DIR/${role}-route-to-peer.txt" 2>&1 || true
  if [[ -n "$iface" ]] && ping -c 5 -W 2 -I "$iface" "$peer" >"$OUT_DIR/${role}-ping.txt" 2>&1; then
    pass "$role peer is reachable via $iface: $peer"
  else
    fail "$role peer is unreachable via ${iface:-default route}: $peer"
  fi
}

if have ping; then
  check_peer management "$MGMT_IFACE" "$PEER_MGMT_IP"
  check_peer data "$DATA_IFACE" "$PEER_DATA_IP"
else
  fail 'ping is not installed'
fi

# RDMA inventory and netdev mapping. Lack of tools is warning unless REQUIRE_RDMA=1.
rdma_ok=0
if have rdma; then
  rdma link show >"$OUT_DIR/rdma-link.txt" 2>&1 || true
  rdma dev show >"$OUT_DIR/rdma-dev.txt" 2>&1 || true
  [[ -s "$OUT_DIR/rdma-link.txt" ]] && rdma_ok=1
fi
if have ibdev2netdev; then ibdev2netdev >"$OUT_DIR/ibdev2netdev.txt" 2>&1 || true; [[ -s "$OUT_DIR/ibdev2netdev.txt" ]] && rdma_ok=1; fi
if have ibv_devinfo; then ibv_devinfo -v >"$OUT_DIR/ibv-devinfo.txt" 2>&1 || true; fi

if (( rdma_ok == 1 )); then
  pass 'RDMA device inventory was captured'
  if [[ -n "$DATA_IFACE" && -s "$OUT_DIR/ibdev2netdev.txt" ]]; then
    if grep -Eq "[[:space:]]${DATA_IFACE}[[:space:]]" "$OUT_DIR/ibdev2netdev.txt"; then
      pass "Data interface maps to an RDMA device: $DATA_IFACE"
    elif (( REQUIRE_RDMA == 1 )); then
      fail "Data interface is not mapped to an RDMA device: $DATA_IFACE"
    else
      warn "No RDMA mapping found for data interface: $DATA_IFACE"
    fi
  fi
else
  if (( REQUIRE_RDMA == 1 )); then fail 'RDMA is required but no RDMA device inventory was found'; else warn 'RDMA inventory unavailable or empty'; fi
fi

# Optional client-side TCP throughput baseline. Start iperf3 -s on the peer first.
if (( RUN_IPERF == 1 )); then
  if ! have iperf3; then
    fail 'RUN_IPERF=1 but iperf3 is not installed'
  elif [[ -z "$PEER_DATA_IP" ]]; then
    fail 'RUN_IPERF=1 but PEER_DATA_IP is empty'
  else
    [[ -n "$DATA_IFACE" ]] && ip -s link show dev "$DATA_IFACE" >"$OUT_DIR/data-counters-before.txt" 2>&1 || true
    [[ -n "$DATA_IFACE" ]] && have ethtool && ethtool -S "$DATA_IFACE" >"$OUT_DIR/data-ethtool-before.txt" 2>&1 || true

    iperf_args=(-c "$PEER_DATA_IP" -t "$IPERF_SECONDS" --json)
    source_ip=""
    if [[ -n "$DATA_IFACE" ]]; then
      source_ip="$(ip -4 -o addr show dev "$DATA_IFACE" | awk 'NR==1 {split($4,a,"/"); print a[1]}')"
      [[ -n "$source_ip" ]] && iperf_args+=(-B "$source_ip")
    fi

    if iperf3 "${iperf_args[@]}" >"$OUT_DIR/iperf3-data.json" 2>"$OUT_DIR/iperf3-data.stderr"; then
      pass 'iperf3 TCP baseline completed on the data path'
    else
      fail 'iperf3 TCP baseline failed; confirm the peer is running iperf3 -s'
    fi

    [[ -n "$DATA_IFACE" ]] && ip -s link show dev "$DATA_IFACE" >"$OUT_DIR/data-counters-after.txt" 2>&1 || true
    [[ -n "$DATA_IFACE" ]] && have ethtool && ethtool -S "$DATA_IFACE" >"$OUT_DIR/data-ethtool-after.txt" 2>&1 || true
  fi
else
  warn 'RUN_IPERF=0; TCP bandwidth baseline was not executed'
fi

printf '\nSummary: failures=%d warnings=%d\nEvidence: %s\n' "$failures" "$warnings" "$OUT_DIR"
(( failures == 0 ))
