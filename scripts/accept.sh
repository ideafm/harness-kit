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
. "$(dirname "$B")/sandbox.sh"
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

merge_check() {
  [ "$(jq -r '.acceptCheck' "$root/.claude/tw.json")" = false ] && return 0
  local awt="$root/.claude/worktrees/tw-accept" cmd setup log="$state/accept-check.log" out
  cmd=$(CLAUDE_PROJECT_DIR="$root" bash -c 'source "$1"; tw_check_cmd' _ "$(dirname "$B")/../hooks/lib.sh")
  [ -n "$cmd" ] || return 0
  setup=$(jq -r '.setup // empty' "$root/.claude/tw.json")
  if [ ! -e "$awt/.git" ]; then
    git worktree prune
    git check-ignore -q "$awt" || echo "/${awt#"$root"/}/" >>"$(git rev-parse --path-format=absolute --git-common-dir)/info/exclude"
    git worktree add -q --detach "$awt" "$base" || return 1
  fi
  git -C "$awt" checkout -q --detach "$base" && git -C "$awt" reset -q --hard && git -C "$awt" clean -qfd || return 1
  if ! git -C "$awt" merge -q --no-ff --no-edit "$branch" >"$log" 2>&1; then
    git -C "$awt" merge --abort 2>/dev/null
    echo "tw: пробное слияние $branch не прошло, $base не изменён. Лог: ${log#"$root"/}"; return 1
  fi
  bash "$B" wt-sync "$awt"
  export TW_SANDBOX="" TW_SRT=""
  if sandbox_on; then
    TW_SRT=$(sandbox_srt) || { echo "tw: нет srt — песочницы для проверки слияния. Поставь: npm i -g @anthropic-ai/sandbox-runtime (или acceptCheck: false / runSandbox: false в .claude/tw.json)"; git -C "$awt" checkout -q --detach "$base"; return 1; }
    TW_SANDBOX="$state/sandbox/accept.json"
    sandbox_profile "$awt" "$TW_SANDBOX"
  fi
  echo "tw: проверяю результат слияния${TW_SANDBOX:+ в песочнице}: $cmd"
  if [[ "$id" == B-* ]]; then
    dchanged=$(bash "$B" deps-changed "$root" "$(bash "$B" deps-ref "$id" "$base")" "$branch" | tr '\n' ' ' | sed 's/ $//')
    if [ -n "$dchanged" ]; then
      echo "tw: ветка меняет зависимости сверх утверждённых ($dchanged) — $base не изменён. Посмотри: git diff $base...$branch -- $dchanged"
      git -C "$awt" checkout -q --detach "$base"; return 1
    fi
  fi
  out=$(bash "$B" wt-deps "$awt") || { echo "tw: не встали зависимости для проверки слияния, $base не изменён. Лог: ${awt#"$root"/}/.claude/tw-state/install.log"; git -C "$awt" checkout -q --detach "$base"; return 1; }
  [ -n "$out" ] && echo "tw: $out"
  export COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-$(basename "$root" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}
  if [ -n "$setup" ] && ! (cd "$root" && eval "$setup") >"$log" 2>&1; then
    echo "tw: setup для проверки слияния упал ($setup), $base не изменён. Лог: ${log#"$root"/}"; git -C "$awt" checkout -q --detach "$base"; return 1
  fi
  if ! (export CLAUDE_PROJECT_DIR="$awt" NO_COLOR=1 && sandboxed "$awt" "$cmd") >"$log" 2>&1; then
    echo "tw: на результате слияния $branch с $base проверки красные — $base не изменён. Каждая ветка зелёная сама по себе, вместе — нет."
    tail -15 "$log" | sed 's/^/  /'
    echo "Лог: ${log#"$root"/}. Варианты: доработать задачу (accept.sh rework $id \"…\") или поправить $base."
    git -C "$awt" checkout -q --detach "$base"; return 1
  fi
  git -C "$awt" checkout -q --detach "$base"
  echo "tw: на результате слияния проверки зелёные"
}
[ "$1" = ui ] && set -- look "$2"
if [ "$1" = look ] && [[ "$2" =~ ^[BE]-?[0-9]+$ ]]; then
  branch="tw/$2"; lwt="$root/.claude/worktrees/tw-look"
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || { echo "tw: нет ветки $branch"; exit 2; }
  if [ ! -e "$lwt/.git" ]; then
    git worktree prune
    git check-ignore -q "$lwt" || echo "/${lwt#"$root"/}/" >>"$(git rev-parse --path-format=absolute --git-common-dir)/info/exclude"
    git worktree add -q --detach "$lwt" "$branch" || exit 1
  fi
  git -C "$lwt" checkout -q --detach "$branch" && git -C "$lwt" reset -q --hard && git -C "$lwt" clean -qfd || exit 1
  bash "$B" wt-sync "$lwt"
  ref=$base; [[ "$2" == B-* ]] && ref=$(bash "$B" deps-ref "$2" "$base")
  out=$(bash "$B" wt-deps "$lwt" "$ref"); rc=$?
  if [ $rc = 3 ]; then
    echo "tw: $out. Посмотри: git diff $base...$branch -- <файлы>; поставить: cd $(H="$HOME" perl -pe 's/^\Q$ENV{H}\E/~/i' <<<"$lwt") && <установка>"
  elif [ $rc != 0 ]; then
    echo "tw: не встали зависимости. Лог: ${lwt#"$root"/}/.claude/tw-state/install.log"; exit 1
  fi
  [ $rc = 0 ] && [ -n "$out" ] && echo "tw: $out"
  echo "tw: код $branch — в отдельной папке, твоя не тронута. Перейти:"
  echo "  cd $(H="$HOME" perl -pe 's/^\Q$ENV{H}\E/~/i' <<<"$lwt")"
  dev=$(jq -r '.dev // empty' "$root/.claude/tw.json")
  pm=npm; [ -f "$root/pnpm-lock.yaml" ] && pm=pnpm; [ -f "$root/yarn.lock" ] && pm=yarn
  [ -z "$dev" ] && jq -e '.scripts.dev' "$root/package.json" >/dev/null 2>&1 && dev="$pm run dev"
  [ -n "$dev" ] && echo "Запуск: $dev"
  echo "Правки там не сохраняются: следующий look перезапишет папку."
  exit 0
