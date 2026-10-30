#!/usr/bin/env bash
# Closes a run's record and copies its cells to S3. Nodes have put-only access,
# which rules out `aws s3 sync`; a recursive copy needs no listing.
# The submitter sets RUN_DIR and DESTINATION; see sweep.sh.
#SBATCH --job-name=sync
#SBATCH --time=00:15:00
#SBATCH --requeue
set -euo pipefail
: "${RUN_DIR:?}" "${DESTINATION:?}"
target="$DESTINATION/$(basename "$RUN_DIR")"
# The run finished when its last cell was written; the nodes it used left markers.
finished=$(date -u -d "@$(stat -c %Y "$RUN_DIR"/cells/*.parquet | sort -n | tail -1)" +%FT%TZ)
nodes_used=$(find "$RUN_DIR/nodes" -mindepth 1 | wc -l)
finished=$finished python3 - "$RUN_DIR/run.json" "$nodes_used" <<'PY'
import json, os, sys
path, nodes_used = sys.argv[1], int(sys.argv[2])
record = json.load(open(path))
record.update(finished=os.environ["finished"], nodes_used=nodes_used)
json.dump(record, open(path, "w"), indent=2)
PY
# A task killed mid-write leaves a .partial file; it is not a result.
aws s3 cp --quiet --recursive --exclude '*.partial' "$RUN_DIR/cells" "$target/"
aws s3 cp --quiet "$RUN_DIR/run.json" "$target/run.json"
echo "$(find "$RUN_DIR/cells" -name '*.parquet' | wc -l) files copied to $target/"
