#!/usr/bin/env bash
# One array task samples one chunk of one cell inside the image; the task index picks both.
# The submitter sets --array, RUN_DIR, SAMPLE_IMAGE, CELLS, SHOTS, CHUNKS, SEED, NOISE and
# --output; see generate.sh.
#SBATCH --job-name=generate
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
set -euo pipefail
: "${RUN_DIR:?}" "${SAMPLE_IMAGE:?}" "${CELLS:?}" "${SHOTS:?}" "${CHUNKS:?}" "${SEED:?}" "${NOISE:?}"
read -r -a cells <<<"$CELLS"
cell=${cells[SLURM_ARRAY_TASK_ID / CHUNKS]}
chunk=$((SLURM_ARRAY_TASK_ID % CHUNKS))
# Each node leaves a marker, so the run's record counts the nodes it actually used.
mkdir -p "$RUN_DIR/nodes" && touch "$RUN_DIR/nodes/$SLURMD_NODENAME"
apptainer exec --bind /scratch "$SAMPLE_IMAGE" decoder-sample --d "${cell%%:*}" --p "${cell#*:}" \
  --shots "$SHOTS" --seed $((SEED + chunk)) --noise "$NOISE" --out "$RUN_DIR/samples"
