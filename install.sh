#!/bin/sh
# Link every skill in this repo into ~/.claude/skills/.
#
# Symlinks, not copies, so an edit here is live immediately. A folder that is
# already there and is not a symlink is left alone rather than overwritten.
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest=${CLAUDE_SKILLS_DIR:-"$HOME/.claude/skills"}
mkdir -p "$dest"

for dir in "$repo"/skills/*/; do
  name=$(basename "$dir")
  link="$dest/$name"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    printf 'skip  %s: %s exists and is not a symlink\n' "$name" "$link" >&2
    printf '      move it aside to switch to this repo: mv "%s" "%s.bak"\n' "$link" "$link" >&2
    continue
  fi
  ln -sfn "$dir" "$link"
  printf 'link  %s -> %s\n' "$link" "$dir"
done

printf '\nThe mermaid skill needs its renderer once:\n'
printf '  claude mcp add mermaid -- npx -y mermaid-render-mcp\n'
