#!/usr/bin/env bash
# Refuses git commands that bypass the gate or write to main directly.
# Commands are parsed as words so that mentions in strings pass and
# option clusters such as -uf or -n do not.
set -o pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
cmd=$(jq -r '.tool_input.command // empty')
[[ $cmd == *git* ]] || exit 0

refuse() { echo "$1" >&2; exit 2; }
# shellcheck source=.claude/hooks/git-command.sh
source "$(dirname "$0")/git-command.sh"

target=$(git branch --show-current 2>/dev/null)

while IFS= read -r simple; do
  read -r -a words <<<"$simple"
  parse_git
  case $sub in
    commit)
      [[ $hooks_off == yes ]] && refuse "hooks are not optional"
      for a in "${args[@]+"${args[@]}"}"; do
        [[ $a == --no-v* || $a =~ ^-[a-zA-Z]*n[a-zA-Z]*$ ]] && refuse "hooks are not optional"
      done
      [[ $target == main ]] && refuse "main takes pull requests only"
      ;;
    push)
      for a in "${args[@]+"${args[@]}"}"; do
        [[ $a == --force* || $a == +* || $a =~ ^-[a-zA-Z]*f[a-zA-Z]*$ ]] && refuse "history is not rewritten"
      done
      [[ $target == main ]] && refuse "main takes pull requests only"
      ;;
    switch | checkout)
      for a in "${args[@]+"${args[@]}"}"; do
        [[ $a == main ]] && target=main
      done
      ;;
  esac
done < <(split_commands "$cmd")
exit 0
