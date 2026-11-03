#!/usr/bin/env bash
# Closes a chain: the two evaluations, matching and learned, are compared cell by cell
# from scratch inside the training image, and the rows and the verdicts land under the
# chain's report directory for its sync job to copy.
# The submitter sets RUN_DIR, REPORT_IMAGE, MATCHING, LEARNED and --output; see chain.sh.
#SBATCH --job-name=report
#SBATCH --time=00:15:00
set -euo pipefail
: "${RUN_DIR:?}" "${REPORT_IMAGE:?}" "${MATCHING:?}" "${LEARNED:?}"
mkdir -p "$RUN_DIR/report"
apptainer exec --bind /scratch "$REPORT_IMAGE" results-compare "$MATCHING" "$LEARNED" \
  --out "$RUN_DIR/report/comparison.parquet" | tee "$RUN_DIR/report/comparison.txt"
