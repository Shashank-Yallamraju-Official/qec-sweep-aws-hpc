#!/usr/bin/env bash
# One job trains the decoder inside the image on whole nodes, one rank per node; torch
# uses every core of each. The ranks meet at the first node's address.
# The submitter sets --nodes, RUN_DIR, TRAIN_IMAGE, SAMPLES, SEED, EPOCHS, LEARNING_RATE,
# DEVICE and --output; see train.sh.
#SBATCH --job-name=train
#SBATCH --ntasks-per-node=1
#SBATCH --exclusive
#SBATCH --time=04:00:00
set -euo pipefail
: "${RUN_DIR:?}" "${TRAIN_IMAGE:?}" "${SAMPLES:?}" "${SEED:?}" "${EPOCHS:?}" "${LEARNING_RATE:?}" "${DEVICE:?}"
mkdir -p "$RUN_DIR/nodes"
MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -1)
export MASTER_ADDR MASTER_PORT=29500
# Each node leaves a marker, so the run's record counts the nodes it actually used.
# shellcheck disable=SC2016 # the quoted script expands on each node, not here
srun bash -c 'touch "$RUN_DIR/nodes/$SLURMD_NODENAME"
  RANK=$SLURM_PROCID WORLD_SIZE=$SLURM_NTASKS exec apptainer exec --bind /scratch "$TRAIN_IMAGE" \
    decoder-train --samples "$SAMPLES" --out "$RUN_DIR/model" \
    --seed "$SEED" --epochs "$EPOCHS" --learning-rate "$LEARNING_RATE" --device "$DEVICE"'
