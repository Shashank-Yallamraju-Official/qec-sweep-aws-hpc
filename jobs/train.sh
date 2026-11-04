#!/usr/bin/env bash
# Submits one training job on a generate run's samples, and a sync job that runs when it is done.
# usage: train.sh [-s seed] [-p parent-run]... [-e epochs] [-P patience] [-l learning rate] [-d device] [-n nodes] [-a job] <image uri> s3://bucket/prefix <samples dir> [queue]
# The image is the training one, oras://ghcr.io/<owner>/<repo>/train:<commit>, which carries torch.
# The job takes whole nodes of the queue, one by default, and trains one model across
# them with a rank per node; -a holds it until the job writing the samples ends. The
# record names what an audit walks back to: the image's digest, the cluster
# configuration, the job ids, the seed, the generate run the samples came from as the
# parent, and the settings.
set -euo pipefail
seed=0 parents='[]' epochs=10 patience='' learning_rate=0.001 device=cpu nodes=1 after=''
while getopts 's:p:e:P:l:d:n:a:' option; do
  case $option in
    s) seed=$OPTARG ;;
    p) parents=$(jq --arg parent "$OPTARG" '. + [$parent]' <<<"$parents") ;;
    e) epochs=$OPTARG ;;
    P) patience=$OPTARG ;;
    l) learning_rate=$OPTARG ;;
    d) device=$OPTARG ;;
    n) nodes=$OPTARG ;;
    a) after=$OPTARG ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
image_uri=$1 destination=${2%/} samples=$3 queue=${4:-train}
[[ $seed =~ ^(0|[1-9][0-9]*)$ ]] || { echo "seed must be a non-negative integer, not '$seed'" >&2; exit 2; }
[[ $epochs =~ ^[1-9][0-9]*$ ]] || { echo "epochs must be a positive integer, not '$epochs'" >&2; exit 2; }
[[ -z $patience || $patience =~ ^[1-9][0-9]*$ ]] || { echo "patience must be a positive integer, not '$patience'" >&2; exit 2; }
[[ $nodes =~ ^[1-9][0-9]*$ ]] || { echo "nodes must be a positive integer, not '$nodes'" >&2; exit 2; }
[[ $learning_rate =~ ^[0-9]*\.?[0-9]+([eE]-?[0-9]+)?$ ]] || { echo "learning rate must be a number, not '$learning_rate'" >&2; exit 2; }
[[ -d $samples ]] || { echo "no samples directory at '$samples'" >&2; exit 2; }
jobs=$(cd "$(dirname "$0")" && pwd)
# Keyed by user so two people's runs never contend for one directory.
run_dir=${SCRATCH:-/scratch}/$USER/train/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run_dir/model" "$run_dir/logs"
# The image is pulled once per digest into a cache shared by every node; the record
# keeps the digest, since a tag can move and a digest cannot.
read -r digest sif < <("$jobs/pull-image.sh" "$image_uri")
# The deploy workflow installs the scripts with the commit they came from beside them.
commit=$(cat "$jobs/COMMIT" 2>/dev/null || true)
config=${CLUSTER_CONFIG:-/opt/parallelcluster/shared/cluster-config.yaml}
config_hash='' idle=''
if [[ -f $config ]]; then
  config_hash=$(sha256sum "$config" | cut -c1-64)
  # The idle tail the node will be billed for is a cluster setting, so the record keeps it.
  idle=$(sed -n 's/^ *ScaledownIdletime: *//p' "$config" | head -1)
fi
hold=()
[[ -n $after ]] && hold=(--dependency="afterok:$after")
submitted=$(date -u +%FT%TZ)
job=$(sbatch --parsable --partition "$queue" --nodes "$nodes" "${hold[@]+"${hold[@]}"}" \
  --export="ALL,RUN_DIR=$run_dir,TRAIN_IMAGE=$sif,SAMPLES=$samples,SEED=$seed,EPOCHS=$epochs,PATIENCE=$patience,LEARNING_RATE=$learning_rate,DEVICE=$device" \
  --output "$run_dir/logs/train.out" "$jobs/train.sbatch")
sync=$(sbatch --parsable --partition "$queue" --dependency="afterany:$job" \
  --export="ALL,RUN_DIR=$run_dir,DESTINATION=$destination,OUTPUTS=model,PATTERN=*" \
  --output "$run_dir/logs/sync.out" "$jobs/sync.sbatch")
# Written after both submissions so the record can name them; the sync job that
# closes it cannot start before the training ends.
jq -n --arg run "$(basename "$run_dir")" --arg queue "$queue" --arg image "$image_uri" --arg digest "$digest" \
  --arg commit "$commit" --arg config_hash "$config_hash" --arg idle "$idle" --arg samples "$samples" \
  --arg device "$device" --arg submitted "$submitted" --arg job "$job" --arg sync "$sync" --arg patience "$patience" \
  --argjson seed "$seed" --argjson parents "$parents" --argjson epochs "$epochs" --argjson learning_rate "$learning_rate" \
  --argjson nodes "$nodes" \
  '{run: $run, queue: $queue, nodes: $nodes, image: $image, image_digest: ($digest | if . == "" then null else . end),
    commit: ($commit | if . == "" then null else . end),
    cluster_config_sha256: ($config_hash | if . == "" then null else . end),
    scaledown_idle_minutes: ($idle | if . == "" then null else tonumber end),
    jobs: {train: ($job | tonumber? // .), sync: ($sync | tonumber? // .)},
    seed: $seed, parents: $parents, samples: $samples, epochs: $epochs,
    patience: ($patience | if . == "" then null else tonumber end), learning_rate: $learning_rate,
    device: $device, submitted: $submitted}' > "$run_dir/run.json"
echo "$run_dir train=$job sync=$sync"
