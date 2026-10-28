#!/bin/bash
input=$(cat)
source "$(dirname "$0")/lib.sh"

plans=()
while IFS= read -r p; do plans+=("$p"); done < <(tw_current_plans)
[ ${#plans[@]} -gt 0 ] || exit 0

changed=$(tw_changed | grep -vE '^(docs/|\.claude/|\.gitignore$)|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$')
[ -n "$changed" ] || exit 0

refs=""; protected=""
for p in "${plans[@]}"; do
  refs+=$(cat "$p")$'\n'
  spec=$(tw_plan_spec "$p") || continue
  refs+=$(cat "$spec")$'\n'
  protected+=$(awk '/^ *\*\*Не трогаем:\*\*/{on=1} on && /^ *\*\*[^*]+:\*\*/ && !/Не трогаем/{on=0} on' "$spec" | sed 's/^ *\*\*Не трогаем:\*\*//; s/^ *[-*] //' | perl -CSA -Mutf8 -ne 'for (split /[,;]\s*|\s+(?:и|а также)\s+/) { s/^\s+|[\s.]+$//g; print "$1\n" if /^`([^`]+)`(?:$|\s+[—–-]\s|\s*\()/ }')$'\n'
done

forbidden=""; outside=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  base=$(basename "$f"); stem=${base%%.*}
  while IFS= read -r t; do
    [ -n "$t" ] || continue
    t=${t%/}
    if [ "$f" = "$t" ] || [ "$stem" = "$t" ] || [ "$base" = "$t" ] || [[ "$f" == "$t"/* ]] || [[ "$f" == $t ]]; then
      forbidden+="$f"$'\n'; continue 2
    fi
  done <<<"$protected"
  grep -qF -e "$f" -e "$base" <<<"$refs" || grep -qE "\`$stem\`" <<<"$refs" || outside+="$f"$'\n'
done <<<"$changed"

lines=$(git -C "$TW_ROOT" diff "$TW_REF" --numstat -- . ':!docs' ':!*.lock' ':!package-lock.json' | awk '{s+=$1+$2} END {print s+0}')
while IFS= read -r f; do
  [ -f "$TW_ROOT/$f" ] && lines=$((lines + $(wc -l <"$TW_ROOT/$f")))
done < <(git -C "$TW_ROOT" ls-files --others --exclude-standard | grep -vE '^(docs/|\.claude/)|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$')

problems=""
[ -n "$forbidden" ] && problems+="Изменены файлы из «Не трогаем» спецификации. Свои правки откати; если правил не ты — не трогай и спроси пользователя:
$(sed '/^$/d; s/^/  - /' <<<"$forbidden")
"
[ -n "$outside" ] && problems+="Изменены файлы, которых нет ни в плане, ни в спецификации. Свои правки либо откати, либо впиши задачу в план и строку в «Журнал» (перепланирование); если правил не ты — спроси пользователя:
$(sed '/^$/d; s/^/  - /' <<<"$outside")
"

sig_file="$TW_STATE/scope-sig"
if [ -z "$problems" ]; then
  rm -f "$sig_file"
  echo "ok $(date '+%Y-%m-%d %H:%M') · diff $lines строк" >"$TW_STATE/last-scope"
  exit 0
fi

sig=$(printf '%s' "$problems" | sed 's/[0-9]//g' | shasum | cut -c1-12)
echo "warn $(date '+%Y-%m-%d %H:%M') · diff $lines строк" >"$TW_STATE/last-scope"
[ "$(cat "$sig_file" 2>/dev/null)" = "$sig escalated" ] && exit 0
if [ "$(cat "$sig_file" 2>/dev/null)" = "$sig" ]; then
  echo "$sig escalated" >"$sig_file"
  jq -n --arg p "$problems" '{systemMessage: ("tw scope: расхождение с планом не устранено — нужен человек.\n" + $p)}'
  exit 0
fi
echo "$sig" >"$sig_file"
jq -n --arg p "$problems" '{decision: "block", reason: ("tw scope: работа вышла за план.\n" + $p)}'
