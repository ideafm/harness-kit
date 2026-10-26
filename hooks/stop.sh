#!/bin/bash
input=$(cat)
source "$(dirname "$0")/lib.sh"

checked="$TW_STATE/checked"
trail=""
stage() { trail+="tw ▸ $1"$'\n'; }
fresh() { [ -f "$1" ] && [ "$(stat -f %m "$1")" != 0 ] && cut -d' ' -f1,4- "$1"; }
digest() {
  local clean n
  clean=$(sed $'s/\x1b\\[[0-9;]*[a-zA-Z]//g' "$1")
  n=$(wc -l <<<"$clean" | tr -d ' ')
  if [ "$n" -le 60 ]; then
    echo "$clean"
    return
  fi
  grep -iE -A4 'fail|error|×|✗|expected|received|assert|:[0-9]+:[0-9]+' <<<"$clean" | grep -vE '^\s*$' | head -60
  echo "(выжимка; полный лог: .claude/tw-state/test.log, $n строк)"
}
emit() {
  local out="${1:-}"
  [ -n "$out" ] || out='{}'
  jq --arg t "${trail%$'\n'}" '.systemMessage = ([$t, (.systemMessage // empty)] | map(select(. != "")) | join("\n"))' <<<"$out"
}
if [ -f "$checked" ]; then
  changed=$(find "$TW_ROOT" \( -path "$TW_ROOT/node_modules" -o -path "$TW_ROOT/.git" -o -path "$TW_ROOT/.claude" \) -prune -o -newer "$checked" -print -quit)
  [ -n "$changed" ] || exit 0
fi

after_tests() {
  local step out msgs="" name
  for step in scope verify; do
    [ -f "$TW_STATE/last-$step" ] && touch -t 197001010000 "$TW_STATE/last-$step"
    out=$("$(dirname "$0")/$step.sh" <<<"$input")
    [ "$step" = scope ] && name="scope" || name="проверяющий"
    stage "$name: $(fresh "$TW_STATE/last-$step" || echo пропущен)"
    [ -n "$out" ] || continue
    if [ "$(jq -r '.decision // empty' <<<"$out")" = "block" ]; then
      stage "блок — агент дорабатывает"
      emit "$out"
      exit 0
    fi
    msgs+=$(jq -r '.systemMessage // empty' <<<"$out")$'\n'
  done
  touch "$checked"
  [ -n "${msgs//$'\n'/}" ] && out=$(jq -n --arg m "${msgs%$'\n'}" '{systemMessage: $m}') || out=""
  emit "$out"
  exit 0
}

test_cmd=$(tw_check_cmd)
if [ -z "$test_cmd" ]; then
  echo "нет тестов" >"$TW_STATE/last-test"
  stage "тесты: нет команды проверок"
  after_tests
fi
max=$(tw_get .maxRounds); max=${max:-3}
effort=$(tw_get .escalateEffort); effort=${effort:-high}

round_file="$TW_STATE/stop-$sid"
log="$TW_STATE/test.log"

sid=$(jq -r '.session_id // "default"' <<<"$input")
env_re='ECONNREFUSED|ENOTFOUND|EADDRNOTAVAIL|Cannot connect to the Docker daemon|Is the docker daemon running|could not connect to server|Connection refused'
env_fail() {
  echo "env $(date '+%Y-%m-%d %H:%M')" >"$TW_STATE/last-test"
  stage "окружение: $1 — нужен человек"
  emit "$(jq -n --arg m "tw: проверки не запустились из-за окружения, а не кода ($1). Подними окружение${2:+ ($2)} — агента не блокирую. Лог: .claude/tw-state/$3" '{systemMessage: $m}')"
  exit 0
}

