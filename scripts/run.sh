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
mkdir -p "$runs"

say() { echo "$(date '+%F %T') · $*" | tee -a "$log"; }

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
echo $$ >"$pidfile"
trap 'rm -f "$pidfile"' EXIT

local max=${1:-0}
cfg="$root/.claude/tw.json"
base=$(jq -r '.runBase // "main"' "$cfg")
threshold=$(jq -r '.runLimit // 95' "$cfg")
model=$(jq -r '.runModel // "sonnet"' "$cfg")
escalate=$(jq -r 'if has("runEscalate") then (.runEscalate // "") else "opus" end' "$cfg")
escalated=""
wt=$(jq -r '.runWorktree // empty' "$cfg"); wt=${wt:-.claude/worktrees/tw-run}
[[ "$wt" = /* ]] || wt="$root/$wt"
pm=npm; [ -f pnpm-lock.yaml ] && pm=pnpm; [ -f yarn.lock ] && pm=yarn
allow=()
while IFS= read -r a; do allow+=("$a"); done < <(jq -r '.runAllow // empty | .[]' "$cfg")
[ ${#allow[@]} -gt 0 ] || allow=("Bash($pm:*)" "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)")
[ -n "$COMPOSE_PROJECT_NAME" ] || export COMPOSE_PROJECT_NAME=$(basename "$root" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')

w() { command git -C "$wt" "$@"; }
wstate="$wt/.claude/tw-state"

is_worktree() {
  [ -e "$wt/.git" ] && [ "$(cd "$wt" && command git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" -ef "$(git rev-parse --path-format=absolute --git-common-dir)" ]
}

ensure_worktree() {
  if ! is_worktree; then
    [ -e "$wt" ] && { say "$wt есть, но это не worktree проекта — разберись руками"; return 1; }
    git worktree prune
    if [[ "$wt" = "$root"/* ]] && ! git check-ignore -q "$wt"; then
      echo "/${wt#"$root"/}/" >>"$(git rev-parse --path-format=absolute --git-common-dir)/info/exclude"
    fi
    git worktree add -q --detach "$wt" "$base" || return 1
    say "worktree $wt от $base"
  fi
  bash "$B" wt-sync "$wt"
}

install_deps() {
  local out rc
  out=$(bash "$B" wt-deps "$wt"); rc=$?
  [ -n "$out" ] && say "$out"
  return $rc
}

copied() {
  jq -e --arg f "$1" '.runCopy // [] | any(. as $c | $f == $c or ($f | startswith($c + "/")))' "$cfg" >/dev/null
}

dirty() {
  local f
  w status --porcelain -uall -- . ':!.claude' | cut -c4- | while IFS= read -r f; do copied "$f" || echo "$f"; done
}

stage_task() {
  w add -u -- . ':!docs/backlog' ':!.claude'
  comm -13 <(sort "$1") <(w ls-files --others --exclude-standard | grep -vE '^(docs/backlog/|\.claude/)' | sort) | while IFS= read -r f; do
    copied "$f" || w add -- "$f"
  done
}

wip() {
  stage_task "$1"
  w commit -qm "chore: wip backlog item $2" >/dev/null 2>&1
}

release() { w checkout -q --detach; }

kill_tree() {
  local c
  for c in $(pgrep -P "$1"); do kill_tree "$c"; done
  kill "$1" 2>/dev/null
}

stopped() {
  [ -n "$cpid" ] && kill_tree "$cpid"
  if [ -n "$id" ] && [ -n "$untracked" ]; then
    wip "$untracked" "$id"; release
    bash "$B" set "$id" Статус готова "прогон остановлен посреди задачи"
  fi
  say "остановлен"
  exit 143
}

save_limits() {
  grep '^{' "$1" | jq -c 'select(.type=="rate_limit_event") | .rate_limit_info.unifiedWindows.five_hour // empty' | tail -1 >"$limits.new"
  [ -s "$limits.new" ] && mv "$limits.new" "$limits" || rm -f "$limits.new"
}

wait_limits() {
  [ -s "$limits" ] || return 0
  local used resets now
  used=$(jq -r '(.utilization * 100) | floor' "$limits")
  resets=$(jq -r '.resetsAt' "$limits")
  now=$(date +%s)
  [ "$used" -ge "$threshold" ] && [ "$resets" -gt "$now" ] || return 0
  say "лимит five_hour $used % ≥ $threshold % — пауза до $(date -r $((resets + 60)) '+%H:%M')"
  sleep "${TW_RUN_SLEEP:-$((resets + 60 - now))}" &
  wait $!
  rm -f "$limits"
}

hit_limit() {
  grep '^{' "$1" | jq -e 'select(.type=="result" and .is_error == true) | .result | test("limit"; "i")' >/dev/null 2>&1
}

outcome() {
  local plan=$1 test verify plan_st human open
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
Задача $1 из бэклога. План: $2. Спецификация — по ссылке в плане.
Исполни план по разделу «Исполнение» skill tw:plan, с первой незакрытой задачи. Человека рядом нет: вопросов не задавай. Если без решения человека дальше нельзя — запиши в журнал плана «нужен человек: <что решить>» и закончи.
Не коммить, не меняй ветку и не трогай docs/backlog/ — это делает исполнитель. Лимиты тоже отслеживает исполнитель: rate-limits.json не читай.

Текст задачи:

$(cat "docs/backlog/$1.md")
EOF
}

stuck() {
  bash "$B" set "$1" Статус "застряла: $2" "исполнитель"
  say "$1 · застряла: $2"
}

done_count=0
env_fails=0
cpid=""; id=""; untracked=""
trap stopped TERM INT
[ -n "$(bash "$B" queue)" ] || { echo "tw: очередь пуста — исполнитель не запущен"; exit 0; }
say "старт · очередь: $(bash "$B" queue | tr '\n' ' ')· worktree ${wt#"$root"/}"
ensure_worktree || { say "не удалось создать worktree $wt — стоп"; exit 1; }

while id=$(bash "$B" queue-next) && [ -n "$id" ]; do
  [ "$max" -gt 0 ] && [ "$done_count" -ge "$max" ] && { say "достигнут предел $max задач"; break; }
  wait_limits
  ensure_worktree || { say "worktree пропал и не создаётся — стоп"; exit 1; }

  if [ -n "$(dirty)" ]; then
    if w symbolic-ref -q HEAD >/dev/null; then
      wip /dev/null "$(w branch --show-current | sed 's#^tw/##')"
      say "в worktree оставались правки — сохранены wip-коммитом в $(w branch --show-current)"
    else
      say "в worktree незакоммиченные правки вне ветки — стоп, разберись: $wt"; exit 1
    fi
  fi
  release 2>/dev/null

  branch="tw/$id"
  plan=$(bash "$B" get "$id" План)
  if ! git rev-parse -q --verify "refs/heads/$branch" >/dev/null; then
    stuck "$id" "нет ветки с планом — подготовь через /tw:run"; bash "$B" queue-pop; continue
  fi
  if [ -z "$plan" ] || [ "$plan" = "—" ] || ! git cat-file -e "$branch:$plan" 2>/dev/null; then
    stuck "$id" "план не закоммичен в $branch — подготовь через /tw:run"; bash "$B" queue-pop; continue
  fi
  if ! w checkout -q "$branch"; then
    stuck "$id" "ветка $branch занята другим worktree"; bash "$B" queue-pop; continue
  fi
  bash "$B" set "$id" Статус "в работе" "исполнитель, ветка $branch"
  bash "$B" set "$id" Ветка "$branch"

  if ! install_deps; then
    release
    stuck "$id" "сбой окружения: установка зависимостей (лог: ${wstate#"$root"/}/install.log)"
    bash "$B" queue-pop
    env_fails=$((env_fails + 1))
    [ "$env_fails" -ge 2 ] && { say "два сбоя окружения подряд — стоп"; exit 1; }
    continue
  fi

  rm -f "$wstate/last-test" "$wstate/last-verify" "$wstate/last-scope" "$wstate/checked" "$wstate/verify-$(basename "$plan" .md)"
  untracked="$runs/$id.untracked"
  w ls-files --others --exclude-standard | sort >"$untracked"
  say "$id · старт в $branch"

  out="$runs/$id-$(date +%Y%m%d-%H%M%S).jsonl"
  args=(-p "$(prompt_for "$id" "$plan")" --permission-mode acceptEdits --output-format stream-json --verbose --allowedTools "${allow[@]}")
  task_model=$model; [ "$escalated" = "$id" ] && task_model=$escalate
  [ -n "$task_model" ] && args+=(--model "$task_model")
  args+=(--plugin-dir "$plugin" --strict-mcp-config --settings "$(jq -c '{enabledPlugins: ((.enabledPlugins // {}) | map_values(false))}' "$HOME/.claude/settings.json" 2>/dev/null || echo '{}')")
  (cd "$wt" && CLAUDE_PROJECT_DIR="$wt" TW_DIFF_BASE=$(git merge-base "$base" "$branch") exec claude "${args[@]}") </dev/null >"$out" 2>&1 &
  cpid=$!
  wait "$cpid"
  cpid=""
  save_limits "$out"

  if hit_limit "$out"; then
    say "$id · упёрлись в лимит посреди задачи — пауза и повтор"
    wip "$untracked" "$id"; release
    bash "$B" set "$id" Статус "готова" "лимит посреди задачи, повтор"
    resets=$(grep '^{' "$out" | jq -r 'select(.type=="result") | .result' | grep -oE '[0-9]{10}' | tail -1)
    [ -n "$resets" ] || resets=$(($(date +%s) + 840))
    jq -n --argjson r "$resets" '{utilization: 1, resetsAt: $r}' >"$limits"
    wait_limits
    continue
  fi

  res=$(outcome "$plan")
  for k in test scope verify; do echo "$k: $(cat "$wstate/last-$k" 2>/dev/null || echo 'не было')"; done >"$runs/$id.checks"
  rm -f "$runs/$id.verify"
  vcache="$wstate/verify-$(basename "$plan" .md)"
  [ -f "$vcache" ] && cp "$vcache" "$runs/$id.verify"
  title=$(head -1 "docs/backlog/$id.md" | sed -E 's/^# B-[0-9]+ · //')
  case "$res" in
    ok)
      stage_task "$untracked"
      w commit -qm "feat: resolve backlog item $id" >/dev/null 2>&1
      release
      bash "$B" set "$id" Статус "на приёмке" "проверки зелёные, проверяющий подтвердил"
      say "$id · на приёмке · $title"; env_fails=0 ;;
    env:*)
      wip "$untracked" "$id"; release
      stuck "$id" "${res#env:}"
      env_fails=$((env_fails + 1))
      [ "$env_fails" -ge 2 ] && { bash "$B" queue-pop; say "два сбоя окружения подряд — стоп"; exit 1; } ;;
    *)
      wip "$untracked" "$id"; release
      reason=${res#stuck:}
      if [ -n "$escalate" ] && [ "$escalated" != "$id" ] && [ "$escalate" != "$model" ] && [[ "$reason" != нужен\ человек* && "$reason" != план\ брошен* ]]; then
        escalated=$id
        bash "$B" set "$id" Статус "готова" "$model не справился ($reason), повтор на $escalate"
        say "$id · $reason на $model — повтор на $escalate"
        untracked=""
        continue
      fi
      stuck "$id" "$reason"; env_fails=0 ;;
  esac
  bash "$B" queue-pop
  untracked=""
  done_count=$((done_count + 1))
done

say "конец · обработано: $done_count"
}

main "$@"
exit
