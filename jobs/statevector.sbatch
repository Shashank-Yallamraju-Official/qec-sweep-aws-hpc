#!/usr/bin/env bash
# Runs the brickwork circuit across the allocation, every rank inside the mpi image.
# The submitter sets IMAGE, QUBITS, LAYERS and OUT; see strong-scaling.sh.
#SBATCH --job-name=statevector
#SBATCH --partition=mpi
#SBATCH --exclusive
#SBATCH --time=00:30:00
# 64 of the 96 cores: the rank count must be a power of two, so each node takes one.
#SBATCH --ntasks-per-node=64
set -euo pipefail
: "${IMAGE:?}" "${QUBITS:?}" "${LAYERS:?}" "${OUT:?}"
# The host's launcher starts the ranks; the image carries the same Open MPI, so they meet.
export PATH=/opt/amazon/openmpi/bin:$PATH
mpirun --bind-to core apptainer exec --bind /scratch "$IMAGE" \
  statevector --qubits "$QUBITS" --layers "$LAYERS" --out "$OUT"
