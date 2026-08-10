#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  echo "Usage: $0 <output-dir> <name> -- <command...>" >&2
}

if (( $# < 4 )); then
  usage
  exit 2
fi

output_dir="$1"
name="$2"
separator="$3"
shift 3

if [[ -z "$output_dir" || "$separator" != "--" || $# -eq 0 ]]; then
  usage
  exit 2
fi
if [[ ! "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "Capture name must be one safe path component" >&2
  exit 2
fi

mkdir -p -- "$output_dir"
capture_dir="$output_dir/$name"
if ! mkdir -- "$capture_dir"; then
  echo "Capture already exists or cannot be created: $capture_dir" >&2
  exit 3
fi

printf '%q ' "$@" >"$capture_dir/command.txt"
printf '\n' >>"$capture_dir/command.txt"

exit_code=0
"$@" >"$capture_dir/stdout.log" 2>"$capture_dir/stderr.log" || exit_code=$?

printf '%s\n' "$exit_code" >"$capture_dir/exit-code.txt"
exit "$exit_code"
