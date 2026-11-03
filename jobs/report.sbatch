#!/usr/bin/env bash
# Closes a chain: the two evaluations, matching and learned, are compared cell by cell
# from scratch inside the training image, and the rows, the verdicts and the figure land
# under the chain's report directory for its sync job to copy. Nodes cannot read the
# bucket, so each evaluation is first staged from scratch into the shape its sync job
# gives it in S3, the cells beside the record, which is the shape the readers know.
# The submitter sets RUN_DIR, REPORT_IMAGE, MATCHING, LEARNED and --output; see chain.sh.
#SBATCH --job-name=report
#SBATCH --time=00:15:00
set -euo pipefail
: "${RUN_DIR:?}" "${REPORT_IMAGE:?}" "${MATCHING:?}" "${LEARNED:?}"
# The node leaves a marker, so the run's record counts the nodes it actually used.
mkdir -p "$RUN_DIR/report" "$RUN_DIR/nodes" && touch "$RUN_DIR/nodes/$SLURMD_NODENAME"
stage() {
  local run
  run=$RUN_DIR/staged/evaluations/$(basename "$1")
  mkdir -p "$run"
  cp "$1/run.json" "$run/"
  # A task killed mid-write leaves a .partial file; it is not a result.
  find "$1/cells" -name '*.parquet' -exec cp {} "$run/" \;
  echo "$run"
}
matching=$(stage "$MATCHING")
learned=$(stage "$LEARNED")
apptainer exec --bind /scratch "$REPORT_IMAGE" results-compare "$matching" "$learned" \
  --out "$RUN_DIR/report/comparison.parquet" | tee "$RUN_DIR/report/comparison.txt"
apptainer exec --bind /scratch "$REPORT_IMAGE" decoder-plot "$matching" "$learned" \
  --out "$RUN_DIR/report/decoders.png" | tee "$RUN_DIR/report/decoders.txt"
