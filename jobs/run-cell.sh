#!/usr/bin/env bash
# Runs one cell on a node and copies its Parquet file under an S3 prefix.
# usage: run-cell.sh s3://bucket/prefix <distance> <noise> <shots>
# SWEEP names the command to run; "apptainer run sweep.sif" runs it from the image.
set -euo pipefail
destination=${1%/} distance=$2 noise=$3 shots=$4
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
# shellcheck disable=SC2086  # SWEEP is a command line, split on purpose
file=$(${SWEEP:-sweep} --d "$distance" --p "$noise" --shots "$shots" --out "$out")
aws s3 cp --quiet "$file" "$destination/$(basename "$file")"
echo "$destination/$(basename "$file")"
