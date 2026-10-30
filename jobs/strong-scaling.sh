#!/usr/bin/env bash
# Runs one circuit at each node count in turn and copies the records to S3.
# usage: strong-scaling.sh <image uri> s3://bucket/prefix <qubits> <layers> <nodes>...
set -euo pipefail
image_uri=$1 destination=${2%/} qubits=$3 layers=$4
shift 4
jobs=$(cd "$(dirname "$0")" && pwd)
run_dir=/scratch/$USER/statevector/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir"
apptainer pull --force "$run_dir/mpi.sif" "$image_uri"
for nodes in "$@"; do
  # --wait holds until the job ends, so no two runs share nodes or the network.
  sbatch --wait --nodes "$nodes" --output "$run_dir/nodes$nodes.out" \
    --export="ALL,IMAGE=$run_dir/mpi.sif,QUBITS=$qubits,LAYERS=$layers,OUT=$run_dir/nodes$nodes.json" \
    "$jobs/statevector.sbatch"
  echo "$nodes nodes: $(jq -c .seconds "$run_dir/nodes$nodes.json")"
done
aws s3 cp --quiet --recursive --exclude mpi.sif "$run_dir" "$destination/$(basename "$run_dir")/"
echo "$run_dir"
