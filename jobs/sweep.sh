#!/usr/bin/env bash
# Submits the whole grid as one Slurm array, and a sync job that runs when it is done.
# usage: sweep.sh [-s seed] [-p parent-run]... [-t instance type] <image uri> s3://bucket/prefix [queue] [nodes]
# Each run records what it used in run.json: what it gets costed from, and what an
# audit walks back to, the image's digest, the cluster configuration, the job ids,
# the sampler seed every cell was given and the runs this one was made from.
set -euo pipefail
seed=0 parents='[]' instance_type=c7a.large
while getopts 's:p:t:' option; do
  case $option in
    s) seed=$OPTARG ;;
    p) parents=$(jq --arg parent "$OPTARG" '. + [$parent]' <<<"$parents") ;;
    t) instance_type=$OPTARG ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
image_uri=$1 destination=${2%/} queue=${3:-sweep} nodes=${4:-}
[[ $seed =~ ^(0|[1-9][0-9]*)$ ]] || { echo "seed must be a non-negative integer, not '$seed'" >&2; exit 2; }
[[ $instance_type =~ ^[a-z0-9]+\.[a-z0-9]+$ ]] || { echo "instance type must be family.size, not '$instance_type'" >&2; exit 2; }
jobs=$(cd "$(dirname "$0")" && pwd)
# Keyed by user so two people's runs never contend for one directory.
run_dir=${SCRATCH:-/scratch}/$USER/sweep/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir/cells" "$run_dir/logs"
# The image is pulled once per digest into a cache shared by every node; the record
# keeps the digest, since a tag can move and a digest cannot.
read -r digest sif < <("$jobs/pull-image.sh" "$image_uri")
# The deploy workflow installs the scripts with the commit they came from beside them.
commit=$(cat "$jobs/COMMIT" 2>/dev/null || true)
config=${CLUSTER_CONFIG:-/opt/parallelcluster/shared/cluster-config.yaml}
config_hash='' idle=''
if [[ -f $config ]]; then
  config_hash=$(sha256sum "$config" | cut -c1-64)
  # The idle tail the nodes will be billed for is a cluster setting, so the record keeps it.
  idle=$(sed -n 's/^ *ScaledownIdletime: *//p' "$config" | head -1)
fi
# The array is exactly as large as the grid inside the image, never a number kept by hand.
last=$(apptainer exec "$sif" python -c 'from sweep.grid import GRID; print(len(GRID) - 1)')
# Every node carries its instance type as a Slurm feature, so a constraint keeps a run on
# one type where a queue offers several. A node count pins the run to that many nodes of
# it: the type's other nodes are excluded by name, and concurrency is capped at two tasks
# per two-vCPU node so those nodes are full, not spread thin. (--nodelist would do the
# opposite: it makes every task hold the whole list.)
range="0-$last"
pin=()
if [[ -n $nodes ]]; then
  [[ $nodes =~ ^[1-9][0-9]*$ ]] || { echo "nodes must be a positive integer, not '$nodes'" >&2; exit 2; }
  range="$range%$((nodes * 2))"
  of_type=$(sinfo -p "$queue" -h -N -o '%N %f' \
    | awk -v type="$instance_type" '{ n = split($2, f, ","); for (i = 1; i <= n; i++) if (f[i] == type) { print $1; break } }')
  surplus=$(tail -n +$((nodes + 1)) <<<"$of_type" | paste -sd, -)
  [[ -n $surplus ]] && pin=(--exclude "$surplus")
fi
submitted=$(date -u +%FT%TZ)
array=$(sbatch --parsable --partition "$queue" --constraint "$instance_type" --array="$range" "${pin[@]+"${pin[@]}"}" \
  --export="ALL,RUN_DIR=$run_dir,SWEEP_IMAGE=$sif,SEED=$seed" \
  --output "$run_dir/logs/%a.out" "$jobs/sweep.sbatch")
sync=$(sbatch --parsable --partition "$queue" --dependency="afterany:$array" \
  --export="ALL,RUN_DIR=$run_dir,DESTINATION=$destination,QUEUE=$queue" \
  --output "$run_dir/logs/sync.out" "$jobs/sync.sbatch")
# Written after both submissions so the record can name them; the sync job that
# closes it cannot start before the array ends.
jq -n --arg run "$(basename "$run_dir")" --arg queue "$queue" --arg nodes "$nodes" --arg image "$image_uri" \
  --arg instance_type "$instance_type" --arg digest "$digest" --arg commit "$commit" --arg config_hash "$config_hash" \
  --arg idle "$idle" --arg submitted "$submitted" --arg array "$array" --arg sync "$sync" \
  --argjson seed "$seed" --argjson parents "$parents" \
  '{run: $run, queue: $queue, nodes: ($nodes | if . == "" then null else tonumber end),
    instance_type: $instance_type, image: $image, image_digest: ($digest | if . == "" then null else . end),
    commit: ($commit | if . == "" then null else . end),
    cluster_config_sha256: ($config_hash | if . == "" then null else . end),
    scaledown_idle_minutes: ($idle | if . == "" then null else tonumber end),
    jobs: {array: ($array | tonumber? // .), sync: ($sync | tonumber? // .)},
    seed: $seed, parents: $parents, submitted: $submitted}' > "$run_dir/run.json"
echo "$run_dir array=$array sync=$sync"
