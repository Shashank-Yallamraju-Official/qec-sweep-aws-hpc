#!/usr/bin/env bash
# Submits the whole grid as one Slurm array, and a sync job that runs when it is done.
# usage: sweep.sh <image uri> s3://bucket/prefix
set -euo pipefail
image_uri=$1 destination=${2%/}
jobs=$(cd "$(dirname "$0")" && pwd)
# Keyed by user so two people's runs never contend for one directory.
run_dir=/scratch/$USER/sweep/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir/cells" "$run_dir/logs"
apptainer pull --force "$run_dir/sweep.sif" "$image_uri"
# The array is exactly as large as the grid inside the image, never a number kept by hand.
last=$(apptainer exec "$run_dir/sweep.sif" python -c 'from sweep.grid import GRID; print(len(GRID) - 1)')
array=$(sbatch --parsable --array="0-$last" \
  --export="ALL,RUN_DIR=$run_dir,SWEEP_IMAGE=$run_dir/sweep.sif" \
  --output "$run_dir/logs/%a.out" "$jobs/sweep.sbatch")
sync=$(sbatch --parsable --dependency="afterany:$array" \
  --export="ALL,RUN_DIR=$run_dir,DESTINATION=$destination" \
  --output "$run_dir/logs/sync.out" "$jobs/sync.sbatch")
echo "$run_dir array=$array sync=$sync"
