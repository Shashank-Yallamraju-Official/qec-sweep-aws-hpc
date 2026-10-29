#!/usr/bin/env bash
# Copies a finished run's cells to S3. Nodes have put-only access, which rules
# out `aws s3 sync`; a recursive copy needs no listing.
# The submitter sets RUN_DIR and DESTINATION; see sweep.sh.
#SBATCH --job-name=sync
#SBATCH --time=00:15:00
set -euo pipefail
: "${RUN_DIR:?}" "${DESTINATION:?}"
target="$DESTINATION/$(basename "$RUN_DIR")"
aws s3 cp --quiet --recursive "$RUN_DIR/cells" "$target/"
echo "$(find "$RUN_DIR/cells" -name '*.parquet' | wc -l) files copied to $target/"
