#!/usr/bin/env bash
# One array task decodes one named cell with the sweep command inside the image, which
# is the training one when the decoder is the learned one; the task index picks the
# cell, and the cell's distance picks the model.
# The submitter sets --array, RUN_DIR, SWEEP_IMAGE, CELLS, SHOTS, SEED, NOISE, DECODER,
# MODELS and --output; see evaluate.sh.
#SBATCH --job-name=evaluate
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
set -euo pipefail
: "${RUN_DIR:?}" "${SWEEP_IMAGE:?}" "${CELLS:?}" "${SHOTS:?}" "${SEED:?}" "${NOISE:?}" "${DECODER:?}" "${MODELS?}"
read -r -a cells <<<"$CELLS"
cell=${cells[SLURM_ARRAY_TASK_ID]}
choice=()
if [[ $DECODER != pymatching ]]; then
  for pair in $MODELS; do
    [[ ${pair%%=*} == "${cell%%:*}" ]] && choice=(--decoder "$DECODER" --model "${pair#*=}")
  done
fi
# Each node leaves a marker, so the run's record counts the nodes it actually used.
mkdir -p "$RUN_DIR/nodes" && touch "$RUN_DIR/nodes/$SLURMD_NODENAME"
apptainer exec --bind /scratch "$SWEEP_IMAGE" sweep --d "${cell%%:*}" --p "${cell#*:}" --shots "$SHOTS" \
  --seed "$SEED" --noise "$NOISE" "${choice[@]+"${choice[@]}"}" --out "$RUN_DIR/cells"
