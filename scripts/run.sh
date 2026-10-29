#!/bin/bash
main() {
B="$(cd "$(dirname "$0")" && pwd)/backlog.sh"
plugin="$(cd "$(dirname "$0")/.." && pwd)"
root=$(bash "$B" root) || exit 2
cd "$root" || exit 2
export CLAUDE_PROJECT_DIR="$root"

state="$root/.claude/tw-state"
runs="$state/run"
log="$state/run.log"
limits="$state/limits"
pidfile="$state/run.pid"
slots="$state/slots"
mkdir -p "$runs" "$slots"

say() { echo "$(date '+%F %T') · $*" | tee -a "$log"; }
notify() {
  [ "$(jq -r '.runNotify' "$root/.claude/tw.json" 2>/dev/null)" = false ] && return 0
  osascript -e 'on run a' -e 'display notification (item 1 of a) with title (item 2 of a)' -e 'end run' "$1" "tw · $(basename "$root")" >/dev/null 2>&1
}
money() { printf '$%.2f' "${1:-0}"; }

if [ "$1" = stop ]; then
  bash "$B" running || { echo "исполнитель не идёт"; exit 0; }
  kill -TERM "$(cat "$pidfile")"
  while bash "$B" running; do sleep 1; done
  echo "исполнитель остановлен"; exit 0
fi
if ! [[ "${1:-0}" =~ ^[0-9]+$ ]]; then
  echo "run.sh: неизвестный аргумент «$1» — ожидаю число задач (0 — вся очередь) или stop" >&2
  exit 2
fi
if bash "$B" running; then
  echo "исполнитель уже идёт (pid $(cat "$pidfile")) — второй не запускаю" >&2
  exit 1
fi

local max=${1:-0}
cfg="$root/.claude/tw.json"
base=$(jq -r '.runBase // "main"' "$cfg")
threshold=$(jq -r '.runLimit // 95' "$cfg")
model=$(jq -r '.runModel // "sonnet"' "$cfg")
escalate=$(jq -r 'if has("runEscalate") then (.runEscalate // "") else "opus" end' "$cfg")
workers=$(jq -r '.runWorkers // 3' "$cfg")
wt1=$(jq -r '.runWorktree // empty' "$cfg"); wt1=${wt1:-.claude/worktrees/tw-run}
[[ "$wt1" = /* ]] || wt1="$root/$wt1"
pm=npm; [ -f pnpm-lock.yaml ] && pm=pnpm; [ -f yarn.lock ] && pm=yarn
allow=("Bash(git status *)" "Bash(git diff *)" "Bash(git log *)" "Bash(git show *)")
run_word=""; [ "$pm" = npm ] && run_word="run "
for name in $( { echo package.json; git ls-files '*package.json' | grep -v node_modules; } | sort -u | xargs jq -r '.scripts // {} | keys[]' 2>/dev/null | sort -u |
  grep -E '^(test|typecheck|lint|format|build|check|db:generate)(:|$)' | grep -vE 'watch|debug|dev|start|prod'); do
  allow+=("Bash($pm $run_word$name)" "Bash($pm $run_word$name *)")
  [ "$pm" = pnpm ] && allow+=("Bash(pnpm --filter * $name)" "Bash(pnpm --filter * $name *)")
done
for bin in vitest jest tsc eslint prettier; do
  allow+=("Bash($pm exec $bin *)")
  [ "$pm" = pnpm ] && allow+=("Bash(pnpm --filter * exec $bin *)")
done
while IFS= read -r a; do allow+=("$a"); done < <(jq -r '.runAllow // empty | .[]' "$cfg")
[ -n "$COMPOSE_PROJECT_NAME" ] || export COMPOSE_PROJECT_NAME=$(basename "$root" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')
plugins_off=$(jq -c '{enabledPlugins: ((.enabledPlugins // {}) | map_values(false))}' "$HOME/.claude/settings.json" 2>/dev/null || echo '{}')
. "$plugin/scripts/sandbox.sh"
export TW_SRT="" TW_CC_SANDBOX=""
if sandbox_on; then
  TW_SRT=$(sandbox_srt) || { echo "tw: нет srt — песочницы для проверок. Поставь: npm i -g @anthropic-ai/sandbox-runtime (или runSandbox: false в .claude/tw.json)"; exit 2; }
  TW_CC_SANDBOX=$(sandbox_claude)
  plugins_off=$(jq -c --argjson sb "$TW_CC_SANDBOX" '. + $sb' <<<"$plugins_off")
fi

[ -n "$(bash "$B" queue)" ] || { echo "tw: очередь пуста — исполнитель не запущен"; exit 0; }
echo $$ >"$pidfile"
rm -f "$slots"/*

slot_wt() { [ "$1" = 1 ] && echo "$wt1" || echo "$wt1-$1"; }

is_worktree() {
  [ -e "$1/.git" ] && [ "$(cd "$1" && git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" -ef "$(git rev-parse --path-format=absolute --git-common-dir)" ]
}

ensure_worktree() {
  local wt=$1
  if ! is_worktree "$wt"; then
    [ -e "$wt" ] && { say "$wt есть, но это не worktree проекта — разберись руками"; return 1; }
    git worktree prune
    if [[ "$wt" = "$root"/* ]] && ! git check-ignore -q "$wt"; then
      echo "/${wt#"$root"/}/" >>"$(git rev-parse --path-format=absolute --git-common-dir)/info/exclude"
    fi
    git worktree add -q --detach "$wt" "$base" || return 1
    say "worktree ${wt#"$root"/} от $base"
  fi
  bash "$B" wt-sync "$wt"
}

copied() {
  jq -e --arg f "$1" '.runCopy // [] | any(. as $c | $f == $c or ($f | startswith($c + "/")))' "$cfg" >/dev/null
}

kill_tree() {
  local c
  for c in $(pgrep -P "$1"); do kill_tree "$c"; done
  kill "$1" 2>/dev/null
}

save_limits() {
  grep '^{' "$1" | jq -c 'select(.type=="rate_limit_event") | .rate_limit_info.unifiedWindows.five_hour // empty' | tail -1 >"$limits.new"
  [ -s "$limits.new" ] && mv "$limits.new" "$limits" || rm -f "$limits.new"
}

limited() {
  [ -s "$limits" ] || return 1
  local used resets
  used=$(jq -r '(.utilization * 100) | floor' "$limits")
  resets=$(jq -r '.resetsAt' "$limits")
  [ "$used" -ge "$threshold" ] && [ "$resets" -gt "$(date +%s)" ]
}

hit_limit() {
  grep '^{' "$1" | jq -e 'select(.type=="result" and .is_error == true) | .result | test("limit"; "i")' >/dev/null 2>&1
}

worker() {
  local slot=$1 id=$2 wt wstate branch plan out res reason title task_model task_cost=0 cost=0 untracked cpid="" m ebranch="" lock="" why=""
  wt=$(slot_wt "$slot")
  wstate="$wt/.claude/tw-state"
  branch="tw/$id"
  w() { git -C "$wt" "$@"; }
  dirty() { local f; w status --porcelain -uall -- . ':!.claude' | cut -c4- | while IFS= read -r f; do copied "$f" || echo "$f"; done; }
  stage_task() {
    w add -u -- . ':!docs/backlog' ':!.claude'
    comm -13 <(sort "$untracked") <(w ls-files --others --exclude-standard | grep -vE '^(docs/backlog/|\.claude/)' | sort) | while IFS= read -r f; do
      copied "$f" || w add -- "$f"
    done
  }
  wip() { stage_task; w commit -qm "chore: wip backlog item $id" >/dev/null 2>&1; }
  release() { w checkout -q --detach; }
  result() { echo "$1 $cost${2:+ $2}" >"$slots/$slot.result"; exit 0; }
  stuck() {
    bash "$B" set "$id" Статус "застряла: $1" "исполнитель"
    say "$id · застряла: $1"
    notify "$id застряла: $1"
  }
  outcome() {
    local test verify plan_st human open
    test=$(cut -d' ' -f1 "$wstate/last-test" 2>/dev/null)
    verify=$(cut -d' ' -f1 "$wstate/last-verify" 2>/dev/null)
    plan_st=$(grep -m1 -oE '^\*\*Статус:\*\* .*' "$wt/$plan" 2>/dev/null | sed 's/^\*\*Статус:\*\* //')
    case "$test" in env) echo "env:сбой окружения"; return ;; red) echo "stuck:красные проверки"; return ;; esac
    case "$verify" in fail) echo "stuck:проверяющий не подтвердил"; return ;; error) echo "stuck:проверяющий не отработал"; return ;; esac
    open=$(grep -cE '^- \[ \] [0-9]+\.' "$wt/$plan" 2>/dev/null)
    human=$(grep -oE 'нужен человек: [^·]*' "$wt/$plan" 2>/dev/null | tail -1 | sed 's/ *$//')
    case "$plan_st" in брошен*) echo "stuck:план брошен${human:+ — $human}"; return ;; esac
    [ -f "$wt/$plan" ] && [ "${open:-0}" -eq 0 ] || { echo "stuck:${human:-план не закрыт (открыто задач: ${open:-?})}"; return; }
    [ "$verify" = ok ] || [ "$(jq -r '.verify' "$cfg")" = false ] || { echo "stuck:проверяющий не запускался"; return; }
    echo ok
  }
  prompt_for() {
    cat <<EOF
Задача $id из бэклога. План: $plan. Спецификация — по ссылке в плане.
Исполни план по разделу «Исполнение» skill tw:plan, с первой незакрытой задачи. Человека рядом нет: вопросов не задавай. Если без решения человека дальше нельзя — запиши в журнал плана «нужен человек: <что решить>» и закончи.
Не коммить, не меняй ветку и не трогай docs/backlog/ — это делает исполнитель. Лимиты тоже отслеживает исполнитель: rate-limits.json не читай. Код меняй только через Edit и Write, не через sed, perl или python. Команды Bash запускай по одной, без `;`, `&&`, скобок и перенаправления в файлы: составные команды требуют подтверждения, а подтвердить некому. Окружение (база, контейнеры) уже поднято — docker и infra-скрипты не запускай. Зависимости не добавляй и не меняй — ни командой, ни правкой package.json или lock-файла: утверждённые уже стоят (поле «Зависимости» задачи). Без новой зависимости никак — запиши в журнал плана «нужен человек: зависимость <имя> — <зачем>» и закончи. Bash работает в песочнице: писать можно только в этой папке, сети наружу нет.

Текст задачи:

$(cat "docs/backlog/$id.md")
EOF
  }
  integrate() {
    local old cmd
    lock="$state/$m.lock"
    until mkdir "$lock" 2>/dev/null; do sleep 1; done
    old=$(git rev-parse "refs/heads/$ebranch")
    w checkout -q --detach "$old"
    if ! w merge -q --no-ff --no-edit -m "feat: merge backlog item $id into $m" "$branch" >/dev/null 2>&1; then
      why="конфликт с эпиком $m: $(w diff --name-only --diff-filter=U | tr '\n' ' ' | sed 's/ *$//')"
      w merge --abort 2>/dev/null; rmdir "$lock"; lock=""; return 1
    fi
    local dchanged
    dchanged=$(bash "$B" deps-changed "$wt" "$(bash "$B" deps-ref "$id" "$old")" "$branch" | tr '\n' ' ' | sed 's/ $//')
    [ -z "$dchanged" ] || { why="ветка меняет зависимости ($dchanged) — их установка запускает чужой код, проверь и поставь сам"; w merge --abort 2>/dev/null; w checkout -q --detach "$old"; rmdir "$lock"; lock=""; return 1; }
    bash "$B" wt-deps "$wt" >/dev/null || { why="в эпике $m не встали зависимости"; rmdir "$lock"; lock=""; return 1; }
    cmd=$(CLAUDE_PROJECT_DIR="$wt" bash -c 'source "$1"; tw_check_cmd' _ "$plugin/hooks/lib.sh")
    if [ -n "$cmd" ] && ! (export CLAUDE_PROJECT_DIR="$wt" NO_COLOR=1 ${env_args[@]+"${env_args[@]}"} && sandboxed "$wt" "$cmd") >"$wstate/epic-check.log" 2>&1; then
      why="в эпике $m после слияния проверки красные (лог: ${wstate#"$root"/}/epic-check.log)"; rmdir "$lock"; lock=""; return 1
    fi
    git update-ref "refs/heads/$ebranch" "$(w rev-parse HEAD)" "$old" || { why="ветка $ebranch сдвинулась во время слияния"; rmdir "$lock"; lock=""; return 1; }
    rmdir "$lock"; lock=""
    git branch -q -D "$branch"
  }
  epic_ready() {
    local row
    row=$(bash "$B" epics | awk -F'\t' -v m="$m" '$1 == m')
    [ "$(cut -f2 <<<"$row")" = открыт ] || return 0
    local n=$(cut -f3 <<<"$row")
    [ "${n%/*}" = "${n#*/}" ] || return 0
    bash "$B" set "$m" Статус "на приёмке" "все задачи эпика в ветке $ebranch"
    say "$m · эпик готов к приёмке · $(cut -f4 <<<"$row")"
    notify "Эпик $m готов к приёмке: $(cut -f4 <<<"$row")"
  }
  interrupted() {
    [ -n "$lock" ] && rmdir "$lock" 2>/dev/null
    [ -n "$cpid" ] && kill_tree "$cpid"
    if [ -n "$untracked" ]; then
      wip; release
      bash "$B" set "$id" Статус готова "прогон остановлен посреди задачи"
    fi
    result requeue
  }
  trap interrupted TERM INT

  ensure_worktree "$wt" || result halt "worktree ${wt#"$root"/} не создаётся"
  if [ -n "$(dirty)" ]; then
    if w symbolic-ref -q HEAD >/dev/null; then
      local prev; prev=$(w branch --show-current)
      untracked=/dev/null; id_prev=${prev#tw/}
      w add -A -- . ':!.claude' && w commit -qm "chore: wip backlog item $id_prev" >/dev/null 2>&1
      untracked=""
      say "в ${wt#"$root"/} оставались правки — сохранены wip-коммитом в $prev"
    else
      result halt "в ${wt#"$root"/} незакоммиченные правки вне ветки, разберись"
    fi
  fi
  release 2>/dev/null

  plan=$(bash "$B" get "$id" План)
  if ! git rev-parse -q --verify "refs/heads/$branch" >/dev/null; then
    stuck "нет ветки с планом — подготовь через /tw:run"; result stuck
  fi
  if [ -z "$plan" ] || [ "$plan" = "—" ] || ! git cat-file -e "$branch:$plan" 2>/dev/null; then
    stuck "план не закоммичен в $branch — подготовь через /tw:run"; result stuck
  fi
  if ! w checkout -q "$branch"; then
    stuck "ветка $branch занята другим worktree"; result stuck
  fi
  m=$(bash "$B" get "$id" Эпик | grep -oE '^E[0-9]+')
  if [ -n "$m" ]; then
    ebranch="tw/$m"
    git rev-parse -q --verify "refs/heads/$ebranch" >/dev/null || { release; stuck "нет ветки эпика $ebranch"; result stuck; }
    w rebase -q "$ebranch" >/dev/null 2>&1 || w rebase --abort >/dev/null 2>&1
  fi
  bash "$B" set "$id" Статус "в работе" "исполнитель $slot, ветка $branch"
  bash "$B" set "$id" Ветка "$branch"

  local out_deps rc
  out_deps=$(bash "$B" wt-deps "$wt" "$(bash "$B" deps-ref "$id" "${ebranch:-$base}")"); rc=$?
  if [ $rc = 3 ]; then
    release; stuck "$out_deps"; result stuck
  elif [ $rc != 0 ]; then
    release
    stuck "сбой окружения: установка зависимостей (лог: ${wstate#"$root"/}/install.log)"; result env
  fi
  export TW_SANDBOX=""
  if [ -n "$TW_SRT" ]; then
    TW_SANDBOX="$state/sandbox/$slot.json"
    sandbox_profile "$wt" "$TW_SANDBOX"
  fi
  [ -n "$out_deps" ] && say "$id · $out_deps"

  untracked="$runs/$id.untracked"
  w ls-files --others --exclude-standard | sort >"$untracked"
  local env_args=() k v
  while IFS=$'\t' read -r k v; do [ -n "$k" ] && env_args+=("$k=${v//\{slot\}/$slot}"); done < <(jq -r '.runEnv // {} | to_entries[] | "\(.key)\t\(.value)"' "$cfg")

  task_model=$model
  while :; do
    rm -f "$wstate/last-test" "$wstate/last-verify" "$wstate/last-scope" "$wstate/checked" "$wstate/verify-$(basename "$plan" .md)"
    say "$id · старт в $branch · исполнитель $slot · $task_model"
    out="$runs/$id-$(date +%Y%m%d-%H%M%S).jsonl"
    args=(-p "$(prompt_for)" --permission-mode acceptEdits --output-format stream-json --verbose --allowedTools "${allow[@]}")
    [ -n "$task_model" ] && args+=(--model "$task_model")
    args+=(--plugin-dir "$plugin" --strict-mcp-config --settings "$plugins_off")
    (cd "$wt" && export CLAUDE_PROJECT_DIR="$wt" TW_SLOT="$slot" TW_DIFF_BASE=$(bash "$B" deps-ref "$id" "${ebranch:-$base}") ${env_args[@]+"${env_args[@]}"} && exec claude "${args[@]}") </dev/null >"$out" 2>&1 &
    cpid=$!
    wait "$cpid"
    cpid=""
    save_limits "$out"
    task_cost=$(grep '^{' "$out" | jq -s '[.[] | select(.type == "result") | .total_cost_usd // 0] | add // 0' 2>/dev/null)
    cost=$(awk -v a="$cost" -v b="${task_cost:-0}" 'BEGIN { print a + b }')

    if hit_limit "$out"; then
      say "$id · упёрлись в лимит посреди задачи — пауза и повтор"
      wip; release
      bash "$B" set "$id" Статус "готова" "лимит посреди задачи, повтор"
      local resets
      resets=$(grep '^{' "$out" | jq -r 'select(.type=="result") | .result' | grep -oE '[0-9]{10}' | tail -1)
      [ -n "$resets" ] || resets=$(($(date +%s) + 840))
      jq -n --argjson r "$resets" '{utilization: 1, resetsAt: $r}' >"$limits"
      result limit
    fi

    res=$(outcome)
    if [ "$res" = ok ]; then
      dchanged=$(bash "$B" deps-changed "$wt" "$(bash "$B" deps-ref "$id" "${ebranch:-$base}")" | tr '\n' ' ' | sed 's/ $//')
      [ -n "$dchanged" ] && res="stuck:нужен человек: агент изменил зависимости сверх утверждённых ($dchanged) — посмотри diff; нужны — утверди через /tw:run $id"
    fi
    for k in test scope verify; do echo "$k: $(cat "$wstate/last-$k" 2>/dev/null || echo 'не было')"; done >"$runs/$id.checks"
    rm -f "$runs/$id.verify"
    [ -f "$wstate/verify-$(basename "$plan" .md)" ] && cp "$wstate/verify-$(basename "$plan" .md)" "$runs/$id.verify"
    title=$(head -1 "docs/backlog/$id.md" | sed -E 's/^# B-[0-9]+ · //')
    case "$res" in
      ok)
        stage_task
        w commit -qm "feat: resolve backlog item $id" >/dev/null 2>&1
        if [ -n "$m" ]; then
          if ! integrate; then
            release; stuck "$why"; result stuck
          fi
          release
          bash "$B" set "$id" Статус "в эпике $m" "проверки зелёные, проверяющий подтвердил, слита в $ebranch"
          say "$id · в эпике $m · $(money "$cost") · $title"
          epic_ready
          result ok
        fi
        release
        bash "$B" set "$id" Статус "на приёмке" "проверки зелёные, проверяющий подтвердил"
        say "$id · на приёмке · $(money "$cost") · $title"
        result ok ;;
      env:*)
        wip; release
        stuck "${res#env:}"; result env ;;
    esac
    wip
    reason=${res#stuck:}
    denied=$(grep '^{' "$out" | jq -r 'select(.type=="result") | .permission_denials[]? | select(.tool_name=="Bash") | .tool_input.command // empty | select(test("[;&|()<>\\n]") | not)' 2>/dev/null | awk '!seen[$0]++' | head -3)
    rm -f "$runs/$id.denied"
    if [ -n "$denied" ]; then
      printf '%s\n' "$denied" >"$runs/$id.denied"
      reason="нет разрешения на \`$(head -1 <<<"$denied")\` — добавь в runAllow в .claude/tw.json · $reason"
    fi
    if [ -n "$escalate" ] && [ -z "$denied" ] && [ "$task_model" != "$escalate" ] && [[ "$reason" != нужен\ человек* && "$reason" != план\ брошен* ]]; then
      bash "$B" log "$id" "$task_model не справился ($reason), повтор на $escalate"
      say "$id · $reason на $task_model — повтор на $escalate"
      task_model=$escalate
      continue
    fi
    release
    stuck "$reason"; result stuck
  done
}

