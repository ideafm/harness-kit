#!/bin/bash
PLUGIN=$(cd "$(dirname "$0")/.." && pwd)
HOOKS="$PLUGIN/hooks/hooks.json"

dir="${CLAUDE_PROJECT_DIR:-$PWD}"
root=""
while [ "$dir" != "/" ]; do
  [ -f "$dir/.claude/tw.json" ] && { root="$dir"; break; }
  dir=$(dirname "$dir")
done

if [ -z "$root" ]; then
  echo "tw не подключён к $PWD — запусти /tw:init"
  exit 0
fi

cfg="$root/.claude/tw.json"
state="$root/.claude/tw-state"
get() { jq -r "$1 // empty" "$cfg"; }
hook() { jq -e --arg e "$1" '.hooks[$e]' "$HOOKS" >/dev/null 2>&1; }
skill() { [ -f "$PLUGIN/skills/$1/SKILL.md" ]; }
mark() { if "$@"; then printf '✓'; else printf '✗'; fi; }
row() { perl -CSA -e 'printf "  %s  %-24s %-21s %s\n", @ARGV' "$1" "$2" "$3" "$4"; }
plan_status() { grep -m1 -oE '^\*\*Статус:\*\* .*' "$1" | sed 's/^\*\*Статус:\*\* //'; }

specs=$(ls "$root"/docs/specs/*.md 2>/dev/null | wc -l | tr -d ' ')
last_spec=$(ls -t "$root"/docs/specs/*.md 2>/dev/null | head -1)

plans_open=0; plans_done=0; acc=""
for p in "$root"/docs/plans/*.md; do
  [ -f "$p" ] || continue
  case "$(plan_status "$p")" in
    готов*) plans_done=$((plans_done + 1)) ;;
    брошен*) ;;
    *) plans_open=$((plans_open + 1)) ;;
  esac
done

test_cmd=$(get .test)
if [ -z "$test_cmd" ] && [ -f "$root/package.json" ] &&
  jq -e '.scripts.test | strings | test("no test specified") | not' "$root/package.json" >/dev/null 2>&1; then
  test_cmd="npm test"
fi
max=$(get .maxRounds)
last_test=$(cat "$state/last-test" 2>/dev/null)
last_scope=$(cat "$state/last-scope" 2>/dev/null)
last_verify=$(cat "$state/last-verify" 2>/dev/null)
verify_model=$(get .verifyModel)
budget=$(get .diffBudget)
prettier="✗ нет prettier в проекте"
[ -x "$root/node_modules/.bin/prettier" ] && prettier="prettier"
comments="комментарии запрещены"
[ "$(get .noComments)" = "false" ] && comments="комментарии разрешены"

echo "tw · ${root/#$HOME/~}"
echo
echo "Pipeline: цель → спецификация → план → loop → проверка → приёмка"
echo
row "$(mark skill spec)" "Цель → спецификация" "skill tw:spec" "спецификаций: $specs${last_spec:+ · последняя: $(basename "$last_spec")}"
row "$(mark skill plan)" "Спецификация → план" "skill tw:plan" "планов: $plans_open открыто, $plans_done готово"
row "$(mark hook Stop)" "Loop до зелёных тестов" "Stop-hook" "${test_cmd:-тестов пока нет} · кругов ${max:-3}, потом субагент → человек"
row "$(mark hook Stop)" "Проверка" "Stop-hook" "последний прогон: ${last_test:-ещё не было}"
row "$(mark hook Stop)" "Scope" "Stop-hook" "diff против плана и «Не трогаем», бюджет ${budget:-400} строк${last_scope:+ · $last_scope}"
row "$(mark hook Stop)" "Независимая проверка" "Stop-hook" "свежий claude (${verify_model:-sonnet}) по спеке и diff${last_verify:+ · $last_verify}"
row "$(mark skill accept)" "Приёмка человеком" "/tw:accept" "карточка: вердикты, допущения, пункты [человек], diff"
row "·" "Перепланирование" "правило в tw:plan" "сначала правка плана и строка в журнале"
row "$(mark hook SessionStart)" "Ledger / память" "SessionStart + план" "план = ledger: статус, [x] после проверки, журнал"
row "$(mark hook PreToolUse)" "Guard" "PreToolUse" "секреты, код только через Edit/Write, $comments"
row "$(mark hook PostToolUse)" "Форматирование" "PostToolUse" "$prettier"

plan_block() {
  local p=$1 st=$2
  local total done acc_total acc_done next journal
  total=$(grep -cE '^- \[[ x]\] [0-9]+\.' "$p")
  done=$(grep -cE '^- \[x\] [0-9]+\.' "$p")
  acc_total=$(sed -n '/^## Приёмка/,/^## /p' "$p" | grep -cE '^- \[[ x]\]')
  acc_done=$(sed -n '/^## Приёмка/,/^## /p' "$p" | grep -cE '^- \[x\]')
  next=$(grep -m1 -E '^- \[ \] [0-9]+\.' "$p" | sed 's/^- \[ \] //' | perl -CSD -Mutf8 -pe 's/^(.{70}).+/$1…/')
  echo
  echo "  ${p#"$root"/}"
  echo "  статус: $st · задачи $done/$total · приёмка по спеке $acc_done/$acc_total"
  [ -n "$next" ] && echo "  следующая: $next"
  journal=$(sed -n '/^## Журнал/,$p' "$p" | grep -vE '^## |^$' | sed 's/^- //' | tail -3 | perl -CSD -Mutf8 -pe 's/^(.{100}).+/$1…/')
  [ -n "$journal" ] && { echo "  журнал:"; sed 's/^/    /' <<<"$journal"; }
}

open_found=0
for p in "$root"/docs/plans/*.md; do
  [ -f "$p" ] || continue
  st=$(plan_status "$p")
  case "$st" in готов*|брошен*) continue ;; esac
  [ $open_found -eq 0 ] && { echo; echo "Активная работа"; }
  open_found=1
  plan_block "$p" "$st"
done

if [ $open_found -eq 0 ]; then
  last=$(ls -t "$root"/docs/plans/*.md 2>/dev/null | head -1)
  if [ -n "$last" ]; then
    echo
    echo "Последний закрытый план"
    plan_block "$last" "$(plan_status "$last")"
  fi
fi
exit 0
