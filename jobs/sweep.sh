#!/usr/bin/env bash
# Submits the whole grid as one Slurm array.
# usage: sweep.sh <image uri>
set -euo pipefail
image_uri=$1
jobs=$(cd "$(dirname "$0")" && pwd)
run_dir=/scratch/sweep/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir/cells" "$run_dir/logs"
apptainer pull --force "$run_dir/sweep.sif" "$image_uri"
array=$(sbatch --parsable --export="ALL,RUN_DIR=$run_dir,SWEEP_IMAGE=$run_dir/sweep.sif" \
  --output "$run_dir/logs/%a.out" "$jobs/sweep.sbatch")
echo "$run_dir array=$array"
