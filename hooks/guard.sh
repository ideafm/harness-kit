#!/bin/bash
input=$(cat)
source "$(dirname "$0")/lib.sh"

deny() {
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

secret_re='(^|/)(\.env(\.[^/]*)?|[^/]*\.(pem|key|p12|pfx)|id_(rsa|ed25519|ecdsa)[^/]*|credentials[^/]*|secrets?\.[a-z]+)$'

tool=$(jq -r '.tool_name' <<<"$input")
file=$(jq -r '.tool_input.file_path // empty' <<<"$input")

if [ -n "$file" ] && [[ "$file" =~ $secret_re ]] && [[ "$file" != *.example ]]; then
  deny "Файл $(basename "$file") похож на секреты, доступ запрещён правилами проекта. Если нужно что-то проверить в нём — дай пользователю команду, пусть выполнит сам."
fi

if [ "$tool" = "Bash" ]; then
  cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
  if grep -qE '(^|[[:space:]/"'"'"'])(\.env(\.[a-z]+)?|id_(rsa|ed25519)|[^[:space:]]*\.pem)([[:space:]"'"'"';|]|$)' <<<"$cmd" && ! grep -q '\.env\.example' <<<"$cmd"; then
    deny "Команда обращается к файлу с секретами, запрещено правилами проекта. Если нужно что-то проверить — дай пользователю команду, пусть выполнит сам."
  fi
  code_ext='\.(ts|tsx|js|jsx|mjs|cjs|vue)([[:space:]"'"'"';|&)]|$)'
  if grep -qE "(>>?|tee([[:space:]]+-a)?)[[:space:]]*[^[:space:];|&>]+$code_ext" <<<"$cmd" \
    || grep -qE "(sed|perl)[[:space:]]+-[a-zA-Z]*i.*$code_ext" <<<"$cmd"; then
    deny "Код в этом проекте меняется только через Edit/Write — на них висят форматирование и проверки. Повтори правку через Edit или Write."
  fi
  exit 0
fi

case "$tool" in
  Write) new=$(jq -r '.tool_input.content // empty' <<<"$input"); old="" ;;
  Edit) new=$(jq -r '.tool_input.new_string // empty' <<<"$input"); old=$(jq -r '.tool_input.old_string // empty' <<<"$input") ;;
  *) exit 0 ;;
esac

added=$(grep -Fvx -f <(printf '%s\n' "$old") <<<"$new")
[ -z "$old" ] && added="$new"

transcript=$(jq -r '.transcript_path // empty' <<<"$input")
last_prompt=""
[ -f "$transcript" ] && last_prompt=$(jq -r 'select(.type=="user" and (.message.content|type)=="string") | .message.content' "$transcript" | tail -1)

base=$(basename "$file")
case "$base" in
  tsconfig*.json|jsconfig*.json|eslint.config.*|.eslintrc*|.oxlintrc*|oxlint.json|biome.json|biome.jsonc|.prettierrc*|prettier.config.*|vitest.config.*|jest.config.*|.size-limit*|knip.json|knip.config.*|.dependency-cruiser.*)
    [ "$tool" = "Write" ] && [ ! -f "$file" ] && exit 0
    grep -qF "$base" <<<"$last_prompt" && exit 0
    while IFS= read -r p; do grep -qF "$base" "$p" && exit 0; done < <(tw_current_plans)
    deny "$base — конфиг проверок. Менять его можно, только если пользователь прямо попросил или файл есть в текущем плане. Не ослабляй проверки, чтобы пройти Stop: почини код. Если правка правда нужна — впиши её в план с причиной или спроси пользователя."
    ;;
esac

case "$file" in *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.vue) ;; *) exit 0 ;; esac

suppress=$(grep -nE '(eslint-disable|oxlint-disable|biome-ignore|@ts-ignore|@ts-expect-error|@ts-nocheck|istanbul ignore|c8 ignore|v8 ignore)' <<<"$added" | head -3)
if [ -n "$suppress" ] && ! grep -qiE 'disable|ignore|подав|отключ|игнор' <<<"$last_prompt"; then
  deny "Подавлять проверки (eslint-disable, @ts-ignore, @ts-expect-error и т. п.) агенту нельзя: это решение человека. Почини причину. Если без исключения никак — спроси пользователя, назови правило, строку и причину. Найдено:
$suppress"
fi

[ "$(tw_get .noComments)" = "false" ] && exit 0
grep -qiE 'коммент|comment|jsdoc|tsdoc' <<<"$last_prompt" && exit 0

found=$(grep -nE '^[[:space:]]*(//|/\*|\*[[:space:]/]|\*$)|[;{})][[:space:]]+//' <<<"$added" \
  | grep -vE '(@ts-|eslint-|prettier-ignore|istanbul|c8 |v8 ignore|///[[:space:]]*<reference|#!)' \
  | head -3)

[ -z "$found" ] && exit 0

deny "В проекте код пишется без комментариев. Убери их и повтори правку. Найдено:
$found"
