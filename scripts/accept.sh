#!/bin/bash
dir="${CLAUDE_PROJECT_DIR:-$PWD}"
root=""
while [ "$dir" != "/" ]; do
  [ -f "$dir/.claude/tw.json" ] && { root="$dir"; break; }
  dir=$(dirname "$dir")
done
[ -n "$root" ] || { echo "tw не подключён к $PWD — запусти /tw:init"; exit 0; }
export CLAUDE_PROJECT_DIR="$root"

state="$root/.claude/tw-state"
wrap() { perl -CSD -Mutf8 -pe 's/^(.{110}).+/$1…/'; }
B="$(cd "$(dirname "$0")" && pwd)/backlog.sh"
base=$(jq -r '.runBase // "main"' "$root/.claude/tw.json")
git() { command git -C "$root" "$@"; }

plan_edit() {
  ACTION=$1 TEXT=$2 DAY=$(date +%F) perl -CSD -Mutf8 -0pi -e '
    my ($a, $t, $d) = map { my $x = $ENV{$_}; utf8::decode($x); $x } qw(ACTION TEXT DAY);
    if ($a eq "merge") {
      s{(## Приёмка\n.*?)(?=\n## |\z)}{ my $b = $1; $b =~ s/^- \[ \](.*\[человек\])/- [x]$1/mg; $b }se;
      s/^(\*\*Статус:\*\* ).*$/$1готов/m;
      $_ .= "- $d · приёмка · принято пользователем\n";
    } else {
      my @n = /^- \[[ x]\] (\d+)\./mg; my $n = (@n ? $n[-1] : 0) + 1;
      s{(\n## Приёмка)}{\n- [ ] $n. Доработка: $t\n  Проверка: то, что назвал пользователь при приёмке, сделано и проверено\n  Закрывает: приёмка человеком\n$1};
      s/^(\*\*Статус:\*\* ).*$/$1в работе/m;
      $_ .= "- $d · приёмка · доработать: $t\n";
    }
  ' "$3"
}

if [ -n "$1" ] && [ -n "$2" ] && [[ "$1" =~ ^(merge|rework|reject|rebase|ui)$ ]]; then
  action=$1; id=$2; note=$3
  bash "$B" get "$id" Статус >/dev/null || exit 2
  branch="tw/$id"
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || { echo "tw: нет ветки $branch"; exit 2; }
  plan=$(bash "$B" get "$id" План)
  if [ "$action" != ui ] && git worktree list --porcelain | grep -qx "branch refs/heads/$branch"; then
    echo "tw: ветка $branch открыта в worktree — исполнитель над ней работает (дождись конца задачи) или прогон прерван ($(bash "$B" running && echo 'идёт' || echo 'не идёт'))"; exit 2
  fi
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  case "$action" in
    merge)
      [ "$(git symbolic-ref -q --short HEAD)" = "$base" ] || { echo "tw: для слияния папка проекта должна стоять на $base (сейчас: $(git branch --show-current))"; exit 3; }
      bash "$B" clean || { echo "tw: в папке проекта незакоммиченные правки — закоммить или убери их:"; git status --short --untracked-files=no -- . ':!docs/backlog'; exit 3; }
      if ! git merge-tree --write-tree --name-only "$base" "$branch" >"$tmp/conflict" 2>&1; then
        echo "tw: $branch конфликтует с $base в файлах:"
        sed -n '2,/^$/p' "$tmp/conflict" | grep . | sed 's/^/  /'
        echo "Предложи rebase: accept.sh rebase $id"; exit 4
      fi
      git show "$branch:$plan" >"$tmp/plan" && plan_edit merge "" "$tmp/plan" &&
        bash "$B" commit-to "$branch" "docs: accept $id" "$plan=$tmp/plan" || exit 2
      if ! git merge -q --no-ff "$branch" -m "feat: merge backlog item $id"; then
        git merge --abort 2>/dev/null
        echo "tw: слияние не прошло, $base не изменён"; exit 4
      fi
      bash "$B" set "$id" Статус принята "слито в $base"
      git branch -q -d "$branch" && echo "tw: $id слита в $base, ветка $branch удалена"
      ;;
    rework)
      [ -n "$note" ] || { echo "tw: что доработать? accept.sh rework $id \"текст\""; exit 2; }
      git show "$branch:$plan" >"$tmp/plan" && plan_edit rework "$note" "$tmp/plan" &&
        bash "$B" commit-to "$branch" "docs: add rework for $id" "$plan=$tmp/plan" || exit 2
      bash "$B" set "$id" Статус готова "доработать: $note"
      echo "tw: $id — доработка в плане ветки $branch, статус готова. В очередь — /tw:run."
      ;;
    reject)
      [ -n "$note" ] || { echo "tw: почему отклоняем? accept.sh reject $id \"причина\""; exit 2; }
      bash "$B" set "$id" Статус "отклонена: $note"
      echo "tw: $id отклонена, ветка $branch осталась"
      ;;
    rebase)
      git worktree add -q "$tmp/wt" "$branch" || exit 2
      if git -C "$tmp/wt" rebase -q "$base" >"$tmp/rebase.log" 2>&1; then
        echo "tw: $branch перенесена на $base — можно сливать"
      else
        files=$(git -C "$tmp/wt" diff --name-only --diff-filter=U)
        git -C "$tmp/wt" rebase --abort
        echo "tw: rebase $branch на $base упал на конфликте — нужен человек. Файлы:"
        sed 's/^/  /' <<<"$files"
        git worktree remove --force "$tmp/wt"; exit 4
      fi
      git worktree remove --force "$tmp/wt"
      ;;
    ui)
      dev=$(jq -r '.dev // empty' "$root/.claude/tw.json")
      pm=npm; [ -f "$root/pnpm-lock.yaml" ] && pm=pnpm; [ -f "$root/yarn.lock" ] && pm=yarn
      [ -z "$dev" ] && jq -e '.scripts.dev' "$root/package.json" >/dev/null 2>&1 && dev="$pm run dev"
      view="$root/.claude/tw-state/view-$id"
      echo "git -C $root worktree add $view $branch && cd $view && $pm install && ${dev:-<команда запуска>}"
      echo "После просмотра: git -C $root worktree remove --force $view"
      ;;
  esac
  exit 0
