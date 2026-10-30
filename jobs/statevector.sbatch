#!/usr/bin/env bash
# Runs the brickwork circuit across the allocation, every rank inside the mpi image.
# The submitter sets --partition, --nodes, --ntasks-per-node, IMAGE, QUBITS, LAYERS
# and OUT; see strong-scaling.sh.
#SBATCH --job-name=statevector
#SBATCH --exclusive
#SBATCH --time=00:30:00
set -euo pipefail
: "${IMAGE:?}" "${QUBITS:?}" "${LAYERS:?}" "${OUT:?}"
# The host's launcher starts the ranks; the image carries the same Open MPI, so they meet.
export PATH=/opt/amazon/openmpi/bin:$PATH
# Each rank is its own container in its own user namespace, so a rank cannot read
# a neighbour's memory directly; left to try, the shared-memory transports hang.
export OMPI_MCA_btl_vader_single_copy_mechanism=none FI_SHM_DISABLE_CMA=1
mpirun --bind-to core apptainer exec --bind /scratch "$IMAGE" \
  statevector --qubits "$QUBITS" --layers "$LAYERS" --out "$OUT"
