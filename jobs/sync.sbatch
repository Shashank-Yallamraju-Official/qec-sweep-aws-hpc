#!/usr/bin/env bash
# Closes a run's record and copies its outputs and logs to S3. Nodes have put-only access,
# which rules out `aws s3 sync`; a recursive copy needs no listing.
# The submitter sets RUN_DIR and DESTINATION, and OUTPUTS and PATTERN when the run writes
# something other than a sweep's cells; see sweep.sh and generate.sh.
#SBATCH --job-name=sync
#SBATCH --time=00:15:00
#SBATCH --requeue
set -euo pipefail
: "${RUN_DIR:?}" "${DESTINATION:?}"
outputs=${OUTPUTS:-cells} pattern=${PATTERN:-*.parquet}
target="$DESTINATION/$(basename "$RUN_DIR")"
# The run finished when its last output was written; the nodes it used left markers.
# shellcheck disable=SC2086 # the pattern is meant to glob
finished=$(date -u -d "@$(stat -c %Y "$RUN_DIR/$outputs"/$pattern | sort -n | tail -1)" +%FT%TZ)
nodes_used=$(find "$RUN_DIR/nodes" -mindepth 1 | wc -l)
finished=$finished python3 - "$RUN_DIR/run.json" "$nodes_used" <<'PY'
import json, os, sys
path, nodes_used = sys.argv[1], int(sys.argv[2])
record = json.load(open(path))
record.update(finished=os.environ["finished"], nodes_used=nodes_used)
json.dump(record, open(path, "w"), indent=2)
PY
# A task killed mid-write leaves a .partial file; it is not a result.
aws s3 cp --quiet --recursive --exclude '*.partial' "$RUN_DIR/$outputs" "$target/"
aws s3 cp --quiet "$RUN_DIR/run.json" "$target/run.json"
# Scratch dies with the cluster, and a task's log is the only trace of a task that failed.
aws s3 cp --quiet --recursive "$RUN_DIR/logs" "$target/logs/"
echo "$(find "$RUN_DIR/$outputs" -name "$pattern" | wc -l) files copied to $target/"
