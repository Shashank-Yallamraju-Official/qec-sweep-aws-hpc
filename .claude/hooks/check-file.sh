#!/usr/bin/env bash
# Runs the commit-time checks on one file the moment it is written,
# so a problem surfaces at the edit rather than at the commit.
set -uo pipefail
f=$(jq -r '.tool_input.file_path // empty')
[[ -f $f ]] || exit 0
git check-ignore -q "$f" && exit 0

out=$(uv run pre-commit run --files "$f" 2>&1) \
  || out=$(uv run pre-commit run --files "$f" 2>&1) \
  || { echo "$out" >&2; exit 2; }

test_file="tests/${f%.py}"
test_file="${test_file%/*}/test_${test_file##*/}.py"
[[ $f == *.py && -f $test_file ]] && { uv run pytest -x "$test_file" >&2 || exit 2; }
exit 0
