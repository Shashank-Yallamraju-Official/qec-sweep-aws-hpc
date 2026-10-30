#!/usr/bin/env bash
# Submits the whole grid as one Slurm array, and a sync job that runs when it is done.
# usage: sweep.sh <image uri> s3://bucket/prefix [queue] [nodes]
# Each run records what it used in run.json, which is what it gets costed from.
set -euo pipefail
image_uri=$1 destination=${2%/} queue=${3:-sweep} nodes=${4:-}
jobs=$(cd "$(dirname "$0")" && pwd)
# Keyed by user so two people's runs never contend for one directory.
run_dir=/scratch/$USER/sweep/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir/cells" "$run_dir/logs"
apptainer pull --force "$run_dir/sweep.sif" "$image_uri"
# The array is exactly as large as the grid inside the image, never a number kept by hand.
last=$(apptainer exec "$run_dir/sweep.sif" python -c 'from sweep.grid import GRID; print(len(GRID) - 1)')
# A node count pins the run to that many nodes: the rest of the queue is excluded, and
# concurrency is capped at two tasks per c7a.large so those nodes are full, not spread thin.
# (--nodelist would do the opposite: it makes every task hold the whole list.)
range="0-$last"
pin=()
if [[ -n $nodes ]]; then
  [[ $nodes =~ ^[1-9][0-9]*$ ]] || { echo "nodes must be a positive integer, not '$nodes'" >&2; exit 2; }
  range="$range%$((nodes * 2))"
  queue_size=$(sinfo -p "$queue" -h -N -o %N | wc -l)
  (( nodes < queue_size )) && pin=(--exclude "$queue-dy-c7a-[$((nodes + 1))-$queue_size]")
fi
jq -n --arg run "$(basename "$run_dir")" --arg queue "$queue" --arg nodes "$nodes" --arg image "$image_uri" \
  --arg submitted "$(date -u +%FT%TZ)" \
  '{run: $run, queue: $queue, nodes: ($nodes | if . == "" then null else tonumber end),
    instance_type: "c7a.large", image: $image, submitted: $submitted}' > "$run_dir/run.json"
array=$(sbatch --parsable --partition "$queue" --array="$range" "${pin[@]+"${pin[@]}"}" \
  --export="ALL,RUN_DIR=$run_dir,SWEEP_IMAGE=$run_dir/sweep.sif" \
  --output "$run_dir/logs/%a.out" "$jobs/sweep.sbatch")
sync=$(sbatch --parsable --partition "$queue" --dependency="afterany:$array" \
  --export="ALL,RUN_DIR=$run_dir,DESTINATION=$destination,QUEUE=$queue" \
  --output "$run_dir/logs/sync.out" "$jobs/sync.sbatch")
echo "$run_dir array=$array sync=$sync"
