#!/usr/bin/env bash
set -euo pipefail
shopt -s lastpipe
usage() {
  echo "Usage: $0 <private-run-source> <public-destination> [--failed] [--literal <value>]..." >&2
}
usage_error() { usage; exit 2; }
die() { echo "$1" >&2; exit "${2:-2}"; }
valid_literal() {
  local value="$1"
  [[ ${#value} -ge 4 && "$value" != "/" && "$value" != "." && "$value" != ".." &&
     "$value" != *$'\n'* && "$value" != *$'\r'* ]]
}
(( $# >= 2 )) || usage_error
source_dir="$1"
destination="$2"
shift 2
declare -a configured_literals=()
failed_mode=false
while (( $# > 0 )); do
  case "$1" in
    --failed) failed_mode=true; shift ;;
    --literal)
      (( $# >= 2 )) && valid_literal "$2" || usage_error
      configured_literals+=("$2"); shift 2 ;;
    *) usage_error ;;
  esac
done
[[ -d "$source_dir" && ! -L "$source_dir" ]] || die "Private source must be a real directory: $source_dir"
[[ ! -e "$destination" && ! -L "$destination" ]] || die "Public destination already exists: $destination"
source_abs="$(realpath -e -- "$source_dir")"
destination_abs="$(realpath -m -- "$destination")"
case "$destination_abs" in
  "$source_abs"|"$source_abs"/*)
    die "Public destination must not be inside the private source"
    ;;
esac
if [[ "$failed_mode" == false ]]; then
  for required in run.yaml derived/summary.json raw/requests.jsonl raw/case-events.jsonl raw/server/server.log; do
    [[ -f "$source_abs/$required" && ! -L "$source_abs/$required" ]] || die "Required publication input is missing or not a regular file: $required"
  done
fi
unsafe_entry="$(find "$source_abs" -mindepth 1 ! -type f ! -type d -print -quit)" || { echo "Private source traversal failed" >&2; exit 2; }
unreadable_file="$(find "$source_abs" -type f ! -readable -print -quit)" || { echo "Private source traversal failed" >&2; exit 2; }
[[ -z "$unsafe_entry" && -z "$unreadable_file" ]] || die "Private source must contain only readable regular files and directories"
if ! perl -MJSON::PP -MSocket=AF_INET,AF_INET6,inet_pton -e 1 2>/dev/null || ! python3 -c 'import yaml' 2>/dev/null; then
  die "Perl JSON::PP/Socket and Python PyYAML support are required"
fi
short_hostname="$(hostname 2>/dev/null || true)"
fqdn_hostname="$(hostname -f 2>/dev/null || true)"
current_home="${HOME:-}"
declare -a private_literals=()
add_literal() {
  local value="$1" existing index
  valid_literal "$value" || return 0
  for existing in "${private_literals[@]}"; do
    [[ "$existing" == "$value" ]] && return 0
  done
  for ((index = 0; index < ${#private_literals[@]}; index++)); do
    if (( ${#value} > ${#private_literals[index]} )); then
      private_literals=("${private_literals[@]:0:index}" "$value" "${private_literals[@]:index}")
      return 0
    fi
  done
  private_literals+=("$value")
}
add_literal "$fqdn_hostname"
add_literal "$short_hostname"
[[ "$current_home" == /* ]] && add_literal "$current_home"
for literal in "${configured_literals[@]}"; do add_literal "$literal"; done
secret_pattern='(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|sk_(live|test)_[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9-]{16,}|AIza[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|Authorization[[:space:]]*[:=][[:space:]]*(Basic|Bearer)[[:space:]]+[A-Za-z0-9._~+/-]{12,}|Bearer[[:space:]]+[A-Za-z0-9._~+/-]{16,}|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|https?://[^/@[:space:]]+:[^/@[:space:]]+@|(^|[^A-Za-z0-9_])(password|passwd|token|secret|api[_-]?key|aws_secret_access_key|aws_session_token|hf_token|ngc_api_key|auth|docker_auth_config|identitytoken|registrytoken)[^A-Za-z0-9_]*[:=][[:space:]]*[^[:space:],}]{8,}|(^|[[:space:]])--?(password|passwd|token|secret|api[-_]?key|hf[-_]?token|ngc[-_]?api[-_]?key|aws[-_]?session[-_]?token)[=[:space:]]+[^[:space:]]{8,})'
scan_tree() {
  local root="$1" label="$2" item relative relative_lower basename_lower literal scan_status traversal_status
  local suspected=0
  find "$root" -mindepth 1 -print0 |
  while IFS= read -r -d '' item; do
    relative="${item#"$root"/}"
    relative_lower="${relative,,}"
    basename_lower="${item##*/}"
    basename_lower="${basename_lower,,}"
    case "$basename_lower" in
      .env|.env.*|id_rsa|id_dsa|id_ecdsa|id_ed25519|*.pem|*.key|.netrc|.npmrc|.pypirc|known_hosts|authorized_keys|credentials|credentials.json|auth.json|docker-config.json)
        echo "Suspected credential file under $label: $relative" >&2; suspected=1 ;;
    esac
    case "/$relative_lower" in
      */.docker/config.json|*/.docker/auth.json|*/.ssh/config|*/.ssh/known_hosts|*/.ssh/authorized_keys)
        echo "Suspected credential path under $label: $relative" >&2; suspected=1 ;;
    esac
    if LC_ALL=C grep -aEqi -- "$secret_pattern" <<<"$relative"; then
      echo "Suspected secret pattern in a path under $label" >&2; suspected=1
    else
      scan_status=$?
      (( scan_status <= 1 )) || { echo "Could not scan a path under $label" >&2; suspected=1; }
    fi
    for literal in "${private_literals[@]}"; do
      if [[ "$relative" == *"$literal"* ]]; then
        echo "Private identifier found in a path under $label; rename it first" >&2
        suspected=1
        break
      fi
    done
    if [[ -f "$item" ]]; then
      if LC_ALL=C grep -aEqi -- "$secret_pattern" "$item"; then
        echo "Suspected secret pattern in $label: $relative" >&2; suspected=1
      else
        scan_status=$?
        (( scan_status <= 1 )) || { echo "Could not scan $label: $relative" >&2; suspected=1; }
      fi
    fi
  done
  traversal_status=$?
  (( traversal_status == 0 )) || { echo "Could not traverse $label" >&2; return 1; }
  (( suspected == 0 ))
}

