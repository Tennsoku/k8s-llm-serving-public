#!/usr/bin/env bash
# Pinned CLI: kubectl v1.36.4. Run from any directory; evidence stays private.
set -euo pipefail
umask 077

if [[ "${1:-}" == --help ]]; then
  echo "Usage: bash $0 <new-run-id> <node-a> <node-b>"
  echo "Creates two CPU-only Pods and two Services; deletes its namespace on success."
  echo "On failure, retains the namespace and captures diagnostics. Use a new run ID to retry."
  exit 0
fi
if (( $# != 3 )); then
  echo "Usage: bash $0 <new-run-id> <node-a> <node-b>" >&2
  exit 2
fi
run_id=$1
node_a=$2
node_b=$3
if [[ ! $run_id =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ || ${#run_id} -gt 56 ]]; then
  echo "run-id must be a lowercase DNS label of at most 56 characters" >&2
  exit 2
fi
for node in "$node_a" "$node_b"; do
  if [[ ! $node =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ || ${#node} -gt 253 ]]; then
    echo "Invalid node name: $node" >&2
    exit 2
  fi
done
if [[ $node_a == "$node_b" ]]; then
  echo "Two distinct nodes are required for cross-node checks" >&2
  exit 2
fi

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$repo"
context=$(kubectl config current-context)
namespace="n2n-net-$run_id"
run="artifacts/private/network/$run_id"
raw="$run/raw"
image='registry.k8s.io/e2e-test-images/agnhost@sha256:a62f40481e05709988fe44e5035b2e0f553cd52bf0ae4e83614928255b00e8c1'
capture=(bash "$repo/scripts/experiments/capture-command.sh" "$raw")
k=(kubectl --context="$context" --namespace="$namespace" --request-timeout=15s)
# mkdir deliberately refuses to overwrite an existing run.
mkdir -p artifacts/private/network
mkdir "$run"
mkdir "$raw" "$run/derived"
started=$(date -u +%FT%TZ)
commit=$(git rev-parse HEAD)
dirty=false
[[ -z $(git status --porcelain) ]] || dirty=true
cat > "$run/run.yaml" <<META
run_id: "$run_id"
milestone: null
experiment: bidirectional-pod-service-dns
timestamp_utc: "$started"
git: {commit: "$commit", dirty: $dirty}
environment: {node: [node-a, node-b]}
runtime: {image: "$image"}
workload: {directions: 2, paths_per_direction: 3}
outcome: running
META
namespace_created=false
trap '
  rc=$?
  trap - EXIT
  if (( rc != 0 )); then
    sed -i "s/^outcome: running$/outcome: failed/" "$run/run.yaml"
    echo "Replay failed (exit $rc); evidence: $run" >&2
    if [[ $namespace_created == true ]]; then
      for resource in pods services endpointslices events; do
        "${capture[@]}" "failure-$resource" -- "${k[@]}" get "$resource" -o yaml ||
          echo "Diagnostic capture failed: $resource; inspect its stderr/exit-code" >&2
      done
      "${capture[@]}" failure-describe -- "${k[@]}" describe pods || echo "Pod describe failed" >&2
      for side in a b; do
        "${capture[@]}" "failure-log-$side" -- "${k[@]}" logs "net-$side" --timestamps=true ||
          echo "Log capture failed: net-$side" >&2
      done
      printf "Namespace retained. After review, cleanup: kubectl --context=%q delete namespace %q\n" "$context" "$namespace" >&2
    fi
  else
    sed -i "s/^outcome: running$/outcome: success/" "$run/run.yaml"
  fi
  printf "finished_utc: \"%s\"\n" "$(date -u +%FT%TZ)" >> "$run/run.yaml"
  exit "$rc"
' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"${capture[@]}" run-start -- date -u +%FT%TZ
"${capture[@]}" context -- printf '%s\n' "$context"
"${capture[@]}" client-host -- hostname
"${capture[@]}" client-version -- kubectl version --client -o yaml
"${capture[@]}" git-status -- git status --short
"${capture[@]}" nodes -- "${k[@]}" get node "$node_a" "$node_b" -o yaml
"${capture[@]}" namespace-create -- "${k[@]}" create namespace "$namespace"
namespace_created=true

for side in a b; do
  node=$node_a
  [[ $side == a ]] || node=$node_b
  pod="net-$side"
  overrides=$(printf '{"spec":{"automountServiceAccountToken":false,"nodeSelector":{"kubernetes.io/hostname":"%s"},"tolerations":[{"key":"node-role.kubernetes.io/control-plane","operator":"Exists","effect":"NoSchedule"}],"containers":[{"name":"%s","image":"%s","args":["serve-hostname","--port=8080"],"readinessProbe":{"httpGet":{"path":"/","port":8080}}}]}}' "$node" "$pod" "$image")
  "${capture[@]}" "$pod-input" -- "${k[@]}" run "$pod" --image="$image" \
    --restart=Never --labels="app=$pod" --overrides="$overrides" --dry-run=client -o yaml
  "${capture[@]}" "$pod-create" -- "${k[@]}" create -f "$raw/$pod-input/stdout.log"
  "${capture[@]}" "$pod-service-input" -- "${k[@]}" create service clusterip "$pod" \
    --tcp=80:8080 --dry-run=client -o yaml
  "${capture[@]}" "$pod-service-create" -- "${k[@]}" create -f "$raw/$pod-service-input/stdout.log"
done

echo "Waiting for both HTTP servers to be Ready..."
"${capture[@]}" pods-ready -- timeout 660s "${k[@]}" --request-timeout=0 wait \
  --for=condition=Ready pod/net-a pod/net-b --timeout=300s
for side in a b; do
  "${capture[@]}" "net-$side-endpoints-ready" -- timeout 180s "${k[@]}" --request-timeout=0 wait \
    endpointslice -l "kubernetes.io/service-name=net-$side" --for=create \
    --for='jsonpath={.endpoints[0].conditions.ready}=true' --timeout=60s
  "${capture[@]}" "net-$side-pod-ip" -- "${k[@]}" get pod "net-$side" -o 'jsonpath={.status.podIP}'
  "${capture[@]}" "net-$side-service-ip" -- "${k[@]}" get service "net-$side" -o 'jsonpath={.spec.clusterIP}'
done
"${capture[@]}" resources-before -- "${k[@]}" get pods,services,endpointslices -o yaml

for source in a b; do
  target=b
  [[ $source == a ]] || target=a
  pod_ip=$(< "$raw/net-$target-pod-ip/stdout.log")
  service_ip=$(< "$raw/net-$target-service-ip/stdout.log")
  for route in pod service dns; do
    case $route in
      pod) url="http://$pod_ip:8080/" ;;
      service) url="http://$service_ip/" ;;
      dns) url="http://net-$target.$namespace.svc.cluster.local/" ;;
    esac
    echo "Checking $source -> $target via $route..."
    "${capture[@]}" "$source-to-$target-$route" -- "${k[@]}" exec "net-$source" -- sh -ec '
      response=$(curl --noproxy "*" -fsS --connect-timeout 2 --max-time 5 "$1")
      printf "%s\n" "$response"
      if [ "$response" != "$2" ]; then
        printf "Expected responder %s, got %s\n" "$2" "$response" >&2
        exit 1
      fi
    ' sh "$url" "net-$target"
  done
done

"${capture[@]}" resources-after -- "${k[@]}" get pods,services,endpointslices -o yaml
"${capture[@]}" events -- "${k[@]}" get events -o yaml
for side in a b; do
  "${capture[@]}" "net-$side-log" -- "${k[@]}" logs "net-$side" --timestamps=true
done
"${capture[@]}" namespace-delete -- timeout 240s "${k[@]}" --request-timeout=0 delete namespace \
  "$namespace" --wait=true --timeout=180s
namespace_created=false
"${capture[@]}" run-end -- date -u +%FT%TZ
echo "PASS: all six cross-node checks matched the expected responder. Evidence: $run"
