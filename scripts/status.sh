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

if [ "$1" = full ]; then
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
  exit 0
fi

cut_to() { perl -CSD -Mutf8 -pe "s/^(.{$1}).+/\$1…/"; }
B="$PLUGIN/scripts/backlog.sh"
bl() { CLAUDE_PROJECT_DIR="$root" bash "$B" "$@"; }
short() { H="$HOME" perl -pe 's/^\Q$ENV{H}\E/~/i' <<<"$1"; }
title() { head -1 "$root/docs/backlog/$1.md" | sed -E 's/^# [BE]-?[0-9]+ · //'; }
resume_cmd() {
  local r sid cwd
  r=$(ls -t "$state/run/$1"-*.jsonl 2>/dev/null | head -1)
  [ -n "$r" ] || return
  sid=$(grep -m1 '"subtype":"init"' "$r" | jq -r '.session_id // empty' 2>/dev/null)
  cwd=$(grep -m1 '"subtype":"init"' "$r" | jq -r '.cwd // empty' 2>/dev/null)
  [ -n "$sid" ] && echo "cd $(short "$cwd") && claude --resume $sid"
}

cd "$root" || exit 0
branch=$(git branch --show-current 2>/dev/null)
dirty=$(git status --porcelain --untracked-files=no -- . ':!docs/backlog' 2>/dev/null | grep -c .)
echo "tw · ${root/#$HOME/~} · ${branch:-?}$([ "$dirty" -gt 0 ] && echo ", незакоммиченных файлов: $dirty" || echo ", чисто")"

cmds=()
cmd() { cmds+=("$(printf '%s\t%s' "$1" "$2")"); }

if [ -d "$root/docs/backlog" ]; then
  backlog=$(bl list)
  count() { awk -F'\t' -v s="$1" 'index($4, s) == 1' <<<"$backlog" | grep -c .; }
  runlog="$state/run.log"
  echo
  if [ -f "$runlog" ]; then
    last=$(awk '/ · старт · /{buf=""} {buf = buf $0 "\n"} END{printf "%s", buf}' "$runlog")
    started=$(head -1 <<<"$last" | cut -c6-16 | sed -E 's/^([0-9]+)-([0-9]+) /\2.\1 /')
    if bl running; then
      busy=$(awk -F'\t' '$4 == "в работе" { print $1 }' <<<"$backlog")
      echo "Исполнитель идёт с $started · в работе: $(grep -c . <<<"$busy")"
      wt1=$(get .runWorktree); wt1=${wt1:-.claude/worktrees/tw-run}
      [[ "$wt1" = /* ]] || wt1="$root/$wt1"
      for cur in $busy; do
        line=$(grep " · $cur · старт в " <<<"$last" | tail -1)
        slot=$(grep -oE 'исполнитель [0-9]+' <<<"$line" | grep -oE '[0-9]+')
        model=$(sed -nE 's/.* · исполнитель [0-9]+ · ([a-z0-9-]+)$/\1/p' <<<"$line")
        t0=$(date -j -f '%Y-%m-%d %H:%M:%S' "$(cut -c1-19 <<<"$line")" +%s 2>/dev/null)
        mins=""; [ -n "$t0" ] && mins="$(( ($(date +%s) - t0) / 60 )) мин"
        wt=$wt1; [ "${slot:-1}" != 1 ] && wt="$wt1-$slot"
        p=$(bl get "$cur" План); prog=""; next=""
        if [ -n "$p" ] && [ -f "$wt/$p" ]; then
          prog="план $(grep -cE '^- \[x\] [0-9]+\.' "$wt/$p")/$(grep -cE '^- \[[ x]\] [0-9]+\.' "$wt/$p")"
          next=$(grep -m1 -E '^- \[ \] [0-9]+\.' "$wt/$p" | sed 's/^- \[ \] //')
        fi
        echo "  $cur · исполнитель ${slot:-1}${model:+ · $model}${mins:+ · $mins}${prog:+ · $prog} · $(title "$cur")" | cut_to 110
        [ -n "$next" ] && echo "         сейчас: $next" | cut_to 110
      done
      cmd "bash $(short "$PLUGIN")/scripts/watch.sh" "смотреть ход"
      cmd "bash $(short "$PLUGIN")/scripts/run.sh stop" "остановить после текущих задач"
    else
      sum=$(grep ' · итог · ' <<<"$last" | tail -1 | sed 's/.* · итог · //')
      echo "Исполнитель не идёт · последний прогон $started${sum:+ · $sum}"
    fi
  else
    echo "Исполнитель ещё не запускался"
  fi

  waiting=$(awk -F'\t' 'index($4, "на приёмке") == 1 || index($4, "застряла") == 1 { print $1 "\t" $4 }' <<<"$backlog")
  epics=$(bl epics)
  epics_ready=$(awk -F'\t' '$2 == "на приёмке" { print $1 }' <<<"$epics")
  if [ -n "$waiting$epics_ready" ]; then
    echo
    echo "Ждут тебя"
    for e in $epics_ready; do
      echo "  $e · эпик на приёмке · $(title "$e")" | cut_to 110
      cmd "/tw:accept $e" "принять эпик $e целиком"
    done
    while IFS=$'\t' read -r id st; do
      [ -n "$id" ] || continue
      case "$st" in
        "на приёмке"*)
          echo "  $id · на приёмке · $(title "$id")" | cut_to 110
          cmd "/tw:accept $id" "посмотреть карточку и принять"
          ;;
        *)
          echo "  $id · застряла · $(title "$id")" | cut_to 110
          echo "         ${st#застряла: }" | cut_to 110
          if [ -s "$state/run/$id.denied" ]; then
            cmd "runAllow в .claude/tw.json" "разрешить: $(head -1 "$state/run/$id.denied" | sed -E 's/.*/Bash(&)/')"
          fi
          cmd "/tw:accept $id" "что сделано и что нет у $id"
          r=$(resume_cmd "$id"); [ -n "$r" ] && cmd "$r" "разговор исполнителя $id"
          cmd "/tw:run $id" "повторить в той же ветке"
          ;;
      esac
    done <<<"$waiting"
  fi

  echo
  queued=$(grep -c . "$state/queue" 2>/dev/null)
  echo "Бэклог: входящих $(count входящая) · готовых $(count готова) · в очереди ${queued:-0} · в эпиках $(count 'в эпике') · принято $(count принята)"
  while IFS=$'\t' read -r e st n t; do
    [ -n "$e" ] && echo "  $e · $st · $n · $t" | cut_to 110
  done <<<"$epics"
fi

for p in "$root"/docs/plans/*.md; do
  [ -f "$p" ] || continue
  st=$(plan_status "$p")
  case "$st" in готов*|брошен*) continue ;; esac
  echo "В папке проекта: ${p#"$root"/} · $st · задачи $(grep -cE '^- \[x\] [0-9]+\.' "$p")/$(grep -cE '^- \[[ x]\] [0-9]+\.' "$p")" | cut_to 110
done

bl running 2>/dev/null || cmd "/tw:run" "набрать задачи и запустить исполнителя"
cmd "/tw:scout · /tw:task" "найти проблемы · записать задачу"
cmd "/tw:status full" "настройки конвейера и проверок"
echo
echo "Команды"
printf '%s\n' "${cmds[@]}" | awk -F'\t' '!seen[$1]++' | while IFS=$'\t' read -r c d; do
  if [ ${#c} -le 28 ]; then perl -CSA -e 'printf "  %-28s %s\n", @ARGV' "$c" "$d"; else echo "  $d:"; echo "    $c"; fi
done
exit 0
