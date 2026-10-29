#!/usr/bin/env bash
# Refuses git commands that bypass the gate or write to main directly.
set -euo pipefail
cmd=$(jq -r '.tool_input.command // empty')
[[ $cmd == *git* ]] || exit 0

refuse() { echo "$1" >&2; exit 2; }

[[ $cmd == *--no-verify* ]] && refuse "hooks are not optional"
[[ $cmd == *push* && ($cmd == *--force* || $cmd == *" -f"*) ]] && refuse "history is not rewritten"
if [[ $cmd =~ git\ (commit|push) ]] && [[ $(git branch --show-current) == main ]]; then
  refuse "main takes pull requests only"
fi
exit 0