fi
if [[ "$2" =~ ^E[0-9]+$ ]] && [[ "$1" =~ ^(merge|rework|reject)$ ]]; then
  action=$1; id=$2; note=$3; branch="tw/$id"
  bash "$B" get "$id" Статус >/dev/null || exit 2
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || { echo "tw: нет ветки эпика $branch"; exit 2; }
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  case "$action" in
    merge)
      [ "$(git symbolic-ref -q --short HEAD)" = "$base" ] || { echo "tw: для слияния папка проекта должна стоять на $base (сейчас: $(git branch --show-current))"; exit 3; }
      bash "$B" clean || { echo "tw: в папке проекта незакоммиченные правки — закоммить или убери их:"; git status --short --untracked-files=no -- . ':!docs/backlog'; exit 3; }
      busy=$(for t in $(bash "$B" epic-tasks "$id"); do s=$(bash "$B" get "$t" Статус); case "$s" in (принята|"в эпике"*|отклонена*) ;; (*) echo "$t ($s)" ;; esac; done)
      [ -z "$busy" ] || { echo "tw: в эпике $id ещё не готовы задачи: $(tr '\n' ' ' <<<"$busy")— сливать рано"; exit 3; }
      if ! git merge-tree --write-tree --name-only "$base" "$branch" >"$tmp/conflict" 2>&1; then
        echo "tw: $branch конфликтует с $base в файлах:"
        sed -n '2,/^$/p' "$tmp/conflict" | grep . | sed 's/^/  /'
        exit 4
      fi
      merge_check || exit 5
      git merge -q --no-ff "$branch" -m "feat: merge epic $id" || { git merge --abort 2>/dev/null; echo "tw: слияние не прошло, $base не изменён"; exit 4; }
      for t in $(bash "$B" epic-tasks "$id"); do
        case "$(bash "$B" get "$t" Статус)" in "в эпике"*) bash "$B" set "$t" Статус принята "эпик $id слит в $base" ;; esac
      done
      bash "$B" set "$id" Статус принят "слит в $base"
      git branch -q -D "$branch" && echo "tw: эпик $id слит в $base, ветка $branch удалена"
      ;;
    rework)
      [ -n "$note" ] || { echo "tw: что доработать? accept.sh rework $id \"текст\""; exit 2; }
      new=$(bash "$B" next-id)
      {
        echo "# $new · Доработка эпика $id: $note"
        echo
        echo "- **Статус:** входящая"
        echo "- **Приоритет:** P1 · **Размер:** S · **Категория:** доработка"
        echo "- **Эпик:** $id"
        echo "- **Область:** —"
        echo "- **Зависит от:** —"
        echo "- **Готово, когда:** $note — сделано и проверено"
        echo "- **Источник:** приёмка эпика $id"
        echo "- **Спека:** — · **План:** — · **Ветка:** —"
        echo
        echo "## Журнал"
        echo
        echo "- $(date +%F) · создана при приёмке эпика $id"
      } >"$root/docs/backlog/$new.md"
      bash "$B" set "$id" Статус открыт "доработка $new: $note"
      echo "tw: $new — доработка эпика $id, статус входящая. Подготовка и очередь — /tw:run."
      ;;
    reject)
      [ -n "$note" ] || { echo "tw: почему отклоняем? accept.sh reject $id \"причина\""; exit 2; }
      bash "$B" set "$id" Статус "отклонён: $note"
      echo "tw: эпик $id отклонён, ветка $branch осталась"
      ;;
  esac
  exit 0
