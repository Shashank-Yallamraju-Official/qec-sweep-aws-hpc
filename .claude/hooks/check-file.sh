#!/usr/bin/env bash
# Runs the commit-time checks on one file the moment it is written,
# so a problem surfaces at the edit rather than at the commit.
# Logs the outcome so tools/process_report.py can count fixes per commit.
set -uo pipefail
root=${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}
cd "$root" || exit 0
f=$(jq -r '.tool_input.file_path // empty')
[[ $f == /* ]] || f=$root/$f
[[ $f == "$root"/* ]] || exit 0
f=${f#"$root/"}
[[ -f $f ]] || exit 0
git check-ignore -q "$f" && exit 0

log() { mkdir -p .claude/metrics; jq -nc --arg f "$f" --arg e "$1" --argjson ok "$2" \
  '{ts: (now | todate), event: $e, file: $f, ok: $ok}' >> .claude/metrics/events.jsonl; }

out=$(uv run pre-commit run --files "$f" 2>&1) \
  || out=$(uv run pre-commit run --files "$f" 2>&1) \
  || { log edit false; echo "$out" >&2; exit 2; }
log edit true

if [[ $f == tests/*test_*.py ]]; then
  test_file=$f
elif [[ $f == *.py ]]; then
  test_file="tests/${f%.py}"
  test_file="${test_file%/*}/test_${test_file##*/}.py"
else
  exit 0
fi
if [[ -f $test_file ]]; then
  uv run pytest -x "$test_file" >&2 || { log test false; exit 2; }
  log test true
fi
exit 0