running=""
started=0; ok_count=0; stuck_count=0; cost_total=0; env_fails=0; halted=""
run_started=$(date +%s)

areas_busy() {
  local s
  for s in $running; do cat "$slots/${s%%:*}.area"; done
}

overlaps() {
  awk 'NR == FNR { if ($0 == "*") all = 1; a[NR] = $0; n = NR; next }
       { if ($0 == "*" || all) { hit = 1; exit } for (i = 1; i <= n; i++) { p = a[i]; q = $0; if (p == q || index(q, p "/") == 1 || index(p, q "/") == 1) { hit = 1; exit } } }
       END { exit hit ? 0 : 1 }' "$1" -
}

pick() {
  local id deps busy
  busy=$(areas_busy)
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    deps=$(bash "$B" deps "$id")
    if grep -qE ' (отклонена|нет)' <<<"$deps"; then
      bash "$B" queue-del "$id"
      bash "$B" set "$id" Статус "застряла: зависимость не будет выполнена ($(tr '\n' ' ' <<<"$deps" | sed 's/ *$//'))" "исполнитель"
      say "$id · застряла: зависимость не будет выполнена"
      echo "$id" >>"$slots/dep-stuck"
      continue
    fi
    [ -z "$deps" ] || continue
    bash "$B" area "$id" >"$slots/next.area"
    [ -n "$busy" ] && overlaps "$slots/next.area" <<<"$busy" && continue
    echo "$id"; return 0
  done < <(bash "$B" queue)
  return 1
}

