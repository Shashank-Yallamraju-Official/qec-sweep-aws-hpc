#!/usr/bin/env bash
# Refuses git commands that bypass the gate or write to main directly.
# Each simple command is parsed as words so that mentions in strings or
# comments pass and option clusters such as -uf or -n do not.
set -o pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
cmd=$(jq -r '.tool_input.command // empty')
[[ $cmd == *git* ]] || exit 0

refuse() { echo "$1" >&2; exit 2; }

target=$(git branch --show-current 2>/dev/null)

# Sets sub, args and hooks_off from words; sub is empty when words is not a git command.
parse() {
  sub="" args=() hooks_off=no
  local i=0 w
  while [[ ${words[i]:-} =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; do
    [[ ${words[i]} == SKIP=* ]] && hooks_off=yes
    i=$((i + 1))
  done
  [[ ${words[i]:-} == git ]] || return 0
  i=$((i + 1))
  while [[ $i -lt ${#words[@]} ]]; do
    w=${words[i]}
    if [[ $w == -c || $w == -C ]]; then
      [[ ${words[i + 1]:-} == core.hooksPath=* ]] && hooks_off=yes
      i=$((i + 2))
    elif [[ $w == -* ]]; then
      i=$((i + 1))
    else
      sub=$w
      args=("${words[@]:i+1}")
      return 0
    fi
  done
}

while IFS= read -r simple; do
  read -r -a words <<<"$simple"
  parse
  case $sub in
    commit)
      [[ $hooks_off == yes ]] && refuse "hooks are not optional"
      for a in "${args[@]+"${args[@]}"}"; do
        [[ $a == --no-verify || $a =~ ^-[a-zA-Z]*n[a-zA-Z]*$ ]] && refuse "hooks are not optional"
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
done < <(sed -E 's/&&|\|\||;|\|/\n/g' <<<"$cmd")
exit 0
