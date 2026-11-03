#!/usr/bin/env bash
# Submits the training set as one Slurm array, one task per cell and seed chunk, and a
# sync job that runs when it is done.
# usage: generate.sh [-s seed] [-p parent-run]... [-n noise model] [-c chunks] <image uri> s3://bucket/prefix <queue> <shots per chunk> <distance:noise>...
# Chunk k of a cell is sampled with seed + k, so the chunks of one cell never repeat a
# shot and the whole set is reproducible from the record: the image digest, the cluster
# configuration, the job ids, the base seed, the noise model and the runs it answers to.
set -euo pipefail
seed=0 parents='[]' noise=depolarising chunks=1
while getopts 's:p:n:c:' option; do
  case $option in
    s) seed=$OPTARG ;;
    p) parents=$(jq --arg parent "$OPTARG" '. + [$parent]' <<<"$parents") ;;
    n) noise=$OPTARG ;;
    c) chunks=$OPTARG ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
image_uri=$1 destination=${2%/} queue=$3 shots=$4
shift 4
[[ $seed =~ ^(0|[1-9][0-9]*)$ ]] || { echo "seed must be a non-negative integer, not '$seed'" >&2; exit 2; }
[[ $chunks =~ ^[1-9][0-9]*$ ]] || { echo "chunks must be a positive integer, not '$chunks'" >&2; exit 2; }
(( $# > 0 )) || { echo "give at least one cell as distance:noise" >&2; exit 2; }
for cell in "$@"; do
  [[ $cell =~ ^[0-9]+:[0-9.e-]+$ ]] || { echo "a cell is distance:noise, not '$cell'" >&2; exit 2; }
done
jobs=$(cd "$(dirname "$0")" && pwd)
run_dir=${SCRATCH:-/scratch}/$USER/generate/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir/samples" "$run_dir/logs"
# The image is pulled once per digest into a cache shared by every node; the record
# keeps the digest, since a tag can move and a digest cannot.
read -r digest sif < <("$jobs/pull-image.sh" "$image_uri")
commit=$(cat "$jobs/COMMIT" 2>/dev/null || true)
config=${CLUSTER_CONFIG:-/opt/parallelcluster/shared/cluster-config.yaml}
config_hash=''
if [[ -f $config ]]; then config_hash=$(sha256sum "$config" | cut -c1-64); fi
last=$(( $# * chunks - 1 ))
submitted=$(date -u +%FT%TZ)
array=$(sbatch --parsable --partition "$queue" --array="0-$last" \
  --export="ALL,RUN_DIR=$run_dir,SAMPLE_IMAGE=$sif,CELLS=$*,SHOTS=$shots,CHUNKS=$chunks,SEED=$seed,NOISE=$noise" \
  --output "$run_dir/logs/%a.out" "$jobs/generate.sbatch")
sync=$(sbatch --parsable --partition "$queue" --dependency="afterany:$array" \
  --export="ALL,RUN_DIR=$run_dir,DESTINATION=$destination,OUTPUTS=samples,PATTERN=*.npz" \
  --output "$run_dir/logs/sync.out" "$jobs/sync.sbatch")
jq -n --arg run "$(basename "$run_dir")" --arg queue "$queue" --arg image "$image_uri" --arg digest "$digest" \
  --arg commit "$commit" --arg config_hash "$config_hash" --arg noise "$noise" --arg submitted "$submitted" \
  --arg array "$array" --arg sync "$sync" --argjson seed "$seed" --argjson parents "$parents" \
  --argjson shots "$shots" --argjson chunks "$chunks" --args \
  '{run: $run, queue: $queue, image: $image, image_digest: ($digest | if . == "" then null else . end),
    commit: ($commit | if . == "" then null else . end),
    cluster_config_sha256: ($config_hash | if . == "" then null else . end),
    jobs: {array: ($array | tonumber? // .), sync: ($sync | tonumber? // .)},
    seed: $seed, parents: $parents, noise: $noise, cells: $ARGS.positional, shots: $shots, chunks: $chunks,
    submitted: $submitted}' "$@" > "$run_dir/run.json"
echo "$run_dir array=$array sync=$sync"
