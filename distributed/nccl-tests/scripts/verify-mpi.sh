#!/usr/bin/env bash
set -Eeuo pipefail

MPI_HOME="${MPI_HOME:-/usr/local/mpi}"

echo "MPI_HOME=${MPI_HOME}"
echo "OPAL_PREFIX=${OPAL_PREFIX:-<unset>}"

expected_mpi_home="$(readlink -f "${MPI_HOME}")"
mpi_header="$(readlink -f "${MPI_HOME}/include/mpi.h")"
mpi_library="$(readlink -f "${MPI_HOME}/lib/libmpi.so")"
mpicxx_binary="$(readlink -f "$(command -v mpicxx)")"
mpirun_binary="$(readlink -f "$(command -v mpirun)")"

printf '%-18s %s\n' \
  "MPI home:" "${expected_mpi_home}" \
  "MPI header:" "${mpi_header}" \
  "MPI library:" "${mpi_library}" \
  "mpicxx:" "${mpicxx_binary}" \
  "mpirun:" "${mpirun_binary}"

mpirun --version
mpicxx --showme:version
mpicxx --showme:compile
mpicxx --showme:link

case "${mpi_header}" in
  *"/ompi5/"*) ;;
  *)
    echo "ERROR: mpi.h is not from HPC-X Open MPI 5."
    exit 1
    ;;
esac

case "${mpi_library}" in
  *"/ompi5/"*) ;;
  *)
    echo "ERROR: libmpi.so is not from HPC-X Open MPI 5."
    exit 1
    ;;
esac

echo "HPC-X Open MPI 5 environment is consistent."
