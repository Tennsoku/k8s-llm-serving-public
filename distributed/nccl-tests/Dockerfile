# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=nvcr.io/nvidia/pytorch@sha256:7531d90bcbe0e43e1f7363029c7e145ce90eebeb494a7b4695fdba0329d7c3c3
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# 固定 nccl-tests revision: NCCL_TESTS_VERSION 2.19.6
ARG NCCL_TESTS_REPO=https://github.com/NVIDIA/nccl-tests.git
ARG NCCL_TESTS_REF=a0b82b2260cf5152b9f8c061bbf7eaf0ba096432 

ENV CUDA_HOME=/usr/local/cuda \
    NCCL_HOME=/usr \
    NCCL_TESTS_HOME=/opt/nccl-tests \
    DEBIAN_FRONTEND=noninteractive

# OpenMPI runtime + development headers.
# openssh-client 仅用于 mpirun 远程启动；镜像本身暂不启动 sshd。
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        openmpi-bin \
        libopenmpi-dev \
        openssh-client \
        iproute2 \
        net-tools \
        pciutils \
        rdma-core \
        ibverbs-utils \
        libibverbs-dev \
        librdmacm-dev \
        && \
    rm -rf /var/lib/apt/lists/*

# 在构建前输出工具链信息，方便 CI/build log 留证。
RUN set -eux; \
    uname -m; \
    test -x "${CUDA_HOME}/bin/nvcc"; \
    "${CUDA_HOME}/bin/nvcc" --version; \
    command -v mpirun; \
    command -v mpicc; \
    command -v mpicxx; \
    mpirun --version; \
    mpicc --showme:version; \
    mpicxx --showme:compile; \
    mpicxx --showme:link

RUN git clone "${NCCL_TESTS_REPO}" "${NCCL_TESTS_HOME}" && \
    cd "${NCCL_TESTS_HOME}" && \
    git checkout "${NCCL_TESTS_REF}" && \
    git rev-parse HEAD > /opt/nccl-tests-revision.txt

WORKDIR ${NCCL_TESTS_HOME}

# Ubuntu apt 安装的 OpenMPI 使用 /usr 作为逻辑安装前缀。
# NAME_SUFFIX 可以明确区分 MPI-enabled binaries。
RUN make -j"$(nproc)" \
      MPI=1 \
      MPI_HOME=/usr \
      CUDA_HOME="${CUDA_HOME}" \
      NCCL_HOME="${NCCL_HOME}" \
      NAME_SUFFIX=_mpi

# 构建期断言：避免镜像虽然 build 成功，却没有生成 MPI binary。
RUN set -eux; \
    test -x build/all_reduce_perf_mpi; \
    test -x build/all_gather_perf_mpi; \
    ldd build/all_reduce_perf_mpi; \
    ldd build/all_reduce_perf_mpi | grep -E 'libmpi|libnccl|libcudart'

COPY scripts/verify-mpi.sh /usr/local/bin/verify-mpi
RUN chmod +x /usr/local/bin/verify-mpi

ENTRYPOINT ["/bin/bash"]