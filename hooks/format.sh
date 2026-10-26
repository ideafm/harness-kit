#!/bin/bash
input=$(cat)
source "$(dirname "$0")/lib.sh"

file=$(jq -r '.tool_input.file_path // empty' <<<"$input")
[ -f "$file" ] || exit 0
case "$file" in "$TW_ROOT"/*) ;; *) exit 0 ;; esac

prettier="$TW_ROOT/node_modules/.bin/prettier"
[ -x "$prettier" ] || exit 0

before=$(shasum "$file")
(cd "$TW_ROOT" && "$prettier" --write --ignore-unknown "$file" >/dev/null 2>&1) || exit 0
after=$(shasum "$file")

[ "$before" = "$after" ] && exit 0

jq -n --arg f "${file#$TW_ROOT/}" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: ("Файл " + $f + " переформатирован prettier. Перед следующей правкой перечитай его.")
  }
}'
