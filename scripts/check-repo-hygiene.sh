#!/usr/bin/env bash
set -euo pipefail
shopt -s lastpipe

if (( $# != 0 )); then
  echo "Usage: $0" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "Run this script from inside the repository" >&2
  exit 2
}
evidence_root="$repo_root/benchmarks/raw-results"
m0_root="$evidence_root/m0-platform-qualification"

if [[ ! -d "$evidence_root" ]]; then
  echo "Evidence root is missing: $evidence_root" >&2
  exit 2
fi

readonly max_run_files=12
readonly max_run_bytes=$((1024 * 1024))
readonly max_file_bytes=$((512 * 1024))
readonly max_summary_bytes=$((256 * 1024))
readonly max_total_files=60
readonly max_total_bytes=$((8 * 1024 * 1024))

violations=0
checked_runs=0

violation() {
  echo "FAIL: $*" >&2
  violations=$((violations + 1))
}

measure_tree() {
  local root="$1" file size
  measured_files=0
  measured_bytes=0
  find "$root" -type f -print0 |
  while IFS= read -r -d '' file; do
    size="$(stat -c %s -- "$file")" || exit 2
    measured_files=$((measured_files + 1))
    measured_bytes=$((measured_bytes + size))
  done
}

# M0 is frozen historical evidence; every budget below applies only to M1+.
find "$evidence_root" -mindepth 2 -maxdepth 2 -type d \
  ! -path "$m0_root/*" -print0 |
while IFS= read -r -d '' run_dir; do
  checked_runs=$((checked_runs + 1))
  measure_tree "$run_dir"
  relative="${run_dir#"$repo_root"/}"
  if (( measured_files > max_run_files )); then
    violation "$relative has $measured_files files (limit: $max_run_files)"
  fi
  if (( measured_bytes > max_run_bytes )); then
    violation "$relative has $measured_bytes bytes (limit: $max_run_bytes)"
  fi
done

total_files=0
total_bytes=0
find "$evidence_root" -path "$m0_root" -prune -o -type f -print0 |
while IFS= read -r -d '' file; do
  size="$(stat -c %s -- "$file")" || exit 2
  total_files=$((total_files + 1))
  total_bytes=$((total_bytes + size))
  relative="${file#"$repo_root"/}"

  if (( size > max_file_bytes )); then
    violation "$relative has $size bytes (evidence-file limit: $max_file_bytes)"
  fi
  if [[ "$file" == */derived/summary.json ]] && (( size > max_summary_bytes )); then
    violation "$relative has $size bytes (summary limit: $max_summary_bytes)"
  fi
done

if (( total_files > max_total_files )); then
  violation "M1+ raw-results has $total_files files (limit: $max_total_files)"
fi
if (( total_bytes > max_total_bytes )); then
  violation "M1+ raw-results has $total_bytes bytes (limit: $max_total_bytes)"
fi

tracked_total=0
tracked_evidence=0
git -C "$repo_root" ls-files -z |
while IFS= read -r -d '' path; do
  [[ "$path" == benchmarks/raw-results/m0-platform-qualification/* ]] && continue
  tracked_total=$((tracked_total + 1))
  if [[ "$path" == benchmarks/raw-results/* ]]; then
    tracked_evidence=$((tracked_evidence + 1))
  fi
done

if (( tracked_total == 0 )); then
  violation "no tracked files found outside the frozen M0 tree"
elif (( tracked_evidence * 100 > tracked_total * 30 )); then
  ratio="$(awk -v raw="$tracked_evidence" -v all="$tracked_total" \
    'BEGIN { printf "%.1f", raw * 100 / all }')"
  violation "M1+ raw-results is $ratio% of tracked non-M0 files ($tracked_evidence/$tracked_total; limit: 30%)"
fi

if (( violations > 0 )); then
  echo "Repository hygiene failed with $violations violation(s)." >&2
  exit 1
fi

echo "Repository hygiene passed: $checked_runs M1+ runs, $total_files files, $total_bytes bytes."
