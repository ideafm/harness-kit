#!/bin/bash
dir="${CLAUDE_PROJECT_DIR:-$PWD}"
root=""
while [ "$dir" != "/" ]; do
  [ -f "$dir/.claude/tw.json" ] && { root="$dir"; break; }
  dir=$(dirname "$dir")
done
[ -n "$root" ] || { echo "tw не подключён к $PWD — запусти /tw:init"; exit 0; }

state="$root/.claude/tw-state"
wrap() { perl -CSD -Mutf8 -pe 's/^(.{110}).+/$1…/'; }

plan=""
for p in "$root"/docs/plans/*.md; do
  [ -f "$p" ] || continue
  st=$(grep -m1 -oE '^\*\*Статус:\*\* .*' "$p" | sed 's/^\*\*Статус:\*\* //')
  case "$st" in брошен*) continue ;; esac
  total=$(grep -cE '^- \[[ x]\] [0-9]+\.' "$p")
  done=$(grep -cE '^- \[x\] [0-9]+\.' "$p")
  [ "$total" -gt 0 ] && [ "$done" -eq "$total" ] && plan="$p" && plan_st="$st"
done

if [ -z "$plan" ]; then
  echo "tw: нет плана со всеми закрытыми задачами — принимать пока нечего."
  echo "Что открыто, покажет /tw:status."
  exit 0
fi

name=$(basename "$plan" .md)
spec=$(grep -m1 -oE '^\*\*Спецификация:\*\* .*' "$plan" | sed 's/^\*\*Спецификация:\*\* //; s/`//g')
cache="$state/verify-$name"

echo "[tw · 5/5 приёмка] Карточка одобрения · $(basename "$plan")"
echo
echo "План: ${plan#"$root"/} · статус: $plan_st"
[ -f "$root/$spec" ] && echo "Спецификация: $spec"
echo

echo "Сделано"
grep -E '^- \[x\] [0-9]+\.' "$plan" | sed 's/^- \[x\] /  /' | wrap
echo

echo "Проверено машиной"
echo "  тесты: $(cat "$state/last-test" 2>/dev/null || echo 'прогона не было')"
echo "  scope: $(cat "$state/last-scope" 2>/dev/null || echo 'проверки не было')"
echo "  независимая проверка: $(cat "$state/last-verify" 2>/dev/null || echo 'проверки не было')"
if [ -f "$cache" ]; then
  jq -r '.items[] | select(.verdict=="да") | "  ✓ \(.item) — \(.evidence)"' "$cache" 2>/dev/null | wrap
  jq -r '.items[] | select(.verdict=="нет") | "  ✗ \(.item) — \(.evidence)"' "$cache" 2>/dev/null | wrap
fi
echo

echo "На тебе — машина проверить не может"
{
  [ -f "$cache" ] && jq -r '.items[] | select(.verdict=="человек") | "  - \(.item) — \(.evidence)"' "$cache" 2>/dev/null
  sed -n '/^## Приёмка/,/^## /p' "$plan" | grep -E '^- \[[ x]\].*\[человек\]' | sed 's/^- \[[ x]\] /  - /'
} | wrap | grep . || echo "  - ничего: все пункты спецификации проверяются машиной"
echo

if [ -f "$root/$spec" ]; then
  echo "Допущения спецификации — решено без тебя"
  grep -F '[допущение]' "$root/$spec" | sed 's/^[-* ]*//; s/^/  - /' | wrap | grep . ||
    echo "  - нет"
  echo
fi

echo "Изменения"
if git -C "$root" rev-parse --verify -q HEAD >/dev/null 2>&1; then
  git -C "$root" diff HEAD --stat -- . ':!docs' | sed 's/^/  /' | grep . || echo "  отслеживаемые файлы не менялись"
  news=$(git -C "$root" ls-files --others --exclude-standard | grep -vE '^(docs/|\.claude/)|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$')
  while IFS= read -r f; do
    [ -n "$f" ] && echo "  $f | $(wc -l <"$root/$f" | tr -d ' ') новых"
  done <<<"$news"
else
  echo "  коммитов ещё нет — вся работа в рабочем дереве"
fi
echo
echo "Журнал — последние записи"
sed -n '/^## Журнал/,$p' "$plan" | grep -vE '^## |^$' | sed 's/^- //' | tail -4 | sed 's/^/  /' | wrap
echo
if [ -f "$state/env" ]; then
  td=$(jq -r '.teardown // empty' "$root/.claude/tw.json")
  echo "Окружение поднято tw $(cut -d' ' -f2- "$state/env") и продолжает работать${td:+ — остановить: $td}"
  echo
fi
echo "Решение: «принято» → отмечу приёмку, запишу в журнал и спрошу про коммит. «доработать» → скажи, что не так."
