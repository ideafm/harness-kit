#!/bin/bash
input=$(cat)
source "$(dirname "$0")/lib.sh"

[ "$(tw_get .verify)" = "false" ] && exit 0
model=$(tw_get .verifyModel); model=${model:-sonnet}
max=$(tw_get .verifyRounds); max=${max:-2}
tools=(Read Grep Glob "Bash(npm test:*)" "Bash(npm run test:*)" "Bash(npm run typecheck:*)" "Bash(npm run lint:*)" "Bash(npx vitest:*)" "Bash(npx tsc:*)" "Bash(git diff:*)" "Bash(git status:*)")
while IFS= read -r t; do [ -n "$t" ] && tools+=("$t"); done < <(jq -r '.verifyTools[]? // empty' "$TW_CONFIG")

exclude='^(docs/|\.claude/|\.gitignore$)|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$'
schema='{"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"item":{"type":"string"},"verdict":{"type":"string","enum":["да","нет","человек"]},"evidence":{"type":"string"}},"required":["item","verdict","evidence"]}}},"required":["items"]}'

while IFS= read -r plan; do
  total=$(grep -cE '^- \[[ x]\] [0-9]+\.' "$plan")
  done=$(grep -cE '^- \[x\] [0-9]+\.' "$plan")
  [ "$total" -gt 0 ] && [ "$done" -eq "$total" ] || continue
  spec=$(tw_plan_spec "$plan") || continue

  name=$(basename "$plan" .md)
  cache="$TW_STATE/verify-$name"
  changed=$(git -C "$TW_ROOT" status --porcelain -uall --no-renames | cut -c4- | grep -vE "$exclude")
  hash=$( {
    cat "$spec"
    git -C "$TW_ROOT" diff HEAD -- . ':!docs'
    while IFS= read -r f; do [ -f "$TW_ROOT/$f" ] && cat "$TW_ROOT/$f"; done <<<"$changed"
  } | shasum | cut -c1-16)

  items=""
  if [ -f "$cache" ] && [ "$(jq -r .hash "$cache")" = "$hash" ]; then
    [ "$(jq -r .state "$cache")" = "fail" ] || continue
    items=$(jq -c .items "$cache")
  fi

  [ -z "$items" ] && {
  diff=$(git -C "$TW_ROOT" diff HEAD -- . ':!docs' | head -c 60000)
  prompt="Ты — независимый проверяющий. Исполнитель утверждает, что работа по спецификации ниже готова. Его рассуждений ты не видел и соглашаться с ним не обязан. Файлы не меняй.

Для каждого пункта раздела «Готово, когда» найди доказательство в коде и тестах: прочитай изменённые файлы, при необходимости запусти тесты. Вердикт:
- «да» — есть конкретное доказательство (файл, тест, вывод команды);
- «нет» — не сделано, сделано не так или доказательства нет;
- «человек» — проверить можно только глазами человека.
В evidence — коротко, где доказательство или чего не хватает.

Спецификация ($(basename "$spec")):
$(cat "$spec")

Изменённые файлы относительно последнего коммита:
${changed:-нет}

Diff отслеживаемых файлов (новые файлы читай сам):
${diff:-нет}"

  out=$(cd "$TW_ROOT" && TW_NESTED=1 claude -p "$prompt" --model "$model" \
    --strict-mcp-config --no-session-persistence --permission-mode default \
    --allowedTools "${tools[@]}" \
    --disallowedTools Edit Write NotebookEdit \
    --output-format json --json-schema "$schema" </dev/null 2>/dev/null)
  items=$(jq -c '.structured_output.items // empty' <<<"$out" 2>/dev/null)
  }

  if [ -z "$items" ]; then
    echo "error $(date '+%Y-%m-%d %H:%M') · $name" >"$TW_STATE/last-verify"
    jq -n '{systemMessage: "tw verify: проверяющий не отработал — проверь работу сам."}'
    exit 0
  fi

  yes=$(jq '[.[] | select(.verdict=="да")] | length' <<<"$items")
  no=$(jq '[.[] | select(.verdict=="нет")] | length' <<<"$items")
  human=$(jq '[.[] | select(.verdict=="человек")] | length' <<<"$items")
  all=$(jq 'length' <<<"$items")
  summary="да $yes/$all"
  [ "$human" -gt 0 ] && summary="$summary, человеку $human"
  report=$(jq -r '.[] | "  - [\(.verdict)] \(.item) — \(.evidence)"' <<<"$items")

  if [ "$no" -eq 0 ]; then
    jq -n --arg h "$hash" --argjson i "$items" '{hash: $h, state: "ok", round: 0, items: $i}' >"$cache"
    echo "ok $(date '+%Y-%m-%d %H:%M') · $summary · $name" >"$TW_STATE/last-verify"
    jq -n --arg s "$summary" --arg r "$report" '{systemMessage: ("tw verify: проверяющий подтвердил спецификацию (" + $s + ")\n" + $r + "\nПредложи пользователю приёмку: скажи, что готова карточка одобрения, и что её покажет /tw:accept. Сам не коммить и приёмку за пользователя не закрывай.")}'
    exit 0
  fi

  round=$(jq -r '.round // 0' "$cache" 2>/dev/null); round=$(( ${round:-0} + 1 ))
  echo "fail $(date '+%Y-%m-%d %H:%M') · $summary, нет $no · круг $round из $max · $name" >"$TW_STATE/last-verify"
  if [ "$round" -gt "$max" ]; then
    jq -n --arg h "$hash" --argjson i "$items" '{hash: $h, state: "human", round: 0, items: $i}' >"$cache"
    jq -n --arg r "$report" --arg m "$max" '{systemMessage: ("tw verify: проверяющий не подтвердил спецификацию после " + $m + " кругов — нужен человек.\n" + $r)}'
    exit 0
  fi
  jq -n --arg h "$hash" --argjson i "$items" --argjson n "$round" '{hash: $h, state: "fail", round: $n, items: $i}' >"$cache"
  jq -n --arg r "$report" --arg n "$round" --arg m "$max" --arg p "${plan#"$TW_ROOT"/}" '{decision: "block", reason: ("tw verify: независимый проверяющий не подтвердил спецификацию (круг " + $n + " из " + $m + "). Верни в " + $p + " статус «в работе», сними [x] с неподтверждённых пунктов приёмки, доработай и запиши в «Журнал». Вердикт:\n" + $r)}'
  exit 0
done < <(tw_current_plans)
exit 0
