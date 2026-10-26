#!/bin/bash
main() {
B="$(cd "$(dirname "$0")" && pwd)/backlog.sh"
plugin="$(cd "$(dirname "$0")/.." && pwd)"
root=$(bash "$B" root) || exit 2
cd "$root" || exit 2

state="$root/.claude/tw-state"
runs="$state/run"
log="$state/run.log"
limits="$state/limits"
mkdir -p "$runs"

local max=${1:-0}
base=$(jq -r '.runBase // "main"' .claude/tw.json)
threshold=$(jq -r '.runLimit // 95' .claude/tw.json)
model=$(jq -r '.runModel // empty' .claude/tw.json)
pm=npm; [ -f pnpm-lock.yaml ] && pm=pnpm; [ -f yarn.lock ] && pm=yarn
allow=()
while IFS= read -r a; do allow+=("$a"); done < <(jq -r '.runAllow // empty | .[]' .claude/tw.json)
[ ${#allow[@]} -gt 0 ] || allow=("Bash($pm:*)" "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)")

stage_task() {
  git add -u -- . ':!docs/backlog'
  comm -13 <(sort "$1") <(git ls-files --others --exclude-standard | grep -v '^docs/backlog/' | sort) | while IFS= read -r f; do git add -- "$f"; done
}

say() { echo "$(date '+%F %T') · $*" | tee -a "$log"; }

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
  sleep "${TW_RUN_SLEEP:-$((resets + 60 - now))}"
  rm -f "$limits"
}

hit_limit() {
  grep '^{' "$1" | jq -e 'select(.type=="result" and .is_error == true) | .result | test("limit"; "i")' >/dev/null 2>&1
}

outcome() {
  local plan=$1 test verify plan_st human
  test=$(cut -d' ' -f1 "$state/last-test" 2>/dev/null)
  verify=$(cut -d' ' -f1 "$state/last-verify" 2>/dev/null)
  plan_st=$(grep -m1 -oE '^\*\*Статус:\*\* .*' "$plan" 2>/dev/null | sed 's/^\*\*Статус:\*\* //')
  case "$test" in env) echo "env:сбой окружения"; return ;; red) echo "stuck:красные проверки"; return ;; esac
  case "$verify" in fail) echo "stuck:проверяющий не подтвердил"; return ;; error) echo "stuck:проверяющий не отработал"; return ;; esac
  human=$(grep -m1 -oE 'нужен человек: [^·]*' "$plan" 2>/dev/null | sed 's/ *$//')
  case "$plan_st" in готов*) echo "ok" ;; *) echo "stuck:${human:-план не закрыт (${plan_st:-нет плана})}" ;; esac
}

prompt_for() {
  cat <<EOF
Задача $1 из бэклога: docs/backlog/$1.md. План: $2. Спецификация — по ссылке в плане.
Исполни план по разделу «Исполнение» skill tw:plan, с первой незакрытой задачи. Человека рядом нет: вопросов не задавай. Если без решения человека дальше нельзя — запиши в журнал плана «нужен человек: <что решить>» и закончи.
Не коммить, не меняй ветку и не трогай docs/backlog/ — это делает исполнитель.
EOF
}

done_count=0
env_fails=0
say "старт · очередь: $(bash "$B" queue | tr '\n' ' ')"

while id=$(bash "$B" queue-next) && [ -n "$id" ]; do
  [ "$max" -gt 0 ] && [ "$done_count" -ge "$max" ] && { say "достигнут предел $max задач"; break; }
  wait_limits

  if [ -n "$(git status --porcelain --untracked-files=no -- . ':!docs/backlog')" ]; then
    say "рабочее дерево не чистое — стоп"; exit 1
  fi

  plan=$(bash "$B" get "$id" План)
  if [ -z "$plan" ] || [ "$plan" = "—" ] || [ ! -f "$plan" ]; then
    bash "$B" set "$id" Статус "застряла: нет плана" "исполнитель"
    say "$id · нет плана — пропуск"; bash "$B" queue-pop; continue
  fi

  branch="tw/$id"
  git checkout -q "$base" || { say "не удалось перейти на $base — стоп"; exit 1; }
  if ! git cat-file -e "$base:$plan" 2>/dev/null; then
    bash "$B" set "$id" Статус "застряла: план не закоммичен в $base" "исполнитель"
    say "$id · план не закоммичен в $base — пропуск"; bash "$B" queue-pop; continue
  fi
  if git rev-parse -q --verify "$branch" >/dev/null; then git checkout -q "$branch"; else git checkout -q -b "$branch"; fi
  bash "$B" set "$id" Статус "в работе" "исполнитель, ветка $branch"
  bash "$B" set "$id" Ветка "$branch"
  rm -f "$state/last-test" "$state/last-verify" "$state/checked"
  untracked="$runs/$id.untracked"
  git ls-files --others --exclude-standard | sort >"$untracked"
  say "$id · старт в $branch"

  out="$runs/$id-$(date +%Y%m%d-%H%M%S).jsonl"
  args=(-p "$(prompt_for "$id" "$plan")" --permission-mode acceptEdits --output-format stream-json --verbose --allowedTools "${allow[@]}")
  [ -n "$model" ] && args+=(--model "$model")
  args+=(--plugin-dir "$plugin")
  claude "${args[@]}" </dev/null >"$out" 2>&1
  save_limits "$out"

  if hit_limit "$out"; then
    say "$id · упёрлись в лимит посреди задачи — пауза и повтор"
    stage_task "$untracked"; git commit -qm "chore: wip backlog item $id" >/dev/null 2>&1
    git checkout -q "$base"
    bash "$B" set "$id" Статус "готова" "лимит посреди задачи, повтор"
    resets=$(grep '^{' "$out" | jq -r 'select(.type=="result") | .result' | grep -oE '[0-9]{10}' | tail -1)
    [ -n "$resets" ] || resets=$(($(date +%s) + 840))
    jq -n --argjson r "$resets" '{utilization: 1, resetsAt: $r}' >"$limits"
    wait_limits
    continue
  fi

  res=$(outcome "$plan")
  stage_task "$untracked"
  title=$(head -1 "docs/backlog/$id.md" | sed -E 's/^# B-[0-9]+ · //')
  case "$res" in
    ok)
      git commit -qm "feat: resolve backlog item $id" >/dev/null 2>&1
      git checkout -q "$base"
      bash "$B" set "$id" Статус "на приёмке" "проверки зелёные, проверяющий подтвердил"
      say "$id · на приёмке · $title"; env_fails=0 ;;
    env:*)
      git commit -qm "chore: wip backlog item $id" >/dev/null 2>&1
      git checkout -q "$base"
      bash "$B" set "$id" Статус "застряла: ${res#env:}" "исполнитель"
      env_fails=$((env_fails + 1))
      say "$id · застряла: ${res#env:}"
      [ "$env_fails" -ge 2 ] && { bash "$B" queue-pop; say "два сбоя окружения подряд — стоп"; exit 1; } ;;
    *)
      git commit -qm "chore: wip backlog item $id" >/dev/null 2>&1
      git checkout -q "$base"
      bash "$B" set "$id" Статус "застряла: ${res#stuck:}" "исполнитель"
      say "$id · застряла: ${res#stuck:}"; env_fails=0 ;;
  esac
  bash "$B" queue-pop
  done_count=$((done_count + 1))
done

say "конец · обработано: $done_count"
}

main "$@"
exit
