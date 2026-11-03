#!/usr/bin/env bash
# Submits an evaluation: named cells decoded by one decoder as one Slurm array, and a
# sync job that runs when it is done. The run has a sweep's shape, so the reducer, the
# comparison and the site read it like any other.
# usage: evaluate.sh [-s seed] [-p parent-run]... [-n noise model] [-D decoder] [-m distance=model]... [-a job[:job]...] <image uri> s3://bucket/prefix <queue> <shots> <distance:noise>...
# The learned decoder needs torch, so its image is the training one, and a model for
# every distance named; -a holds the array until the jobs that write those models end.
set -euo pipefail
seed=0 parents='[]' noise=depolarising decoder=pymatching models='' after=''
while getopts 's:p:n:D:m:a:' option; do
  case $option in
    s) seed=$OPTARG ;;
    p) parents=$(jq --arg parent "$OPTARG" '. + [$parent]' <<<"$parents") ;;
    n) noise=$OPTARG ;;
    D) decoder=$OPTARG ;;
    m) models="${models:+$models }$OPTARG" ;;
    a) after=$OPTARG ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
image_uri=$1 destination=${2%/} queue=$3 shots=$4
shift 4
[[ $seed =~ ^(0|[1-9][0-9]*)$ ]] || { echo "seed must be a non-negative integer, not '$seed'" >&2; exit 2; }
[[ $decoder == pymatching || $decoder == learned ]] || { echo "the decoder is pymatching or learned, not '$decoder'" >&2; exit 2; }
(( $# > 0 )) || { echo "give at least one cell as distance:noise" >&2; exit 2; }
for cell in "$@"; do
  [[ $cell =~ ^[0-9]+:[0-9.e-]+$ ]] || { echo "a cell is distance:noise, not '$cell'" >&2; exit 2; }
  if [[ $decoder == learned ]]; then
    [[ " $models " == *" ${cell%%:*}="* ]] || { echo "no model for distance ${cell%%:*}; give -m ${cell%%:*}=<decoder.pt>" >&2; exit 2; }
  fi
done
jobs=$(cd "$(dirname "$0")" && pwd)
run_dir=${SCRATCH:-/scratch}/$USER/evaluations/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir/cells" "$run_dir/logs"
# The image is pulled once per digest into a cache shared by every node; the record
# keeps the digest, since a tag can move and a digest cannot.
read -r digest sif < <("$jobs/pull-image.sh" "$image_uri")
commit=$(cat "$jobs/COMMIT" 2>/dev/null || true)
config=${CLUSTER_CONFIG:-/opt/parallelcluster/shared/cluster-config.yaml}
config_hash='' idle=''
if [[ -f $config ]]; then
  config_hash=$(sha256sum "$config" | cut -c1-64)
  idle=$(sed -n 's/^ *ScaledownIdletime: *//p' "$config" | head -1)
fi
hold=()
[[ -n $after ]] && hold=(--dependency="afterok:$after")
submitted=$(date -u +%FT%TZ)
array=$(sbatch --parsable --partition "$queue" --array="0-$(( $# - 1 ))" "${hold[@]+"${hold[@]}"}" \
  --export="ALL,RUN_DIR=$run_dir,SWEEP_IMAGE=$sif,CELLS=$*,SHOTS=$shots,SEED=$seed,NOISE=$noise,DECODER=$decoder,MODELS=$models" \
  --output "$run_dir/logs/%a.out" "$jobs/evaluate.sbatch")
sync=$(sbatch --parsable --partition "$queue" --dependency="afterany:$array" \
  --export="ALL,RUN_DIR=$run_dir,DESTINATION=$destination" \
  --output "$run_dir/logs/sync.out" "$jobs/sync.sbatch")
jq -n --arg run "$(basename "$run_dir")" --arg queue "$queue" --arg image "$image_uri" --arg digest "$digest" \
  --arg commit "$commit" --arg config_hash "$config_hash" --arg idle "$idle" --arg noise "$noise" \
  --arg decoder "$decoder" --arg models "$models" --arg submitted "$submitted" --arg array "$array" --arg sync "$sync" \
  --argjson seed "$seed" --argjson parents "$parents" --argjson shots "$shots" --args \
  '{run: $run, queue: $queue, image: $image, image_digest: ($digest | if . == "" then null else . end),
    commit: ($commit | if . == "" then null else . end),
    cluster_config_sha256: ($config_hash | if . == "" then null else . end),
    scaledown_idle_minutes: ($idle | if . == "" then null else tonumber end),
    jobs: {array: ($array | tonumber? // .), sync: ($sync | tonumber? // .)},
    seed: $seed, parents: $parents, noise: $noise, decoder: $decoder,
    models: ($models | split(" ") | map(select(length > 0) | split("=") | {key: .[0], value: .[1]}) | from_entries),
    cells: $ARGS.positional, shots: $shots, submitted: $submitted}' "$@" > "$run_dir/run.json"
echo "$run_dir array=$array sync=$sync"
