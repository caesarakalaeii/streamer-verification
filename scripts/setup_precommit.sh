#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
venv_dir="$repo_root/.venv"
precommit_home="$repo_root/.cache/pre-commit"

if [ ! -d "$venv_dir" ]; then
  python -m venv "$venv_dir"
fi

"$venv_dir/bin/python" -m pip install --upgrade pip
"$venv_dir/bin/python" -m pip install -r requirements-dev.txt

mkdir -p "$precommit_home"
PRE_COMMIT_HOME="$precommit_home" "$venv_dir/bin/pre-commit" install

hook_path="$repo_root/.git/hooks/pre-commit"
if [ -f "$hook_path" ] && ! grep -q "PRE_COMMIT_HOME" "$hook_path"; then
  {
    read -r first_line
    printf "%s\n" "$first_line"
    printf "export PRE_COMMIT_HOME=%q\n" "$precommit_home"
    cat
  } < "$hook_path" > "${hook_path}.tmp"
  mv "${hook_path}.tmp" "$hook_path"
  chmod +x "$hook_path"
fi
