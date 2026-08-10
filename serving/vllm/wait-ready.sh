#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: wait-ready.sh [options]

Options:
  -o, --output-dir DIR   Evidence directory created by start-server.sh
  -h, --host HOST        Override host from base-url.txt
  -p, --port PORT        Override port from base-url.txt
  -t, --timeout SECONDS  Readiness deadline (default: 300)
      --help             Show this help
HELP
}

OPTS="$(getopt \
  -o o:h:p:t: \
  --long output-dir:,host:,port:,timeout:,help \
  -n 'wait-ready.sh' -- "$@")" || {
  usage >&2
  exit 2
}
eval set -- "${OPTS}"

OUTPUT_DIR="."
HOST=""
PORT=""
TIMEOUT="300"

while true; do
  case "$1" in
    -o|--output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    -h|--host) HOST="$2"; shift 2 ;;
    -p|--port) PORT="$2"; shift 2 ;;
    -t|--timeout) TIMEOUT="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    --) shift; break ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ $# -eq 0 ]] || { echo "error: unexpected positional arguments: $*" >&2; exit 2; }
command -v curl >/dev/null || { echo "error: curl is required" >&2; exit 1; }
[[ "${TIMEOUT}" =~ ^[1-9][0-9]*$ ]] || {
  echo "error: timeout must be a positive integer" >&2
  exit 2
}
if [[ -n "${PORT}" ]]; then
  [[ "${PORT}" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || {
    echo "error: port must be an integer from 1 to 65535" >&2
    exit 2
  }
fi

OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd -P)" || {
  echo "error: output directory does not exist: ${OUTPUT_DIR}" >&2
  exit 1
}
START_NS_FILE="${OUTPUT_DIR}/server-start-ns.txt"
[[ -r "${START_NS_FILE}" ]] || {
  echo "error: missing ${START_NS_FILE}; run start-server.sh with the same output directory" >&2
  exit 1
}
ready_started_ns="$(sed -n '1p' "${START_NS_FILE}")"
[[ "${ready_started_ns}" =~ ^[0-9]+$ ]] || {
  echo "error: invalid nanosecond timestamp in ${START_NS_FILE}" >&2
  exit 1
}

if [[ -z "${HOST}" && -z "${PORT}" && -r "${OUTPUT_DIR}/base-url.txt" ]]; then
  base_url="$(sed -n '1p' "${OUTPUT_DIR}/base-url.txt")"
else
  base_url="http://${HOST:-127.0.0.1}:${PORT:-8000}"
fi

ATTEMPTS_FILE="${OUTPUT_DIR}/readiness-attempts.tsv"
if [[ -e "${ATTEMPTS_FILE}" || -e "${OUTPUT_DIR}/ready-result.env" ]]; then
  echo "error: readiness evidence already exists; use a fresh run directory" >&2
  exit 1
fi
printf 'attempt\ttimestamp\tcurl_rc\thttp_status\n' >"${ATTEMPTS_FILE}"

ready=false
attempt=0
last_status="000"
last_curl_rc=0
loop_started_seconds=${SECONDS}

while (( SECONDS - loop_started_seconds < TIMEOUT )); do
  attempt=$((attempt + 1))
  observed_at="$(date --iso-8601=seconds)"

  printf 'attempt=%d timestamp=%s\n' "${attempt}" "${observed_at}" \
    >>"${OUTPUT_DIR}/readiness-curl.stderr.log"
  set +e
  status="$(curl --silent --show-error \
    --connect-timeout 1 \
    --max-time 2 \
    --output /dev/null \
    --write-out '%{http_code}' \
    "${base_url}/health" \
    2>>"${OUTPUT_DIR}/readiness-curl.stderr.log")"
  curl_rc=$?
  set -e

  [[ "${status}" =~ ^[0-9]{3}$ ]] || status="000"
  last_status="${status}"
  last_curl_rc="${curl_rc}"
  printf '%d\t%s\t%d\t%s\n' \
    "${attempt}" "${observed_at}" "${curl_rc}" "${status}" >>"${ATTEMPTS_FILE}"

  if (( curl_rc == 0 )) && [[ "${status}" == "200" ]]; then
    ready=true
    break
  fi
  sleep 1
done

ready_finished_ns="$(date +%s%N)"
date --iso-8601=seconds >"${OUTPUT_DIR}/ready-finished-time.txt"
ready_seconds="$(awk -v start="${ready_started_ns}" -v finish="${ready_finished_ns}" \
  'BEGIN { printf "%.3f", (finish-start)/1000000000 }')"
printf 'server_ready_seconds=%s\n' "${ready_seconds}" >"${OUTPUT_DIR}/ready-time.txt"
printf '%s\n' "${last_status}" >"${OUTPUT_DIR}/health.txt"
{
  printf 'ready=%s\n' "${ready}"
  printf 'attempts=%d\n' "${attempt}"
  printf 'last_curl_rc=%d\n' "${last_curl_rc}"
  printf 'last_http_status=%s\n' "${last_status}"
  printf 'server_ready_seconds=%s\n' "${ready_seconds}"
} >"${OUTPUT_DIR}/ready-result.env"

if [[ "${ready}" != true ]]; then
  echo "error: server did not become ready within ${TIMEOUT} seconds" >&2
  exit 1
fi

printf 'ready=true\nattempts=%d\nserver_ready_seconds=%s\n' "${attempt}" "${ready_seconds}"