free_slot() {
  local n
  for n in $(seq 1 "$workers"); do
    grep -qE "(^| )$n:" <<<" $running" || { echo "$n"; return 0; }
  done
  return 1
}

reap() {
  local s slot pid id r kind cost rest
  if [ -s "$slots/dep-stuck" ]; then
    stuck_count=$((stuck_count + $(grep -c . "$slots/dep-stuck"))); rm -f "$slots/dep-stuck"
  fi
  for s in $running; do
    slot=${s%%:*}; pid=${s#*:}; pid=${pid%%:*}; id=${s##*:}
    kill -0 "$pid" 2>/dev/null && continue
    wait "$pid" 2>/dev/null
    running=$(tr ' ' '\n' <<<"$running" | grep -vx "$s" | tr '\n' ' ' | sed 's/ *$//')
    r=$(cat "$slots/$slot.result" 2>/dev/null); rm -f "$slots/$slot.result" "$slots/$slot.area"
    kind=${r%% *}; rest=${r#* }; cost=${rest%% *}; [ "$rest" = "$cost" ] && rest="" || rest=${rest#* }
    cost_total=$(awk -v a="$cost_total" -v b="${cost:-0}" 'BEGIN { print a + b }')
    case "$kind" in
      ok) ok_count=$((ok_count + 1)); env_fails=0 ;;
      stuck) stuck_count=$((stuck_count + 1)); env_fails=0 ;;
      env) stuck_count=$((stuck_count + 1)); env_fails=$((env_fails + 1))
        [ "$env_fails" -ge 2 ] && halted="два сбоя окружения подряд — стоп" ;;
      limit|requeue) bash "$B" queue-front "$id"; started=$((started - 1)) ;;
      halt) bash "$B" queue-front "$id"; started=$((started - 1)); halted="$rest — стоп" ;;
      *) bash "$B" queue-front "$id"; started=$((started - 1)); halted="исполнитель $slot упал на $id без итога — стоп" ;;
    esac
  done
}

