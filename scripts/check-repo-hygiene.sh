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
readonly max_milestone_files=60
readonly max_milestone_bytes=$((8 * 1024 * 1024))

violations=0
checked_runs=0
excluded_runs=0
declare -A excluded_run_paths=()
declare -A milestone_files=() milestone_bytes=() milestone_runs=()

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

top_level_value() {
  local run_yaml="$1/run.yaml"
  local key="$2"
  [[ -f "$run_yaml" ]] || return 0
  awk -F: -v key="$key" '$1 == key {
    sub(/^[^:]*:[[:space:]]*/, ""); gsub(/["'\''[:space:]]/, ""); print; exit
  }' "$run_yaml"
}

is_excluded_path() {
  local path="$1" run
  for run in "${!excluded_run_paths[@]}"; do
    [[ "$path" == "$run" || "$path" == "$run/"* ]] && return 0
  done
  return 1
}

# M0 is frozen historical evidence; every budget below applies only to M1+.
find "$evidence_root" -mindepth 2 -maxdepth 2 -type d \
  ! -path "$m0_root/*" -print0 |
while IFS= read -r -d '' run_dir; do
  relative="${run_dir#"$repo_root"/}"
  outcome="$(top_level_value "$run_dir" outcome)"
  if [[ "$outcome" != "success" ]]; then
    excluded_run_paths["$relative"]=1
    excluded_runs=$((excluded_runs + 1))
    [[ -n "$outcome" ]] || outcome="missing"
    echo "INFO: excluding failure/incomplete evidence from budgets: $relative (outcome: $outcome)"
    continue
  fi
  milestone="$(top_level_value "$run_dir" milestone)"
  if [[ -z "$milestone" ]]; then
    violation "$relative has outcome success but no top-level milestone"
  fi
  checked_runs=$((checked_runs + 1))
  measure_tree "$run_dir"
  if [[ -n "$milestone" ]]; then
    file_count="${milestone_files[$milestone]:-0}"
    byte_count="${milestone_bytes[$milestone]:-0}"
    run_count="${milestone_runs[$milestone]:-0}"
    milestone_files["$milestone"]=$((file_count + measured_files))
    milestone_bytes["$milestone"]=$((byte_count + measured_bytes))
    milestone_runs["$milestone"]=$((run_count + 1))
  fi
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
  relative="${file#"$repo_root"/}"
  is_excluded_path "$relative" && continue
  size="$(stat -c %s -- "$file")" || exit 2
  total_files=$((total_files + 1))
  total_bytes=$((total_bytes + size))

  if (( size > max_file_bytes )); then
    violation "$relative has $size bytes (evidence-file limit: $max_file_bytes)"
  fi
  if [[ "$file" == */derived/summary.json ]] && (( size > max_summary_bytes )); then
    violation "$relative has $size bytes (summary limit: $max_summary_bytes)"
  fi
done

if (( ${#milestone_files[@]} > 0 )); then
  while IFS= read -r milestone; do
    files="${milestone_files[$milestone]}"
    bytes="${milestone_bytes[$milestone]}"
    runs="${milestone_runs[$milestone]}"
    echo "INFO: $milestone success evidence: $runs runs, $files files, $bytes bytes"
    if (( files > max_milestone_files )); then
      violation "$milestone success evidence has $files files (limit: $max_milestone_files)"
    fi
    if (( bytes > max_milestone_bytes )); then
      violation "$milestone success evidence has $bytes bytes (limit: $max_milestone_bytes)"
    fi
  done < <(printf '%s\n' "${!milestone_files[@]}" | sort)
fi
echo "INFO: eligible M1+ raw-results total: $total_files files, $total_bytes bytes"

tracked_total=0
tracked_evidence=0
git -C "$repo_root" ls-files -z |
while IFS= read -r -d '' path; do
  [[ "$path" == benchmarks/raw-results/m0-platform-qualification/* ]] && continue
  is_excluded_path "$path" && continue
  tracked_total=$((tracked_total + 1))
  if [[ "$path" == benchmarks/raw-results/* ]]; then
    tracked_evidence=$((tracked_evidence + 1))
  fi
done

if (( tracked_total == 0 )); then
  violation "no tracked files found outside the frozen M0 tree"
else
  ratio="$(awk -v raw="$tracked_evidence" -v all="$tracked_total" \
    'BEGIN { printf "%.1f", raw * 100 / all }')"
  echo "INFO: tracked M1+ raw-results ratio: $ratio% ($tracked_evidence/$tracked_total non-M0 files)"
fi

if (( violations > 0 )); then
  echo "Repository hygiene failed with $violations violation(s); $excluded_runs failure/incomplete run(s) excluded." >&2
  exit 1
fi

echo "Repository hygiene passed: $checked_runs M1+ success runs, $excluded_runs failure/incomplete run(s) excluded, $total_files files, $total_bytes bytes."
