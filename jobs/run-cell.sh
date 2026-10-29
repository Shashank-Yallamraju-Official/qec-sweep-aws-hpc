#!/usr/bin/env bash
# Runs one cell on a node and copies its Parquet file under an S3 prefix.
# usage: run-cell.sh s3://bucket/prefix <distance> <noise> <shots>
# With SWEEP_IMAGE set, the cell runs inside that Apptainer image.
set -euo pipefail
destination=${1%/} distance=$2 noise=$3 shots=$4
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
sweep=(sweep)
# Scratch directories are not bound into the container by default.
[[ -n ${SWEEP_IMAGE:-} ]] && sweep=(apptainer run --bind "$out" "$SWEEP_IMAGE")
file=$("${sweep[@]}" --d "$distance" --p "$noise" --shots "$shots" --out "$out")
aws s3 cp --quiet "$file" "$destination/$(basename "$file")"
echo "$destination/$(basename "$file")"
