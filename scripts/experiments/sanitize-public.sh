#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <private-source> <public-destination> [--literal <value>]..." >&2
}

valid_literal() {
  local value="$1"
  [[ ${#value} -ge 4 && "$value" != "/" && "$value" != "." && "$value" != ".." &&
     "$value" != *$'\n'* && "$value" != *$'\r'* ]]
}

if (( $# < 2 )); then
  usage
  exit 2
fi

source_dir="$1"
destination="$2"
shift 2

declare -a configured_literals=()
while (( $# > 0 )); do
  if [[ "$1" != "--literal" || $# -lt 2 ]] || ! valid_literal "$2"; then
    usage
    exit 2
  fi
  configured_literals+=("$2")
  shift 2
done

if [[ ! -d "$source_dir" || -L "$source_dir" ]]; then
  echo "Private source must be a real directory: $source_dir" >&2
  exit 2
fi
if [[ -e "$destination" || -L "$destination" ]]; then
  echo "Public destination already exists: $destination" >&2
  exit 2
fi
if ! perl -MSocket=AF_INET,AF_INET6,inet_pton -e 1 2>/dev/null; then
  echo "Perl Socket support is required" >&2
  exit 2
fi

source_abs="$(realpath -e -- "$source_dir")"
destination_abs="$(realpath -m -- "$destination")"
case "$destination_abs" in
  "$source_abs"|"$source_abs"/*)
    echo "Public destination must not be inside the private source" >&2
    exit 2
    ;;
esac

if ! find "$source_abs" -mindepth 1 -print0 >/dev/null; then
  echo "Private source cannot be traversed safely" >&2
  exit 2
fi
if [[ -n "$(find "$source_abs" -mindepth 1 ! -type f ! -type d -print -quit)" ]]; then
  echo "Private source must contain only readable regular files and directories" >&2
  exit 2
fi
if [[ -n "$(find "$source_abs" -type f ! -readable -print -quit)" ]]; then
  echo "Private source contains an unreadable file" >&2
  exit 2
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
for literal in "${configured_literals[@]}"; do
  add_literal "$literal"
done

secret_pattern='(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|sk_(live|test)_[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9-]{16,}|AIza[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|Authorization[[:space:]]*[:=][[:space:]]*(Basic|Bearer)[[:space:]]+[A-Za-z0-9._~+/-]{12,}|Bearer[[:space:]]+[A-Za-z0-9._~+/-]{16,}|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|https?://[^/@[:space:]]+:[^/@[:space:]]+@|(^|[^A-Za-z0-9_])(password|passwd|token|secret|api[_-]?key|aws_secret_access_key|aws_session_token|hf_token|ngc_api_key|auth|docker_auth_config|identitytoken|registrytoken)[^A-Za-z0-9_]*[:=][[:space:]]*[^[:space:],}]{8,}|(^|[[:space:]])--?(password|passwd|token|secret|api[-_]?key|hf[-_]?token|ngc[-_]?api[-_]?key|aws[-_]?session[-_]?token)[=[:space:]]+[^[:space:]]{8,})'

scan_tree() {
  local root="$1" label="$2" item relative relative_lower basename_lower literal scan_status
  local suspected=0
  while IFS= read -r -d '' item; do
    relative="${item#"$root"/}"
    relative_lower="${relative,,}"
    basename_lower="${item##*/}"
    basename_lower="${basename_lower,,}"

    case "$basename_lower" in
      .env|.env.*|id_rsa|id_dsa|id_ecdsa|id_ed25519|*.pem|*.key|.netrc|.npmrc|.pypirc|known_hosts|authorized_keys|credentials|credentials.json|auth.json|docker-config.json)
        echo "Suspected credential file under $label" >&2
        suspected=1
        ;;
    esac
    case "/$relative_lower" in
      */.docker/config.json|*/.docker/auth.json|*/.ssh/config|*/.ssh/known_hosts|*/.ssh/authorized_keys)
        echo "Suspected credential path under $label" >&2
        suspected=1
        ;;
    esac

    if LC_ALL=C grep -Eqi -- "$secret_pattern" <<<"$relative"; then
      echo "Suspected secret pattern in a path under $label" >&2
      suspected=1
    else
      scan_status=$?
      (( scan_status <= 1 )) || suspected=1
    fi
    for literal in "${private_literals[@]}"; do
      if [[ "$relative" == *"$literal"* ]]; then
        echo "Private identifier found in a path under $label; rename it before publication" >&2
        suspected=1
        break
      fi
    done

    if [[ -f "$item" ]]; then
      if LC_ALL=C grep -aEqi -- "$secret_pattern" "$item"; then
        echo "Suspected secret pattern in $label: $relative" >&2
        suspected=1
      else
        scan_status=$?
        (( scan_status <= 1 )) || suspected=1
      fi
    fi
  done < <(find "$root" -mindepth 1 -print0)
  (( suspected == 0 ))
}

if LC_ALL=C grep -Eqi -- "$secret_pattern" <<<"$destination"; then
  echo "Public destination contains a suspected secret pattern" >&2
  exit 3
fi
if ! scan_tree "$source_abs" "private source"; then
  echo "No public copy was created. Review the private source before publication." >&2
  exit 3
fi

mkdir -p -- "$(dirname -- "$destination_abs")"
trap 'echo "Sanitization failed; treat any created public copy as unsafe." >&2' ERR
cp -R -- "$source_abs" "$destination_abs"

while IFS= read -r -d '' file; do
  # NUL-containing files are copied unchanged; the secret scan still reads them as bytes.
  if LC_ALL=C grep -Iq '' "$file"; then
    for literal in "${private_literals[@]}"; do
      replacement='<PRIVATE_LITERAL>'
      if [[ "$literal" == "$fqdn_hostname" || "$literal" == "$short_hostname" ]]; then
        replacement='<HOSTNAME>'
      elif [[ "$literal" == "$current_home" ]]; then
        replacement='<HOME>'
      fi
      LITERAL="$literal" REPLACEMENT="$replacement" \
        perl -pi -e 's/\Q$ENV{LITERAL}\E/$ENV{REPLACEMENT}/g' "$file"
    done

    perl -MSocket=AF_INET,AF_INET6,inet_pton -pi -e '
      s{(?<![A-Za-z0-9_.-])/(?:home|Users)/[^/\s]+}{<HOME>}g;
      s{(?<![A-Za-z0-9_.-])/root(?=/|\s|$)}{<HOME>}g;
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
    ' "$file"
  fi
done < <(find "$destination_abs" -type f -print0)

if ! scan_tree "$destination_abs" "public copy"; then
  echo "Public copy was created, but suspected secrets require review. Do not publish it yet." >&2
  exit 3
fi

trap - ERR
echo "Sanitized public copy created: $destination_abs"
echo "Manual privacy review is still required before commit."
