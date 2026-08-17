#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: stop-server.sh [options]

Options:
  -o, --output-dir DIR   Evidence directory created by start-server.sh
  -t, --timeout SECONDS  SIGTERM grace period before Docker uses SIGKILL (default: 60)
  -n, --name NAME        Expected container name; defaults to container-name.txt
      --help             Show this help

The script stops the recorded container when it is running, captures its logs
and final state, then removes it. Shutdown observations are evidence, not a
cleanup gate; rerun the benchmark if the evidence shows a failed lifecycle.
HELP
}

OPTS="$(getopt \
  -o o:t:n: \
  --long output-dir:,timeout:,name:,help \
  -n 'stop-server.sh' -- "$@")" || {
  usage >&2
  exit 2
}
eval set -- "${OPTS}"

OUTPUT_DIR="."
TIMEOUT="60"
CONTAINER_NAME=""

while true; do
  case "$1" in
    -o|--output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    -t|--timeout) TIMEOUT="$2"; shift 2 ;;
    -n|--name) CONTAINER_NAME="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    --) shift; break ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ $# -eq 0 ]] || { echo "error: unexpected positional arguments: $*" >&2; exit 2; }
command -v docker >/dev/null || { echo "error: docker is required" >&2; exit 1; }
[[ "${TIMEOUT}" =~ ^[1-9][0-9]*$ ]] || {
  echo "error: timeout must be a positive integer" >&2
  exit 2
}

OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd -P)" || {
  echo "error: output directory does not exist: ${OUTPUT_DIR}" >&2
  exit 1
}
for metadata_file in container-name.txt container-id.txt; do
  [[ -r "${OUTPUT_DIR}/${metadata_file}" ]] || {
    echo "error: missing ${OUTPUT_DIR}/${metadata_file}; use the start-server.sh run directory" >&2
    exit 1
  }
done
recorded_name="$(sed -n '1p' "${OUTPUT_DIR}/container-name.txt")"
recorded_id="$(sed -n '1p' "${OUTPUT_DIR}/container-id.txt")"
CONTAINER_NAME="${CONTAINER_NAME:-${recorded_name}}"

[[ "${CONTAINER_NAME}" == "${recorded_name}" ]] || {
  echo "error: requested container ${CONTAINER_NAME} does not match recorded container ${recorded_name}" >&2
  exit 1
}
if ! current_id="$(docker inspect --format '{{.Id}}' "${CONTAINER_NAME}" 2>/dev/null)"; then
  echo "error: recorded container ${CONTAINER_NAME} no longer exists" >&2
  exit 1
fi
[[ "${current_id}" == "${recorded_id}" ]] || {
  echo "error: container ID mismatch; refusing to stop a different container" >&2
  exit 1
}

: >"${OUTPUT_DIR}/container-inspect.stderr.log"

inspect_field() {
  local format="$1"
  local value
  if value="$(docker inspect --format "${format}" "${CONTAINER_NAME}" \
      2>>"${OUTPUT_DIR}/container-inspect.stderr.log")"; then
    printf '%s' "${value}"
  else
    printf 'unknown'
  fi
}

pre_stop_running="$(inspect_field '{{.State.Running}}')"
date +%s%N >"${OUTPUT_DIR}/server-stop-requested-ns.txt"
date --iso-8601=seconds >"${OUTPUT_DIR}/server-stop-requested-time.txt"
stop_started_ns="$(sed -n '1p' "${OUTPUT_DIR}/server-stop-requested-ns.txt")"

docker_stop_attempted=false
docker_stop_rc="not_run"
if [[ "${pre_stop_running}" == "true" ]]; then
  docker_stop_attempted=true
  set +e
  docker stop --signal SIGTERM --timeout "${TIMEOUT}" "${CONTAINER_NAME}" \
    >"${OUTPUT_DIR}/docker-stop.stdout.log" \
    2>"${OUTPUT_DIR}/docker-stop.stderr.log"
  docker_stop_rc=$?
  set -e
