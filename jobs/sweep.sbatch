#!/usr/bin/env bash
# One array task decodes one grid cell inside the image; the task index picks the cell.
# The submitter sets --array, RUN_DIR, SWEEP_IMAGE and --output; see sweep.sh.
#SBATCH --job-name=sweep
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
set -euo pipefail
: "${RUN_DIR:?}" "${SWEEP_IMAGE:?}"
# Each node leaves a marker, so the run's record counts the nodes it actually used.
mkdir -p "$RUN_DIR/nodes" && touch "$RUN_DIR/nodes/$SLURMD_NODENAME"
apptainer run --bind /scratch "$SWEEP_IMAGE" --index "$SLURM_ARRAY_TASK_ID" --out "$RUN_DIR/cells"
