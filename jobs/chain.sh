#!/usr/bin/env bash
# Submits the whole decoder loop as one chain of Slurm jobs, wired by dependency so no
# hand touches it between the first sample and the comparison: for each training cell a
# generate array and a training job on its samples; then the evaluation cells decoded
# by matching and, once every model is written, by the learned decoder; then a report
# that compares the two evaluations, and a sync that copies the report to S3.
# usage: chain.sh [-s seed] [-n noise model] [-c chunks] [-e epochs] [-N train nodes] [-r noise rate]... <sweep image> <train image> s3://bucket <queue> <train shots per chunk> <evaluate shots> <distance:noise>...
# Each training cell is one distance at one noise rate; the evaluation decodes every
# distance at every -r rate, or at the training rates when none is given. Every child
# run names this chain as a parent, and the chain's record names every child.
set -euo pipefail
seed=0 noise=depolarising chunks=1 epochs=10 train_nodes=1 rates=()
while getopts 's:n:c:e:N:r:' option; do
  case $option in
    s) seed=$OPTARG ;;
    n) noise=$OPTARG ;;
    c) chunks=$OPTARG ;;
    e) epochs=$OPTARG ;;
    N) train_nodes=$OPTARG ;;
    r) rates+=("$OPTARG") ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
sweep_image=$1 train_image=$2 bucket=${3%/} queue=$4 train_shots=$5 evaluate_shots=$6
shift 6
(( $# > 0 )) || { echo "give at least one training cell as distance:noise" >&2; exit 2; }
for value in "$train_shots:train shots" "$evaluate_shots:evaluate shots" "$chunks:chunks" "$epochs:epochs" "$train_nodes:train nodes"; do
  [[ ${value%%:*} =~ ^[1-9][0-9]*$ ]] || { echo "${value#*:} must be a positive integer, not '${value%%:*}'" >&2; exit 2; }
done
[[ $seed =~ ^(0|[1-9][0-9]*)$ ]] || { echo "seed must be a non-negative integer, not '$seed'" >&2; exit 2; }
distances=()
for cell in "$@"; do
  [[ $cell =~ ^[0-9]+:[0-9.e-]+$ ]] || { echo "a cell is distance:noise, not '$cell'" >&2; exit 2; }
  # One model per distance: the evaluation picks a cell's model by its distance alone.
  [[ " ${distances[*]+"${distances[*]}"} " == *" ${cell%%:*} "* ]] && { echo "two training cells of distance ${cell%%:*}; one per distance" >&2; exit 2; }
  distances+=("${cell%%:*}")
done
if (( ${#rates[@]} == 0 )); then
  while read -r rate; do rates+=("$rate"); done < <(printf '%s\n' "${@#*:}" | awk '!seen[$0]++')
fi
jobs=$(cd "$(dirname "$0")" && pwd)
run_dir=${SCRATCH:-/scratch}/$USER/chains/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir/report" "$run_dir/logs"
chain_uri=$bucket/chains/$(basename "$run_dir")
read -r sweep_digest _ < <("$jobs/pull-image.sh" "$sweep_image")
read -r train_digest train_sif < <("$jobs/pull-image.sh" "$train_image")
commit=$(cat "$jobs/COMMIT" 2>/dev/null || true)
config=${CLUSTER_CONFIG:-/opt/parallelcluster/shared/cluster-config.yaml}
config_hash='' idle=''
if [[ -f $config ]]; then
  config_hash=$(sha256sum "$config" | cut -c1-64)
  idle=$(sed -n 's/^ *ScaledownIdletime: *//p' "$config" | head -1)
fi
submitted=$(date -u +%FT%TZ)
generate_runs='[]' train_runs='[]' models=() train_jobs=() train_parents=()
for cell in "$@"; do
  # A run is named by the second it was submitted in; two children must not share one.
  (( ${#train_jobs[@]} > 0 )) && sleep 1
  read -r generate_dir generate_array _ < <("$jobs/generate.sh" -s "$seed" -n "$noise" -c "$chunks" -p "$chain_uri" \
    "$sweep_image" "$bucket/generate" "$queue" "$train_shots" "$cell")
  generate_uri=$bucket/generate/$(basename "$generate_dir")
  sleep 1
  read -r train_dir train_job _ < <("$jobs/train.sh" -s "$seed" -e "$epochs" -n "$train_nodes" -a "${generate_array#array=}" \
    -p "$chain_uri" -p "$generate_uri" "$train_image" "$bucket/train" "$generate_dir/samples" "$queue")
  train_uri=$bucket/train/$(basename "$train_dir")
  generate_runs=$(jq --arg uri "$generate_uri" '. + [$uri]' <<<"$generate_runs")
  train_runs=$(jq --arg uri "$train_uri" '. + [$uri]' <<<"$train_runs")
  models+=(-m "${cell%%:*}=$train_dir/model/decoder.pt")
  train_jobs+=("${train_job#train=}")
  train_parents+=(-p "$train_uri")
done
cells=()
for cell in "$@"; do
  for rate in "${rates[@]}"; do cells+=("${cell%%:*}:$rate"); done
done
sleep 1
read -r matching_dir matching_array _ < <("$jobs/evaluate.sh" -s "$seed" -n "$noise" -p "$chain_uri" \
  "$sweep_image" "$bucket/evaluations" "$queue" "$evaluate_shots" "${cells[@]}")
sleep 1
read -r learned_dir learned_array _ < <("$jobs/evaluate.sh" -s "$seed" -n "$noise" -D learned "${models[@]}" \
  -a "$(IFS=:; echo "${train_jobs[*]}")" -p "$chain_uri" "${train_parents[@]}" \
  "$train_image" "$bucket/evaluations" "$queue" "$evaluate_shots" "${cells[@]}")
report=$(sbatch --parsable --partition "$queue" --dependency="afterok:${matching_array#array=}:${learned_array#array=}" \
  --export="ALL,RUN_DIR=$run_dir,REPORT_IMAGE=$train_sif,MATCHING=$matching_dir,LEARNED=$learned_dir" \
  --output "$run_dir/logs/report.out" "$jobs/report.sbatch")
sync=$(sbatch --parsable --partition "$queue" --dependency="afterany:$report" \
  --export="ALL,RUN_DIR=$run_dir,DESTINATION=$bucket/chains,OUTPUTS=report,PATTERN=*" \
  --output "$run_dir/logs/sync.out" "$jobs/sync.sbatch")
jq -n --arg run "$(basename "$run_dir")" --arg queue "$queue" --arg image "$sweep_image" --arg digest "$sweep_digest" \
  --arg train_image "$train_image" --arg train_digest "$train_digest" --arg commit "$commit" --arg config_hash "$config_hash" \
  --arg idle "$idle" --arg noise "$noise" --arg submitted "$submitted" --arg report "$report" --arg sync "$sync" \
  --arg matching "$bucket/evaluations/$(basename "$matching_dir")" --arg learned "$bucket/evaluations/$(basename "$learned_dir")" \
  --argjson seed "$seed" --argjson chunks "$chunks" --argjson epochs "$epochs" --argjson train_nodes "$train_nodes" \
  --argjson train_shots "$train_shots" --argjson evaluate_shots "$evaluate_shots" \
  --argjson generate_runs "$generate_runs" --argjson train_runs "$train_runs" \
  --argjson cells "$(jq -cn '$ARGS.positional' --args "$@")" --argjson rates "$(jq -cn '$ARGS.positional' --args "${rates[@]}")" \
  '{run: $run, queue: $queue, image: $image, image_digest: ($digest | if . == "" then null else . end),
    train_image: $train_image, train_image_digest: ($train_digest | if . == "" then null else . end),
    commit: ($commit | if . == "" then null else . end),
    cluster_config_sha256: ($config_hash | if . == "" then null else . end),
    scaledown_idle_minutes: ($idle | if . == "" then null else tonumber end),
    jobs: {report: ($report | tonumber? // .), sync: ($sync | tonumber? // .)},
    seed: $seed, noise: $noise, cells: $cells, rates: $rates,
    shots: {generate: $train_shots, chunks: $chunks, evaluate: $evaluate_shots},
    epochs: $epochs, train_nodes: $train_nodes,
    children: {generate: $generate_runs, train: $train_runs, evaluations: {pymatching: $matching, learned: $learned}},
    submitted: $submitted}' > "$run_dir/run.json"
echo "$run_dir report=$report sync=$sync"