fi
if [ -n "$1" ] && [[ "$1" =~ ^E[0-9]+$ ]]; then
  id=$1; branch="tw/$id"; f="$root/docs/backlog/$id.md"
  [ -f "$f" ] || { echo "tw: нет эпика $id в docs/backlog/"; exit 0; }
  tasks=$(bash "$B" epic-tasks "$id")
  echo "[tw · 5/5 приёмка] Эпик $id · $(head -1 "$f" | sed -E 's/^# E[0-9]+ · //')" | wrap
  echo
  echo "Статус: $(bash "$B" get "$id" Статус) · ветка $branch$(git rev-parse -q --verify "refs/heads/$branch" >/dev/null && echo " · коммитов против $base: $(git rev-list --count "$base..$branch")")"
  for k in Цель "Как посмотреть"; do v=$(bash "$B" get "$id" "$k"); [ -n "$v" ] && echo "$k: $v"; done | wrap
  echo
  echo "Задачи"
  for t in $tasks; do
    v=$(sed -n 's/^verify: [a-z]* [0-9-]* [0-9:]* · //p' "$state/run/$t.checks" 2>/dev/null | sed 's/ · [^·]*$//')
    echo "  $t · $(bash "$B" get "$t" Статус)${v:+ · проверяющий $v} · $(head -1 "$root/docs/backlog/$t.md" | sed -E 's/^# B-[0-9]+ · //')"
  done | wrap
  echo
  echo "На тебе — машина проверить не может"
  for t in $tasks; do
    [ -f "$state/run/$t.verify" ] && jq -r --arg t "$t" '.items[] | select(.verdict=="человек") | "  - \($t): \(.item) — \(.evidence)"' "$state/run/$t.verify" 2>/dev/null
    p=$(bash "$B" get "$t" План)
    [ -n "$p" ] && [ "$p" != "—" ] && git show "$branch:$p" 2>/dev/null | sed -n '/^## Приёмка/,/^## /p' | grep -E '^- \[ \].*\[человек\]' | sed "s/^- \[ \] /  - $t: /"
  done | wrap | grep . || echo "  - ничего: всё проверено машиной"
  echo
  echo "Изменения против $base"
  git diff --stat "$base...$branch" -- . ':!docs' 2>/dev/null | tail -1 | sed 's/^/  /' | grep . || echo "  код не менялся"
  echo
  echo "Решение: принять эпик и слить в $base / посмотреть / доработать (новая задача в этом эпике) / отклонить."
  echo "Сейчас папка проекта: $(git branch --show-current) · $(bash "$B" clean && echo чистая || echo 'есть незакоммиченные правки')"
  exit 0
fi
if [ -n "$1" ] && [ -n "$2" ] && [[ "$1" =~ ^(merge|rework|reject|rebase)$ ]]; then
  action=$1; id=$2; note=$3
  bash "$B" get "$id" Статус >/dev/null || exit 2
  branch="tw/$id"
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || { echo "tw: нет ветки $branch"; exit 2; }
  plan=$(bash "$B" get "$id" План)
  if git worktree list --porcelain | grep -qx "branch refs/heads/$branch"; then
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
      merge_check || exit 5
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
  esac
  exit 0
fi

if [ -z "$1" ]; then
  ms=$(bash "$B" epics | awk -F'\t' '$2 == "на приёмке"')
  if [ -n "$ms" ]; then
    echo "[tw · 5/5 приёмка] Эпики на приёмке"
    echo
    while IFS=$'\t' read -r m st n title; do echo "  $m · задач $n · $title"; done <<<"$ms" | wrap
    echo
  fi
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
    echo "Исполнитель — заходы"
    sid=""; wt=""
    while IFS= read -r r; do
      line=$(grep '^{' "$r" | jq -rs '(map(select(.subtype=="init"))[0] // {}) as $i | (map(select(.type=="result"))[0] // {}) as $e | "\($i.session_id // "")\t\($i.model // "?") · ходов \($e.num_turns // "?") · $\(($e.total_cost_usd // 0) * 100 | round / 100) · \((($e.duration_ms // 0) / 60000) | floor) мин"' 2>/dev/null)
      [ -n "${line%%$'\t'*}" ] && { sid=${line%%$'\t'*}; wt=$(grep '^{' "$r" | jq -r 'select(.subtype=="init") | .cwd // empty' 2>/dev/null | head -1); }
      echo "  $(basename "$r" .jsonl | sed -E 's/^B-[0-9]+-//') · ${line#*$'\t'}"
    done <<<"$runs"
    [ -n "$sid" ] && echo "  разговор последнего захода: ${wt:+cd ${wt/#$HOME/~} && }claude --resume $sid"
    echo
  fi
  echo "Журнал задачи"
  sed -n '/^## Журнал/,$p' "$f" | grep -vE '^## |^$' | sed 's/^- //' | tail -4 | sed 's/^/  /' | wrap
  echo "Журнал плана"
  sed -n '/^## Журнал/,$p' <<<"$ptext" | grep -vE '^## |^$' | sed 's/^- //' | tail -3 | sed 's/^/  /' | wrap
  echo
  echo "Решение: принять и слить в $base / доработать / посмотреть руками / отклонить."
  echo "Попробовать руками на коде ветки: bash $(H="$HOME" perl -pe 's/^\Q$ENV{H}\E/~/i' <<<"$(dirname "$B")")/accept.sh look $id"
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
