#!/usr/bin/env bash
# Runs one circuit at each node count in turn and copies the records to S3, with a
# run.json naming the image digest, the cluster configuration and each node count's job.
# usage: strong-scaling.sh [-p parent-run]... <image uri> s3://bucket/prefix <queue> <ranks per node> <qubits> <layers> <nodes>...
# Ranks per node is a power of two, 64 of an hpc6a's 96 cores, so the rank count stays one.
# A parent is a run this one answers to, such as the CPU run a GPU run is checked against.
set -euo pipefail
parents='[]'
while getopts 'p:' option; do
  case $option in
    p) parents=$(jq --arg parent "$OPTARG" '. + [$parent]' <<<"$parents") ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
image_uri=$1 destination=${2%/} queue=$3 ranks=$4 qubits=$5 layers=$6
shift 6
jobs=$(cd "$(dirname "$0")" && pwd)
run_dir=/scratch/$USER/statevector/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir"
read -r digest sif < <("$jobs/pull-image.sh" "$image_uri")
# The deploy workflow installs the scripts with the commit they came from beside them.
commit=$(cat "$jobs/COMMIT" 2>/dev/null || true)
config=/opt/parallelcluster/shared/cluster-config.yaml
config_hash='' idle=''
if [[ -f $config ]]; then
  config_hash=$(sha256sum "$config" | cut -c1-64)
  idle=$(sed -n 's/^ *ScaledownIdletime: *//p' "$config" | head -1)
fi
submitted=$(date -u +%FT%TZ)
job_ids='{}'
for nodes in "$@"; do
  # --wait holds until the job ends, so no two runs share nodes or the network.
  job=$(sbatch --wait --parsable --partition "$queue" --nodes "$nodes" --ntasks-per-node "$ranks" \
    --output "$run_dir/nodes$nodes.out" \
    --export="ALL,IMAGE=$sif,QUBITS=$qubits,LAYERS=$layers,OUT=$run_dir/nodes$nodes.json" \
    "$jobs/statevector.sbatch")
  job_ids=$(jq --arg n "$nodes" --argjson id "$job" '. + {($n): $id}' <<<"$job_ids")
  echo "$nodes nodes: $(jq -c .seconds "$run_dir/nodes$nodes.json")"
done
jq -n --arg run "$(basename "$run_dir")" --arg queue "$queue" --arg image "$image_uri" --arg digest "$digest" --arg commit "$commit" \
  --arg config_hash "$config_hash" --arg idle "$idle" --argjson ranks "$ranks" --argjson qubits "$qubits" --argjson layers "$layers" \
  --argjson jobs "$job_ids" --argjson parents "$parents" --arg submitted "$submitted" --arg finished "$(date -u +%FT%TZ)" \
  '{run: $run, queue: $queue, image: $image, image_digest: ($digest | if . == "" then null else . end),
    commit: ($commit | if . == "" then null else . end),
    cluster_config_sha256: ($config_hash | if . == "" then null else . end),
    scaledown_idle_minutes: ($idle | if . == "" then null else tonumber end),
    ranks_per_node: $ranks, qubits: $qubits, layers: $layers, jobs: $jobs, parents: $parents,
    submitted: $submitted, finished: $finished}' > "$run_dir/run.json"
aws s3 cp --quiet --recursive "$run_dir" "$destination/$(basename "$run_dir")/"
echo "$run_dir"
