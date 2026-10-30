#!/usr/bin/env bash
# Runs one circuit at each node count in turn and copies the records to S3.
# usage: strong-scaling.sh <image uri> s3://bucket/prefix <queue> <ranks per node> <qubits> <layers> <nodes>...
# Ranks per node is a power of two, 64 of an hpc6a's 96 cores, so the rank count stays one.
set -euo pipefail
image_uri=$1 destination=${2%/} queue=$3 ranks=$4 qubits=$5 layers=$6
shift 6
jobs=$(cd "$(dirname "$0")" && pwd)
run_dir=/scratch/$USER/statevector/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir"
apptainer pull --force "$run_dir/mpi.sif" "$image_uri"
for nodes in "$@"; do
  # --wait holds until the job ends, so no two runs share nodes or the network.
  sbatch --wait --partition "$queue" --nodes "$nodes" --ntasks-per-node "$ranks" \
    --output "$run_dir/nodes$nodes.out" \
    --export="ALL,IMAGE=$run_dir/mpi.sif,QUBITS=$qubits,LAYERS=$layers,OUT=$run_dir/nodes$nodes.json" \
    "$jobs/statevector.sbatch"
  echo "$nodes nodes: $(jq -c .seconds "$run_dir/nodes$nodes.json")"
done
aws s3 cp --quiet --recursive --exclude mpi.sif "$run_dir" "$destination/$(basename "$run_dir")/"
echo "$run_dir"