setup=$(tw_get .setup)
teardown=$(tw_get .teardown)
env_file="$TW_STATE/env"
run_setup() {
  (cd "$TW_ROOT" && eval "$setup") >"$TW_STATE/setup.log" 2>&1 || env_fail "setup упал" "$setup" setup.log
  echo "$sid $(date '+%Y-%m-%d %H:%M')" >"$env_file"
  stage "окружение поднято ($setup)${teardown:+ — остаётся работать, остановить: $teardown}"
}
run_check() { (cd "$TW_ROOT" && NO_COLOR=1 FORCE_COLOR=0 eval "$test_cmd") >"$log" 2>&1; }

if [ -n "$setup" ] && [ "$(cut -d' ' -f1 "$env_file" 2>/dev/null)" != "$sid" ]; then
  run_setup
fi

passed=0
run_check && passed=1
if [ "$passed" = 0 ] && [ -n "$setup" ] && grep -qE "$env_re" "$log"; then
  run_setup
  run_check && passed=1
fi

if [ "$passed" = 1 ]; then
  rm -f "$round_file"
  echo "green $(date '+%Y-%m-%d %H:%M')" >"$TW_STATE/last-test"
  stage "тесты: зелёные ($test_cmd)"
  after_tests
fi

env_hit=$(grep -m1 -oE "$env_re[^\"'}]{0,40}" "$log")
[ -n "$env_hit" ] && env_fail "$env_hit" "$setup" test.log

round=0; last_sig=""
[ -f "$round_file" ] && read -r round last_sig <"$round_file"
round=$((round + 1))
echo "red $(date '+%Y-%m-%d %H:%M') круг $round" >"$TW_STATE/last-test"
sig=$(grep -iE 'fail|error|×|✗' "$log" | sed 's/[0-9]//g' | shasum | cut -c1-12)
tail=$(digest "$log")

if [ "$round" -gt "$max" ] || { [ "$sig" = "$last_sig" ] && [ -f "$round_file.escalated" ]; }; then
  rm -f "$round_file" "$round_file.escalated"
  touch "$checked"
  stage "тесты: красные — нужен человек"
  emit "$(jq -n --arg r "$((round - 1))" '{systemMessage: ("tw: тесты красные после " + $r + " кругов — нужен человек. Лог: .claude/tw-state/test.log")}')"
  exit 0
fi

echo "$round $sig" >"$round_file"

if [ "$round" -eq "$max" ] || [ "$sig" = "$last_sig" ]; then
  touch "$round_file.escalated"
  tp=$(jq -r '.transcript_path // empty' <<<"$input")
  cur_model=""; cur_effort=""
  if [ -f "$tp" ]; then
    cur_model=$(jq -r 'select(.type=="assistant") | .message.model // empty' "$tp" 2>/dev/null | tail -1)
    cur_effort=$(jq -r '.message.output_config.effort? // empty' "$tp" 2>/dev/null | tail -1)
  fi
  case "$cur_model" in
    *opus*|*fable*)
      case "$cur_effort" in low) up=medium ;; medium) up=high ;; high) up=xhigh ;; xhigh|max) up=max ;; *) up=$effort ;; esac
      target="model \"$( [[ $cur_model == *fable* ]] && echo fable || echo opus )\", effort \"$up\"" ;;
    "") target="effort \"$effort\"" ;;
    *) target="model \"opus\"${cur_effort:+, effort \"$cur_effort\"}" ;;
  esac
  stage "эскалация: ${cur_model:-модель ?}${cur_effort:+/$cur_effort} → $target"
  reason="Проверки красные, круг $round из $max, починка не продвигается. Не чини сам: запусти свежего субагента (Agent) с $target, передай ему задачу, что менялось и этот вывод тестов. Когда он закончит — проверь результат.

$tail"
else
  reason="Проверки красные ($test_cmd), круг $round из $max. Почини и только потом заканчивай.

$tail"
fi

stage "тесты: красные, круг $round из $max — агент чинит"
emit "$(jq -n --arg reason "$reason" '{decision: "block", reason: $reason}')"
