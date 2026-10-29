#!/usr/bin/env bash
# Runs one cell on a node and copies its Parquet file under an S3 prefix.
# usage: run-cell.sh s3://bucket/prefix <distance> <noise> <shots>
set -euo pipefail
destination=$1 distance=$2 noise=$3 shots=$4
out=$(mktemp -d)
file=$(sweep --d "$distance" --p "$noise" --shots "$shots" --out "$out")
aws s3 cp --quiet "$file" "$destination/$(basename "$file")"
echo "$destination/$(basename "$file")"
