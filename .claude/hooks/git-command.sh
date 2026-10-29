# shellcheck shell=bash
# Shared by the hooks that inspect a shell command for git subcommands.
# split_commands prints each simple command on its own line. parse_git
# reads the array `words` and sets sub, args and hooks_off; sub is empty
# when the words are not a git command.

split_commands() { sed -E 's/&&|\|\||;|\|/\n/g' <<<"$1"; }

# shellcheck disable=SC2034  # sub, args and hooks_off are set for the caller
parse_git() {
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