fi

if [ -z "$1" ]; then
  pending=$(bash "$B" list | awk -F'\t' '$4 == "на приёмке"')
  if [ -n "$pending" ]; then
    echo "[tw · 5/5 приёмка] Задачи бэклога на приёмке"
    echo
    while IFS=$'\t' read -r id p size st title; do echo "  $id · $p · $size · $title"; done <<<"$pending" | wrap
    echo
    echo "Выбери задачу — покажу карточку по её ветке против $base."
    exit 0
  fi
fi

if [ -n "$1" ]; then
  id=$1
  f="$root/docs/backlog/$id.md"
  [ -f "$f" ] || { echo "tw: нет задачи $id в docs/backlog/"; exit 0; }
  branch=$(bash "$B" get "$id" Ветка)
  plan=$(bash "$B" get "$id" План)
  if [ -z "$branch" ] || [ "$branch" = "—" ] || ! git rev-parse -q --verify "$branch" >/dev/null; then
    echo "tw: у $id нет ветки — исполнитель её ещё не брал."
    exit 0
  fi
  show() { git show "$branch:$1" 2>/dev/null; }
  title=$(head -1 "$f" | sed -E 's/^# B-[0-9]+ · //')
  ptext=$(show "$plan")
  spec=$(grep -m1 -oE '^\*\*Спецификация:\*\* .*' <<<"$ptext" | sed 's/^\*\*Спецификация:\*\* //; s/`//g')
  cache="$state/run/$id.verify"

  echo "[tw · 5/5 приёмка] Карточка $id · $title" | wrap
  echo
  echo "Статус: $(bash "$B" get "$id" Статус) · ветка $branch · коммитов против $base: $(git rev-list --count "$base..$branch")"
  echo "План: $plan · статус: $(grep -m1 -oE '^\*\*Статус:\*\* .*' <<<"$ptext" | sed 's/^\*\*Статус:\*\* //')"
  [ -n "$spec" ] && echo "Спецификация: $spec"
  echo

  echo "Сделано"
  grep -E '^- \[x\] [0-9]+\.' <<<"$ptext" | sed 's/^- \[x\] /  /' | wrap | grep . || echo "  ничего не отмечено"
  open=$(grep -E '^- \[ \] [0-9]+\.' <<<"$ptext" | sed 's/^- \[ \] /  /' | wrap)
  [ -n "$open" ] && { echo "Не сделано"; echo "$open"; }
  echo

  echo "Проверено машиной"
  if [ -f "$state/run/$id.checks" ]; then
    sed 's/^verify:/независимая проверка:/; s/^test:/тесты:/; s/^/  /' "$state/run/$id.checks"
  else
    echo "  исполнитель не сохранил итог проверок"
  fi
  if [ -f "$cache" ]; then
    jq -r '.items[] | select(.verdict=="да") | "  ✓ \(.item) — \(.evidence)"' "$cache" 2>/dev/null | wrap
    jq -r '.items[] | select(.verdict=="нет") | "  ✗ \(.item) — \(.evidence)"' "$cache" 2>/dev/null | wrap
    jq -r '.denied // [] | .[] | "  проверяющему не разрешили: \(split("\n")[0])"' "$cache" 2>/dev/null | wrap
  fi
  echo

  echo "На тебе — машина проверить не может"
  {
    [ -f "$cache" ] && jq -r '.items[] | select(.verdict=="человек") | "  - \(.item) — \(.evidence)"' "$cache" 2>/dev/null
    sed -n '/^## Приёмка/,/^## /p' <<<"$ptext" | grep -E '^- \[[ x]\].*\[человек\]' | sed 's/^- \[[ x]\] /  - /'
  } | wrap | grep . || echo "  - ничего: все пункты спецификации проверяются машиной"
  echo

  if [ -n "$spec" ]; then
    echo "Допущения спецификации — решено без тебя"
    show "$spec" | grep -F '[допущение]' | sed 's/^[-* ]*//; s/^/  - /' | wrap | grep . || echo "  - нет"
    echo
  fi

  echo "Изменения против $base"
  git diff --stat "$base...$branch" -- . ':!docs' | sed 's/^/  /' | grep . || echo "  код не менялся"
  echo
  runs=$(ls "$state"/run/"$id"-*.jsonl 2>/dev/null)
  if [ -n "$runs" ]; then
    wt=$(jq -r '.runWorktree // empty' "$root/.claude/tw.json" 2>/dev/null); wt=${wt:-.claude/worktrees/tw-run}
    [[ "$wt" = /* ]] || wt="$root/$wt"
    echo "Исполнитель — заходы"
    sid=""
    while IFS= read -r r; do
      line=$(grep '^{' "$r" | jq -rs '(map(select(.subtype=="init"))[0] // {}) as $i | (map(select(.type=="result"))[0] // {}) as $e | "\($i.session_id // "")\t\($i.model // "?") · ходов \($e.num_turns // "?") · $\(($e.total_cost_usd // 0) * 100 | round / 100) · \((($e.duration_ms // 0) / 60000) | floor) мин"' 2>/dev/null)
      [ -n "${line%%$'\t'*}" ] && sid=${line%%$'\t'*}
      echo "  $(basename "$r" .jsonl | sed -E 's/^B-[0-9]+-//') · ${line#*$'\t'}"
    done <<<"$runs"
    [ -n "$sid" ] && echo "  разговор последнего захода: cd ${wt/#$HOME/~} && claude --resume $sid"
    echo
  fi
  echo "Журнал задачи"
  sed -n '/^## Журнал/,$p' "$f" | grep -vE '^## |^$' | sed 's/^- //' | tail -4 | sed 's/^/  /' | wrap
  echo "Журнал плана"
  sed -n '/^## Журнал/,$p' <<<"$ptext" | grep -vE '^## |^$' | sed 's/^- //' | tail -3 | sed 's/^/  /' | wrap
  echo
  echo "Решение: принять и слить в $base / доработать / посмотреть UI / отклонить."
  echo "Сейчас папка проекта: $(git branch --show-current) · $(bash "$B" clean && echo чистая || echo 'есть незакоммиченные правки')"
  exit 0
fi

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
