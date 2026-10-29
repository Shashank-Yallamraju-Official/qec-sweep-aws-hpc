#!/usr/bin/env bash
# Logs whether a `git commit` run from Claude Code produced a commit.
# Called with `before` (remember HEAD) and `after` (compare and log).
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}"
cmd=$(jq -r '.tool_input.command // empty')
# shellcheck source=.claude/hooks/git-command.sh
source "$(dirname "$0")/git-command.sh"
commits=no
while IFS= read -r simple; do
  read -r -a words <<<"$simple"
  parse_git
  [[ $sub == commit ]] && commits=yes
done < <(split_commands "$cmd")
[[ $commits == yes ]] || exit 0

dir=.claude/metrics
mkdir -p "$dir"
head_now=$(git rev-parse --verify -q HEAD || echo none)

case $1 in
  before)
    echo "$head_now" > "$dir/head"
    ;;
  after)
    head_before=$(cat "$dir/head" 2>/dev/null || echo none)
    if [[ $head_now == "$head_before" ]]; then
      jq -nc '{ts: (now | todate), event: "commit_rejected"}' >> "$dir/events.jsonl"
    else
      jq -nc --arg sha "$head_now" --arg subject "$(git log -1 --format=%s)" \
        '{ts: (now | todate), event: "commit", sha: $sha, subject: $subject}' >> "$dir/events.jsonl"
    fi
    ;;
esac