else
  : >"${OUTPUT_DIR}/docker-stop.stdout.log"
  printf 'container was not running when stop was requested\n' \
    >"${OUTPUT_DIR}/docker-stop.stderr.log"
fi

date +%s%N >"${OUTPUT_DIR}/server-stop-finished-ns.txt"
date --iso-8601=seconds >"${OUTPUT_DIR}/server-stop-finished-time.txt"
stop_finished_ns="$(sed -n '1p' "${OUTPUT_DIR}/server-stop-finished-ns.txt")"
stop_seconds="$(awk -v start="${stop_started_ns}" -v finish="${stop_finished_ns}" \
  'BEGIN { printf "%.3f", (finish-start)/1000000000 }')"

set +e
docker logs --timestamps "${CONTAINER_NAME}" \
  >"${OUTPUT_DIR}/server.log" 2>&1
server_log_capture_rc=$?
docker inspect "${CONTAINER_NAME}" \
  >"${OUTPUT_DIR}/container-post-stop-inspect.json" \
  2>>"${OUTPUT_DIR}/container-inspect.stderr.log"
post_stop_inspect_rc=$?
set -e

post_stop_running="$(inspect_field '{{.State.Running}}')"
container_status="$(inspect_field '{{.State.Status}}')"
container_exit_code="$(inspect_field '{{.State.ExitCode}}')"
oom_killed="$(inspect_field '{{.State.OOMKilled}}')"
restart_count="$(inspect_field '{{.RestartCount}}')"

graceful_shutdown=false
if [[ "${docker_stop_attempted}" == true ]] \
  && [[ "${docker_stop_rc}" == "0" ]] \
  && [[ "${post_stop_running}" == "false" ]] \
  && [[ "${container_exit_code}" == "0" ]] \
  && [[ "${oom_killed}" == "false" ]]; then
  graceful_shutdown=true
fi

set +e
docker rm --force "${CONTAINER_NAME}" \
  >"${OUTPUT_DIR}/docker-rm.stdout.log" \
  2>"${OUTPUT_DIR}/docker-rm.stderr.log"
container_remove_rc=$?
set -e
container_removed=false
if [[ "${container_remove_rc}" == "0" ]]; then
  container_removed=true
fi

logging_complete=false
if (( server_log_capture_rc == 0 )) && (( post_stop_inspect_rc == 0 )); then
  logging_complete=true
fi
lifecycle_success="${container_removed}"

{
  printf 'graceful_shutdown=%s\n' "${graceful_shutdown}"
  printf 'lifecycle_success=%s\n' "${lifecycle_success}"
  printf 'docker_stop_attempted=%s\n' "${docker_stop_attempted}"
  printf 'docker_stop_rc=%s\n' "${docker_stop_rc}"
  printf 'container_status=%s\n' "${container_status}"
  printf 'container_running=%s\n' "${post_stop_running}"
  printf 'container_exit_code=%s\n' "${container_exit_code}"
  printf 'oom_killed=%s\n' "${oom_killed}"
  printf 'restart_count=%s\n' "${restart_count}"
  printf 'server_log_capture_rc=%d\n' "${server_log_capture_rc}"
  printf 'post_stop_inspect_rc=%d\n' "${post_stop_inspect_rc}"
  printf 'logging_complete=%s\n' "${logging_complete}"
  printf 'stop_seconds=%s\n' "${stop_seconds}"
  printf 'container_remove_rc=%s\n' "${container_remove_rc}"
  printf 'container_removed=%s\n' "${container_removed}"
} >"${OUTPUT_DIR}/graceful-shutdown.env"

printf 'graceful_shutdown=%s\nlifecycle_success=%s\nstop_seconds=%s\n' \
  "${graceful_shutdown}" "${lifecycle_success}" "${stop_seconds}"

if [[ "${lifecycle_success}" != true ]]; then
  echo "error: container cleanup failed; see ${OUTPUT_DIR}/graceful-shutdown.env" >&2
  exit 1
fi