summary() {
  local m=$((($(date +%s) - run_started) / 60))
  say "итог · на приёмке $ok_count · застряло $stuck_count · $(money "$cost_total") · $m мин"
  notify "Прогон закончен: на приёмке $ok_count, застряло $stuck_count, $(money "$cost_total"), $m мин${1:+ · $1}"
}

shutdown() {
  trap '' TERM INT
  local s
  for s in $running; do s=${s#*:}; kill -TERM "${s%%:*}" 2>/dev/null; done
  for s in $running; do s=${s#*:}; wait "${s%%:*}" 2>/dev/null; done
  reap
  say "остановлен"
  summary "остановлен"
  exit 143
}

trap 'rm -f "$pidfile"' EXIT
trap shutdown TERM INT
say "старт · очередь: $(bash "$B" queue | tr '\n' ' ')· исполнителей до $workers"
setup=$(jq -r '.setup // empty' "$cfg")
if [ -n "$setup" ]; then
  if (eval "$setup") >"$state/setup.log" 2>&1; then
    say "окружение поднято: $setup"
  else
    say "окружение не поднялось: $setup (лог: .claude/tw-state/setup.log) — стоп"
    summary "окружение не поднялось"
    exit 1
  fi
fi

while :; do
  reap
  [ -n "$halted" ] && [ -z "$running" ] && { say "$halted"; summary "$halted"; exit 1; }
  if [ -z "$halted" ] && { [ "$max" -eq 0 ] || [ "$started" -lt "$max" ]; } && slot=$(free_slot); then
    if limited; then
      if [ -z "$running" ]; then
        used=$(jq -r '(.utilization * 100) | floor' "$limits"); resets=$(jq -r '.resetsAt' "$limits")
        say "лимит five_hour $used % ≥ $threshold % — пауза до $(date -r $((resets + 60)) '+%H:%M')"
        sleep "${TW_RUN_SLEEP:-$((resets + 60 - $(date +%s)))}" &
        wait $!
        rm -f "$limits"
        continue
      fi
    elif id=$(pick); then
      bash "$B" queue-del "$id"
      cp "$slots/next.area" "$slots/$slot.area"
      worker "$slot" "$id" &
      running="${running:+$running }$slot:$!:$id"
      started=$((started + 1))
      continue
    fi
  fi
  if [ -z "$running" ]; then
    left=$(bash "$B" queue | tr '\n' ' ' | sed 's/ *$//')
    [ -n "$left" ] && [ -z "$halted" ] && { [ "$max" -eq 0 ] || [ "$started" -lt "$max" ]; } && say "в очереди остались задачи с невыполненными зависимостями: $left"
    [ "$max" -gt 0 ] && [ "$started" -ge "$max" ] && say "достигнут предел $max задач"
    break
  fi
  sleep "${TW_RUN_TICK:-2}" &
  wait $!
done

say "конец · обработано: $((ok_count + stuck_count))"
summary
}

main "$@"
exit
