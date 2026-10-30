#!/usr/bin/env bash
# Runs the grid at 1, 4, 8 and 16 spot nodes, one run after another, for the weak-scaling table.
# usage: weak-scaling.sh <image uri> s3://bucket/prefix
set -euo pipefail
image_uri=$1 destination=$2
jobs=$(cd "$(dirname "$0")" && pwd)
for nodes in 1 4 8 16; do
  out=$("$jobs/sweep.sh" "$image_uri" "$destination" sweep-spot "$nodes")
  echo "$nodes nodes: $out"
  sync=${out##*sync=}
  run_dir=${out%% *}
  # One run at a time, so each run's record describes only its own nodes.
  while squeue -h -j "$sync" 2>/dev/null | grep -q .; do sleep 20; done
  # Slurm forgets a finished job quickly; the record it was meant to close is the proof.
  grep -q '"finished"' "$run_dir/run.json" || { echo "run $run_dir did not close its record" >&2; exit 1; }
done