LC_ALL=C grep -Eqi -- "$secret_pattern" <<<"$destination" && die "Public destination contains a suspected secret pattern" 3
if ! scan_tree "$source_abs" "private source"; then
  echo "No public copy was created. Review the private source before publication." >&2
  exit 3
fi

if [[ "$failed_mode" == false ]]; then
  run_outcome="$(awk -F: '/^outcome:[[:space:]]*/ {sub(/^[^:]*:[[:space:]]*/, ""); gsub(/["'\''[:space:]]/, ""); print; exit}' "$source_abs/run.yaml")"
  [[ -n "$run_outcome" ]] || die "run.yaml is missing top-level outcome" 3
fi

mkdir -p -- "$(dirname -- "$destination_abs")"
trap 'echo "Sanitization failed; treat any created public copy as unsafe." >&2' ERR
mkdir -p -- "$destination_abs"
preserved_failure_tree=false
if [[ "$failed_mode" == true ]]; then
  cp -R -- "$source_abs/." "$destination_abs/"
  preserved_failure_tree=true
else
mkdir -p -- "$destination_abs/derived" "$destination_abs/raw/server"
cp -- "$source_abs/run.yaml" "$destination_abs/run.yaml"
publication_state="$(perl -MJSON::PP -e '
  my ($requests,$events,$summary_path,$case_root,$request_out,$life_out,$summary_out)=@ARGV;
  my $json=JSON::PP->new->canonical->utf8; my (%requests_by_case,%seen,%stats); my $failure=0; (my $derived_dir=$summary_path)=~s{/[^/]+\z}{};
  my @fields=qw(case_id request_index start_wall_utc start_monotonic_ns first_content_monotonic_ns last_content_monotonic_ns end_monotonic_ns input_tokens output_tokens token_count_source http_status success timeout error_type error_message finish_reason stream_event_count content_chunk_count request_id_verified);
  sub records { my ($path)=@_; open my $fh,"<:raw",$path or die "$path: $!\n"; my @rows;
    while (<$fh>) { next unless /\S/; my $row=$json->decode($_); die "$path contains a non-object record\n" unless ref($row) eq "HASH"; push @rows,$row } return @rows }
  open my $sf,"<:raw",$summary_path or die "$summary_path: $!\n"; my $summary_text; { local $/; $summary_text=<$sf> } close $sf;
  my $summary=$json->decode($summary_text); die "summary must be an object\n" unless ref($summary) eq "HASH";
  die "summary already contains public sampling metadata\n" if exists($summary->{sampling}) || exists($summary->{percentiles_recomputable_from_public_raw});
  for my $pair (["cases","cases.jsonl"],["concurrency_summary","concurrency-summary.jsonl"]) {
    my ($key,$name)=@$pair; my $path="$derived_dir/$name"; next unless -f $path; my @rows=records($path);
    die "$name is not equivalent to summary.$key\n" unless ref($summary->{$key}) eq "ARRAY" && $json->encode(\@rows) eq $json->encode($summary->{$key});
  }
  for my $row (records($requests)) { my ($case,$index)=@{$row}{qw(case_id request_index)};
    die "request record has invalid case_id\n" unless defined($case) && !ref($case) && $case =~ /\A[A-Za-z0-9._-]+\z/ && $case !~ /\A\.\.?\z/;
    die "request record has invalid request_index\n" unless defined($index) && !ref($index) && $index =~ /\A\d+\z/;
    die "duplicate case_id/request_index\n" if $seen{"$case\0$index"}++;
    die "request record has invalid success/timeout\n" unless JSON::PP::is_bool($row->{success}) && JSON::PP::is_bool($row->{timeout});
    my %public; for my $field (@fields) { die "request record is missing $field\n" unless exists $row->{$field}; $public{$field}=$row->{$field} }
    my $kind=(!$row->{success} || $row->{timeout}) ? "failure" : "success"; $failure=1 if $kind eq "failure";
    push @{$requests_by_case{$case}{$kind}}, [$index,\%public];
  }
  open my $ro,">:raw",$request_out or die "$request_out: $!\n";
  for my $case (sort keys %requests_by_case) { my @ok=sort {$a->[0]<=>$b->[0]} @{$requests_by_case{$case}{success}//[]};
    my @bad=sort {$a->[0]<=>$b->[0]} @{$requests_by_case{$case}{failure}//[]}; my ($stride,@sample)=(1);
    if (@ok<=60) {@sample=@ok} else { $stride=int((@ok-40+19)/20); push @sample,@ok[0..19];
      for (my $i=20;$i<@ok-20 && @sample<40;$i+=$stride) { push @sample,$ok[$i] } push @sample,@ok[@ok-20..@ok-1] }
    my @kept=sort {$a->[0]<=>$b->[0]} (@bad,@sample); print $ro $json->encode($_->[1]),"\n" for @kept;
    $stats{$case}={source_success_records=>0+@ok,failure_records=>0+@bad,stride=>$stride,retained_success_records=>0+@sample};
  }
  my %event; for my $row (records($events)) { my ($case,$type)=@{$row}{qw(case_id event_type)};
    die "case event has invalid case_id/type\n" unless defined($case) && $case =~ /\A[A-Za-z0-9._-]+\z/ && defined($type) && ($type eq "start" || $type eq "end");
    die "duplicate $type event for $case\n" if exists $event{$case}{$type}; $event{$case}{$type}=$row;
  }
  open my $lo,">:raw",$life_out or die "$life_out: $!\n";
  for my $case (sort keys %event) { my ($start,$end)=@{$event{$case}}{qw(start end)}; $failure=1 unless $start && $end && ($end->{outcome}//"") eq "success";
    my %exit; for my $name (qw(client idle-after metrics-after)) { my $path="$case_root/$case/$name-exit-code.txt"; my $value;
      if (-f $path) { open my $fh,"<",$path or die "$path: $!\n"; $value=<$fh>; close $fh; $value =~ s/\s+\z// if defined $value; die "$path has invalid exit code\n" unless defined($value) && $value =~ /\A-?\d+\z/; $value=0+$value }
      (my $field=$name)=~tr/-/_/; $exit{$field."_exit_code"}=$value; $failure=1 unless defined($value) && $value==0;
    }
    my $base=$end//$start//{}; my %life=(case_id=>$case,concurrency=>$base->{concurrency},repetition=>$base->{repetition},measured=>$base->{measured},
      start_wall_utc=>$start ? $start->{timestamp_utc}:undef,start_monotonic_ns=>$start ? $start->{monotonic_ns}:undef,
      end_wall_utc=>$end ? $end->{timestamp_utc}:undef,end_monotonic_ns=>$end ? $end->{monotonic_ns}:undef,
      planned_requests=>$base->{planned_requests},completed_requests=>$end ? $end->{completed_requests}:undef,
      successful_requests=>$end ? $end->{successful_requests}:undef,failed_requests=>$end ? $end->{failed_requests}:undef,
      outcome=>$end ? $end->{outcome}:"missing_end",wall_time_seconds=>$end ? $end->{wall_time_seconds}:undef,%exit);
    print $lo $json->encode(\%life),"\n";
  }
  die "request case is missing lifecycle events\n" if grep {!exists $event{$_}} keys %requests_by_case;
  my $sampling=$json->encode({method=>"failures-plus-head-tail-fixed-stride-v2",head_success_records=>20,tail_success_records=>20,max_success_records_per_case=>60,public_record_fields=>\@fields,cases=>\%stats});
  my ($compact,$quoted,$escaped)=("",0,0); for my $char (split //,$summary_text) { if ($quoted) {$compact.=$char;if($escaped){$escaped=0}elsif($char eq "\\"){$escaped=1}elsif($char eq "\""){$quoted=0}}
    elsif($char eq "\""){$quoted=1;$compact.=$char}elsif($char!~/\s/){$compact.=$char} }
  die "summary must be a JSON object\n" unless substr($compact,0,1) eq "{"; substr($compact,0,1,"{\"sampling\":$sampling,\"percentiles_recomputable_from_public_raw\":false,"); $json->decode($compact);
  open my $so,">:raw",$summary_out or die "$summary_out: $!\n"; print $so $compact,"\n"; print $failure ? "failure\n" : "success\n";
' "$source_abs/raw/requests.jsonl" "$source_abs/raw/case-events.jsonl" "$source_abs/derived/summary.json" "$source_abs/raw/cases" \
  "$destination_abs/.requests.jsonl" "$destination_abs/.case-lifecycle.jsonl" "$destination_abs/.summary.json")"
if [[ "$run_outcome" != "success" || "$publication_state" != "success" ]]; then
  cp -R -- "$source_abs/." "$destination_abs/"
  preserved_failure_tree=true
fi
mv -- "$destination_abs/.requests.jsonl" "$destination_abs/raw/requests.jsonl"
mv -- "$destination_abs/.case-lifecycle.jsonl" "$destination_abs/raw/case-lifecycle.jsonl"
mv -- "$destination_abs/.summary.json" "$destination_abs/derived/summary.json"
if [[ "$preserved_failure_tree" == false ]]; then
  awk '{ line[NR]=$0; low=tolower($0); if (!ready && low ~ /application startup complete/) ready=NR;
    if (!stop && low ~ /\[shutdown\]|shutting down/) stop=NR;
    if (low ~ /warning|error|exception|traceback/) keep[NR]=1 }
    END { end=ready ? ready : NR; if (end>NR) end=NR; for(i=1;i<=end;i++) keep[i]=1;
      start=NR-199; if(start<1) start=1; for(i=start;i<=NR;i++) keep[i]=1;
      if(stop) for(i=stop;i<=NR;i++) keep[i]=1; for(i=1;i<=NR;i++) if(keep[i]) print line[i] }
  ' "$source_abs/raw/server/server.log" >"$destination_abs/raw/server/server.log"
fi
fi
structure_code='import hashlib,json,sys,yaml; from pathlib import Path; root=Path(sys.argv[1])
shape=lambda value: ["dict",[(key,shape(value[key])) for key in sorted(value)]] if isinstance(value,dict) else ["list",[shape(item) for item in value]] if isinstance(value,list) else type(value).__name__
load=lambda path: yaml.safe_load(path.read_text()) if path.suffix in {".yaml",".yml"} else json.loads(path.read_text()) if path.suffix==".json" else [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def safe_shape(path):
 try: return ["parsed",shape(load(path))]
 except (json.JSONDecodeError,yaml.YAMLError,UnicodeDecodeError): return ["unparseable"]
paths=sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in {".json",".jsonl",".yaml",".yml"}); value=[(str(path.relative_to(root)),safe_shape(path)) for path in paths]; print(hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest())'
structure_before="$(python3 -c "$structure_code" "$destination_abs")"
find "$destination_abs" -type f -print0 |
while IFS= read -r -d '' file; do
  if LC_ALL=C grep -Iq '' "$file"; then
    for literal in "${private_literals[@]}"; do
      replacement='<PRIVATE_LITERAL>'
      [[ "$literal" == "$fqdn_hostname" || "$literal" == "$short_hostname" ]] && replacement='<HOSTNAME>'
      [[ "$literal" == "$current_home" ]] && replacement='<HOME>'
      LITERAL="$literal" REPLACEMENT="$replacement" perl -pi -e 's/\Q$ENV{LITERAL}\E/$ENV{REPLACEMENT}/g' "$file"
    done
    perl -MSocket=AF_INET,AF_INET6,inet_pton -pi -e '
      s{(?<![A-Za-z0-9_.-])/(?:home|Users)/[^/\s]+}{<HOME>}g; s{(?<![A-Za-z0-9_.-])/root(?=/|\s|$)}{<HOME>}g;
      s{(?<![A-Za-z0-9_.-])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![A-Za-z0-9_.-])}{<MAC>}g;
      s{(?<![A-Za-z0-9_.-])((?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?)(?![A-Za-z0-9_.-])}{my $c=$1;(my $a=$c)=~s{/\d{1,2}$}{};my $safe=($a eq "0.0.0.0"||$a=~/^127\./||$a=~/^192\.0\.2\./||$a=~/^198\.51\.100\./||$a=~/^203\.0\.113\./);defined(inet_pton(AF_INET,$a))&&!$safe?"<IPV4>":$c}ge;
      s{(?<![A-Za-z0-9_.-])([0-9A-Fa-f:]*:[0-9A-Fa-f:]+(?:%[A-Za-z0-9_.-]+)?(?:/\d{1,3})?)(?![A-Za-z0-9_.-])}{my $c=$1;(my $a=$c)=~s{/\d{1,3}$}{};$a=~s{%[A-Za-z0-9_.-]+$}{};my $safe=($a eq "::"||$a eq "::1"||$a=~/^2001:0*db8(?::|$)/i);defined(inet_pton(AF_INET6,$a))&&!$safe?"<IPV6>":$c}ge;
    ' "$file"
  fi
done
structure_after="$(python3 -c "$structure_code" "$destination_abs")"
[[ "$structure_after" == "$structure_before" ]] || { echo "Redaction changed structured evidence keys or types" >&2; exit 3; }
if ! scan_tree "$destination_abs" "public copy"; then
  echo "Public copy contains suspected secrets. Do not publish it." >&2
  exit 3
fi
trap - ERR
echo "Sanitized public copy created: $destination_abs"
[[ "$preserved_failure_tree" == true ]] && echo "Failure evidence was preserved in full; repository hygiene may fail."
echo "Manual privacy review is still required before commit."
