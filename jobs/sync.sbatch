#!/usr/bin/env bash
# Copies a finished run's cells to S3. Nodes have put-only access, which rules
# out `aws s3 sync`; a recursive copy needs no listing.
# The submitter sets RUN_DIR and DESTINATION; see sweep.sh.
#SBATCH --job-name=sync
#SBATCH --time=00:15:00
set -euo pipefail
: "${RUN_DIR:?}" "${DESTINATION:?}" "${QUEUE:?}"
target="$DESTINATION/$(basename "$RUN_DIR")"
# Close the run record: when the array finished and how many nodes the queue had up.
up=$(sinfo -p "$QUEUE" -h -t alloc,mix,idle -o %N | wc -l)
finished=$(date -u +%FT%TZ) python3 - "$RUN_DIR/run.json" "$up" <<'PY'
import json, os, sys
path, up = sys.argv[1], int(sys.argv[2])
record = json.load(open(path))
record.update(finished=os.environ["finished"], nodes_up=up)
json.dump(record, open(path, "w"), indent=2)
PY
# A task killed mid-write leaves a .partial file; it is not a result.
aws s3 cp --quiet --recursive --exclude '*.partial' "$RUN_DIR/cells" "$target/"
aws s3 cp --quiet "$RUN_DIR/run.json" "$target/run.json"
echo "$(find "$RUN_DIR/cells" -name '*.parquet' | wc -l) files copied to $target/"
