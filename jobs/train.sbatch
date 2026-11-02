#!/usr/bin/env bash
# One job trains the decoder inside the image on a whole node; torch uses every core.
# The submitter sets RUN_DIR, TRAIN_IMAGE, SAMPLES, SEED, EPOCHS, LEARNING_RATE, DEVICE
# and --output; see train.sh.
#SBATCH --job-name=train
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=04:00:00
set -euo pipefail
: "${RUN_DIR:?}" "${TRAIN_IMAGE:?}" "${SAMPLES:?}" "${SEED:?}" "${EPOCHS:?}" "${LEARNING_RATE:?}" "${DEVICE:?}"
# The node leaves a marker, so the run's record counts the nodes it actually used.
mkdir -p "$RUN_DIR/nodes" && touch "$RUN_DIR/nodes/$SLURMD_NODENAME"
apptainer exec --bind /scratch "$TRAIN_IMAGE" decoder-train --samples "$SAMPLES" --out "$RUN_DIR/model" \
  --seed "$SEED" --epochs "$EPOCHS" --learning-rate "$LEARNING_RATE" --device "$DEVICE"
