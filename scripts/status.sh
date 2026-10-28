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
  [ -f "$root/yarn.lock" ] && test_cmd="yarn test"
  [ -f "$root/pnpm-lock.yaml" ] && test_cmd="pnpm test"
fi
check_cmd=$(get .check)
env_st=$(cat "$state/env" 2>/dev/null | cut -d' ' -f2-)
teardown=$(get .teardown)
max=$(get .maxRounds)
last_test=$(cat "$state/last-test" 2>/dev/null)
last_scope=$(cat "$state/last-scope" 2>/dev/null)
last_verify=$(cat "$state/last-verify" 2>/dev/null)
verify_model=$(get .verifyModel)
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
row "$(mark hook Stop)" "Loop до зелёных тестов" "Stop-hook" "${check_cmd:-${test_cmd:-тестов пока нет}} · кругов ${max:-3}, потом субагент → человек"
[ -n "$(get .setup)" ] && row "$(mark hook Stop)" "Окружение" "Stop-hook" "$(get .setup) · $( [ -n "$env_st" ] && echo "поднято tw $env_st" || echo "ещё не поднималось")${teardown:+ · остановить: $teardown}"
row "$(mark hook Stop)" "Проверка" "Stop-hook" "последний прогон: ${last_test:-ещё не было}"
row "$(mark hook Stop)" "Scope" "Stop-hook" "diff против плана и «Не трогаем»${last_scope:+ · $last_scope}"
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

if [ -d "$root/docs/backlog" ]; then
  backlog=$(CLAUDE_PROJECT_DIR="$root" bash "$PLUGIN/scripts/backlog.sh" list)
  count() { awk -F'\t' -v s="$1" 'index($4, s) == 1' <<<"$backlog" | grep -c .; }
  queued=$(grep -c . "$state/queue" 2>/dev/null)
  echo
  echo "Бэклог · docs/backlog/"
  echo "  входящих $(count входящая) · готовых $(count готова) · в очереди ${queued:-0} · на приёмке $(count 'на приёмке') · в вехах $(count 'в вехе') · принято $(count принята)"
  CLAUDE_PROJECT_DIR="$root" bash "$PLUGIN/scripts/backlog.sh" milestones | while IFS=$'\t' read -r m st n title; do
    echo "  $m · $st · задач в вехе $n · $title"
  done | perl -CSD -Mutf8 -pe 's/^(.{100}).+/$1…/'
  runlog="$state/run.log"
  if [ -f "$runlog" ]; then
    last=$(awk '/ · старт · /{buf=""} {buf = buf $0 "\n"} END{printf "%s", buf}' "$runlog")
    started=$(head -1 <<<"$last" | cut -d' ' -f1,2)
    ok=$(grep -cE ' · (на приёмке|в вехе M[0-9]+) · ' <<<"$last")
    stuck=$(grep -c ' · застряла: ' <<<"$last")
    busy=$(awk -F'\t' '$4 == "в работе" { print $1 }' <<<"$backlog")
    if CLAUDE_PROJECT_DIR="$root" bash "$PLUGIN/scripts/backlog.sh" running; then
      run_st="идёт с $started${busy:+, сейчас $(tr '\n' ' ' <<<"$busy" | sed 's/ $//')} (остановить: bash $PLUGIN/scripts/run.sh stop)"
    else
      run_st="последний с $started"; busy=""
    fi
    echo "  прогон: $run_st · сделано $ok · застряло $stuck · ждёт приёмки $(count 'на приёмке')"
    wt1=$(get .runWorktree); wt1=${wt1:-.claude/worktrees/tw-run}
    [[ "$wt1" = /* ]] || wt1="$root/$wt1"
    for cur in $busy; do
      slot=$(grep -oE 'исполнитель [0-9]+' "$root/docs/backlog/$cur.md" | tail -1 | grep -oE '[0-9]+')
      wt=$wt1; [ "${slot:-1}" != 1 ] && wt="$wt1-$slot"
      cur_plan=$(CLAUDE_PROJECT_DIR="$root" bash "$PLUGIN/scripts/backlog.sh" get "$cur" План)
      [ -n "$cur_plan" ] && [ -f "$wt/$cur_plan" ] && plan_block "$wt/$cur_plan" "$(plan_status "$wt/$cur_plan") · исполнитель ${slot:-1}, $cur"
    done
  fi
  awk -F'\t' 'index($4, "застряла") == 1 { print "  " $1 " · " $4 }' <<<"$backlog" | perl -CSD -Mutf8 -pe 's/^(.{100}).+/$1…/'
fi

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
