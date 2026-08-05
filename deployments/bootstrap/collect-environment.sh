#!/usr/bin/env bash
set -Eeuo pipefail

NODE_NAME="${NODE_NAME:-$(hostname)}"
OUTPUT_DIR="${OUTPUT_DIR:-docs/environment/fingerprints}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_FILE="${OUTPUT_DIR}/${NODE_NAME}-${TIMESTAMP}.txt"

mkdir -p "${OUTPUT_DIR}"

run_section() {
    local title="$1"
    shift

    {
        echo
        echo "================================================================"
        echo "${title}"
        echo "================================================================"
        "$@" 2>&1 || echo "[WARN] Command failed: $*"
    } >>"${OUTPUT_FILE}"
}

{
    echo "Environment Fingerprint"
    echo "Generated UTC: $(date -u --iso-8601=seconds)"
    echo "Node: ${NODE_NAME}"
} >"${OUTPUT_FILE}"

run_section "Hostname" hostnamectl
run_section "Kernel" uname -a
run_section "Architecture" uname -m
run_section "OS Release" cat /etc/os-release
run_section "CPU" lscpu
run_section "Memory" free -h
run_section "Block Devices" lsblk -o NAME,MODEL,SIZE,TYPE,FSTYPE,MOUNTPOINTS
run_section "Filesystem" df -hT
run_section "PCI Devices" lspci -nn
run_section "Network Addresses" ip -brief address
run_section "Network Links" ip -details link
run_section "NVIDIA SMI" nvidia-smi
run_section "NVIDIA SMI Query" \
    nvidia-smi --query-gpu=name,uuid,driver_version,memory.total,memory.used \
    --format=csv,noheader
run_section "CUDA Compiler" nvcc --version
run_section "Docker" docker version
run_section "Docker Info" docker info
run_section "Containerd" containerd --version
run_section "NVIDIA Container CLI" nvidia-container-cli info
run_section "Python" python3 --version
run_section "Installed NVIDIA Packages" \
    bash -c "dpkg-query -W | grep -Ei 'nvidia|cuda|nccl|container' || true"
run_section "APT Sources" \
    bash -c "grep -RhvE '^[[:space:]]*(#|$)' /etc/apt/sources.list /etc/apt/sources.list.d 2>/dev/null || true"
run_section "Git Status" git status --short

echo "Environment fingerprint written to ${OUTPUT_FILE}"