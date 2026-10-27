#!/bin/bash

tw_config() {
  local dir="${CLAUDE_PROJECT_DIR:-$PWD}"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/.claude/tw.json" ]; then
      echo "$dir/.claude/tw.json"
      return 0
    fi
    dir=$(dirname "$dir")
  done
  return 1
}

tw_get() {
  jq -r "$1 // empty" "$TW_CONFIG"
}

tw_pm() {
  if [ -f "$TW_ROOT/pnpm-lock.yaml" ]; then echo pnpm
  elif [ -f "$TW_ROOT/yarn.lock" ]; then echo yarn
  else echo npm
  fi
}

tw_test_cmd() {
  local cmd
  cmd=$(tw_get .test)
  if [ -z "$cmd" ] && [ -f "$TW_ROOT/package.json" ]; then
    jq -e '.scripts.test | strings | test("no test specified") | not' "$TW_ROOT/package.json" >/dev/null 2>&1 && cmd="$(tw_pm) test"
  fi
  echo "$cmd"
}

tw_check_cmd() {
  local cmd
  cmd=$(tw_get .check)
  if [ -z "$cmd" ] && [ -f "$TW_ROOT/package.json" ]; then
    jq -e '.scripts.check | strings' "$TW_ROOT/package.json" >/dev/null 2>&1 && cmd="$(tw_pm) run check"
  fi
  [ -n "$cmd" ] || cmd=$(tw_test_cmd)
  echo "$cmd"
}

tw_current_plans() {
  local p
  git -C "$TW_ROOT" rev-parse --verify -q HEAD >/dev/null 2>&1 || return 0
  for p in "$TW_ROOT"/docs/plans/*.md; do
    [ -f "$p" ] || continue
    if grep -qE '^\*\*Статус:\*\* в работе' "$p" || [ -n "$(git -C "$TW_ROOT" status --porcelain -- "$p")" ]; then
      echo "$p"
    fi
  done
}

tw_changed() {
  { git -C "$TW_ROOT" diff --name-only --no-renames "$TW_REF"; git -C "$TW_ROOT" ls-files --others --exclude-standard; } | sort -u
}

tw_plan_spec() {
  local spec
  spec=$(grep -m1 -oE '^\*\*Спецификация:\*\* .*' "$1" | sed 's/^\*\*Спецификация:\*\* //; s/`//g')
  [ -f "$TW_ROOT/$spec" ] && echo "$TW_ROOT/$spec"
}

[ -n "$TW_NESTED" ] && exit 0
TW_CONFIG=$(tw_config) || exit 0
TW_ROOT=$(dirname "$(dirname "$TW_CONFIG")")
TW_STATE="$TW_ROOT/.claude/tw-state"
TW_REF=HEAD
[ -n "$TW_DIFF_BASE" ] && git -C "$TW_ROOT" cat-file -e "$TW_DIFF_BASE^{commit}" 2>/dev/null && TW_REF=$TW_DIFF_BASE
mkdir -p "$TW_STATE"
