#!/bin/bash
K="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$K/tests/fakebin:$PATH"
export TW_RUN_SLEEP=1
work=$(mktemp -d)
trap 'pkill -f "$work" 2>/dev/null; rm -rf "$work"' EXIT
pass=0; fail=0; only=$1

ok() { pass=$((pass + 1)); printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad() { fail=$((fail + 1)); printf '  \033[31m✗\033[0m %s\n' "$1"; [ -n "$2" ] && sed 's/^/      /' <<<"$2" | head -15; }
check() { local name=$1; shift; if "$@" >/dev/null 2>&1; then ok "$name"; else bad "$name" "$(tail -5 "$P/.claude/tw-state/run.log" 2>/dev/null)"; fi; }
is() { [ "$1" = "$2" ] || { echo "ожидалось «$2», получено «$1»" >&2; return 1; }; }
has() { grep -q -- "$2" <<<"$1"; }

fixture() {
  P="$work/$1/proj"
  mkdir -p "$P/src" "$P/.claude" "$P/docs/backlog" "$P/docs/specs" "$P/docs/plans"
  export FAKE_LOG="$work/$1/models"
  : >"$FAKE_LOG"; : >"$FAKE_LOG.notify"
  cd "$P" || exit 1
  git init -q -b main
  echo base >src/app.txt
  echo base >src/other.txt
  printf '.claude/tw-state/\ndocs/backlog/\n' >.gitignore
  printf '{"check": "true"}\n' >.claude/tw.json
  git add -A && git -c user.name=t -c user.email=t@t commit -qm init
}

task() {
  local id=$1
  cat >"docs/backlog/$id.md" <<EOF
# $id · Тестовая задача $id

- **Статус:** входящая
- **Приоритет:** P2 · **Размер:** S · **Категория:** корректность
- **Готово, когда:** работает
- **Спека:** — · **План:** — · **Ветка:** —

## Журнал

- 2026-01-01 · создана
EOF
}

prepare() {
  local id=$1 n
  n=$(tr '[:upper:]' '[:lower:]' <<<"$id")
  task "$id"
  printf '# Спека %s\n\n**Готово, когда:**\n\n- сделано\n- проверено\n\n**Не трогаем:** `src/other.txt`\n' "$id" >"docs/specs/$n.md"
  printf '# План %s\n\n**Статус:** в работе\n**Спецификация:** docs/specs/%s.md\n\n## Задачи\n\n- [ ] 1. Сделать\n  Проверка: тест\n- [ ] 2. Проверить\n  Проверка: тест\n\n## Приёмка\n\n- [ ] Глазами [человек]\n\n## Журнал\n\n' "$id" "$n" >"docs/plans/$n.md"
  tw backlog.sh prepare "$id" "docs/specs/$n.md" "docs/plans/$n.md"
}

tw() { CLAUDE_PROJECT_DIR="$P" GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t bash "$K/scripts/$1" "${@:2}"; }
st() { tw backlog.sh get "$1" Статус; }
run() { tw backlog.sh queue-add "$@" && tw run.sh 0 >"$P/.claude/run.out" 2>&1; }
untouched() { is "$(git -C "$P" branch --show-current)" main && [ -z "$(git -C "$P" status --porcelain --untracked-files=no)" ]; }
scenario() { [ -z "$only" ] || [ "$only" = "$1" ] || return 1; echo; echo "$1"; }

if scenario prepare; then
  fixture prepare
  prepare B-001 >/dev/null
  check "статус готова" is "$(st B-001)" готова
  check "ветка со спекой и планом" git cat-file -e tw/B-001:docs/plans/b-001.md
  check "в main спеки нет" bash -c "! git cat-file -e main:docs/specs/b-001.md"
  check "локальные копии убраны" bash -c "[ ! -f docs/plans/b-001.md ]"
  check "папка на main и чистая" untouched
fi

if scenario ok; then
  fixture ok
  prepare B-001 >/dev/null
  run B-001
  check "на приёмке" is "$(st B-001)" "на приёмке"
  check "модель sonnet, без повтора" is "$(cat "$FAKE_LOG")" sonnet
  check "коммит в ветке" has "$(git log --format=%s tw/B-001 -1)" "feat: resolve backlog item B-001"
  check "работа в ветке" has "$(git show tw/B-001:src/app.txt)" "work sonnet"
  check "worktree отпустил ветку" bash -c "! git worktree list --porcelain | grep -q 'refs/heads/tw/B-001'"
  check "папка не тронута" untouched
  check "итог проверок сохранён" grep -q 'test: green' .claude/tw-state/run/B-001.checks
  check "карточка показывает заходы" has "$(tw accept.sh B-001)" "sonnet · ходов 3"
  check "стоимость задачи в run.log" grep -q 'B-001 · на приёмке · \$0.01' .claude/tw-state/run.log
  check "итог прогона в run.log" grep -q 'итог · на приёмке 1 · застряло 0 · \$0.01' .claude/tw-state/run.log
  check "уведомление об итоге" grep -q 'Прогон закончен: на приёмке 1, застряло 0' "$FAKE_LOG.notify"
fi

if scenario escalate; then
  fixture escalate
  prepare B-001 >/dev/null
  FAKE_MODE=sonnet-red run B-001
  check "повтор на opus довёл до приёмки" is "$(st B-001)" "на приёмке"
  check "модели sonnet → opus" is "$(tr '\n' ' ' <"$FAKE_LOG")" "sonnet opus "
  check "журнал про повтор" grep -q 'повтор на opus' docs/backlog/B-001.md
fi

if scenario red; then
  fixture red
  prepare B-001 >/dev/null
  FAKE_MODE=red run B-001
  check "застряла: красные проверки" is "$(st B-001)" "застряла: красные проверки"
  check "повтор был один" is "$(tr '\n' ' ' <"$FAKE_LOG")" "sonnet opus "
  check "незакоммиченное ушло wip-коммитом" has "$(git log --format=%s tw/B-001 -1)" "chore: wip backlog item B-001"
  check "папка не тронута" untouched
  check "уведомление о застрявшей" grep -q 'B-001 застряла: красные проверки' "$FAKE_LOG.notify"
  check "итог считает застрявшие" grep -q 'итог · на приёмке 0 · застряло 1' .claude/tw-state/run.log
fi

if scenario human; then
  fixture human
  prepare B-001 >/dev/null
  FAKE_MODE=human run B-001
  check "застряла: нужен человек" is "$(st B-001)" "застряла: нужен человек: выбрать формат"
  check "без повтора на opus" is "$(cat "$FAKE_LOG")" sonnet
fi

if scenario noverify; then
  fixture noverify
  prepare B-001 >/dev/null
  FAKE_MODE=noverify run B-001
  check "без проверяющего не на приёмке" has "$(st B-001)" "проверяющий не запускался"
fi

if scenario nobranch; then
  fixture nobranch
  task B-002
  tw backlog.sh set B-002 Статус готова >/dev/null
  run B-002
  check "нет ветки — застряла" has "$(st B-002)" "нет ветки с планом"
  check "claude не запускался" is "$(cat "$FAKE_LOG")" ""
fi

if scenario limit; then
  fixture limit
  prepare B-001 >/dev/null
  FAKE_MODE=limit-once run B-001
  check "после паузы по лимиту задача сделана" is "$(st B-001)" "на приёмке"
  check "пауза записана" grep -q 'лимит посреди задачи' .claude/tw-state/run.log
fi

if scenario args; then
  fixture args
  tw run.sh stop. >/dev/null 2>&1
  check "неверный аргумент — отказ" is "$?" 2
  out=$(tw run.sh 0 2>&1)
  check "пустая очередь — не стартует" has "$out" "очередь пуста"
  check "пустой старт не пишет run.log" bash -c "! grep -q 'старт' .claude/tw-state/run.log 2>/dev/null"
  check "stop без исполнителя" has "$(tw run.sh stop)" "не идёт"
fi

if scenario stop; then
  fixture stop
  prepare B-001 >/dev/null
  tw backlog.sh queue-add B-001
  FAKE_MODE=hang tw run.sh 0 >"$P/.claude/run.out" 2>&1 &
  for _ in $(seq 50); do grep -q 'B-001 · старт' .claude/tw-state/run.log 2>/dev/null && grep -q . "$FAKE_LOG" && break; sleep 0.2; done
  sleep 0.5
  tw run.sh 0 >/dev/null 2>&1
  check "второй исполнитель не стартует" is "$?" 1
  check "running видит исполнителя" tw backlog.sh running
  tw run.sh stop >/dev/null
  check "после stop задача снова готова" is "$(st B-001)" готова
  check "и первая в очереди" is "$(tw backlog.sh queue-next)" B-001
  check "wip-коммит в ветке" has "$(git log --format=%s tw/B-001 -1)" "chore: wip backlog item B-001"
  check "дерево claude погашено" bash -c "! pgrep -f '$K/tests/fakebin/claude'"
  check "итог при остановке" grep -q 'Прогон закончен.*остановлен' "$FAKE_LOG.notify"
  check "исполнитель не идёт" bash -c "! CLAUDE_PROJECT_DIR='$P' bash '$K/scripts/backlog.sh' running"
fi

if scenario accept; then
  fixture accept
  prepare B-001 >/dev/null
  prepare B-002 >/dev/null
  run B-001 B-002
  echo dirty >>src/other.txt
  tw accept.sh merge B-001 >/dev/null
  check "грязная папка — отказ слияния" is "$?" 3
  git checkout -q -- src/other.txt
  tw accept.sh merge B-001 >/dev/null
  check "слита" is "$(st B-001)" принята
  check "merge-коммит в main" has "$(git log --format=%s -1)" "feat: merge backlog item B-001"
  check "ветка удалена" bash -c "! git rev-parse -q --verify refs/heads/tw/B-001"
  check "план закрыт приёмкой" grep -q 'принято пользователем' docs/plans/b-001.md
  tw accept.sh merge B-002 >/dev/null
  check "конфликт — отказ, main не тронут" is "$?" 4
  check "после конфликта main чистый" untouched
  tw accept.sh rebase B-002 >/dev/null
  check "rebase с конфликтом — отказ" is "$?" 4
  git worktree list >"$work/wt.txt"
  check "rebase не оставил worktree" is "$(grep -vcE 'tw-(run|accept)' "$work/wt.txt")" 1
  tw accept.sh rework B-002 "добавить тест" >/dev/null
  check "доработка — статус готова" is "$(st B-002)" готова
  check "доработка в плане ветки" has "$(git show tw/B-002:docs/plans/b-002.md)" "3. Доработка: добавить тест"
  tw accept.sh reject B-002 "не нужно" >/dev/null
  check "отклонена" is "$(st B-002)" "отклонена: не нужно"
fi

if scenario merge-check; then
  fixture merge-check
  printf '{"check": "! grep -q BREAK src/other.txt"}\n' >.claude/tw.json
  prepare B-001 >/dev/null
  FAKE_MODE=breaks run B-001
  head=$(git rev-parse HEAD)
  out=$(tw accept.sh merge B-001)
  check "красное слияние — отказ" is "$?" 5
  check "причина в выводе" has "$out" "проверки красные"
  check "main не тронут" is "$(git rev-parse HEAD)" "$head"
  check "статус остался на приёмке" is "$(st B-001)" "на приёмке"
  check "ветка осталась" git rev-parse -q --verify refs/heads/tw/B-001
  prepare B-002 >/dev/null
  run B-002
  out=$(tw accept.sh merge B-002)
  check "зелёное слияние проходит" is "$(st B-002)" принята
  check "проверка слияния была" has "$out" "проверки зелёные"
  check "проверочный worktree отпущен на main" is "$(git -C .claude/worktrees/tw-accept rev-parse HEAD)" "$(git rev-parse HEAD~1)"
fi

if scenario rebase; then
  fixture rebase
  prepare B-001 >/dev/null
  run B-001
  echo more >>src/other.txt
  git -c user.name=t -c user.email=t@t commit -qam "chore: other"
  tw accept.sh rebase B-001 >/dev/null
  check "rebase без конфликта" is "$?" 0
  check "ветка на свежем main" git merge-base --is-ancestor main tw/B-001
fi

if scenario stop-hook; then
  fixture stop-hook
  mkdir -p .claude/tw-state && touch .claude/tw-state/checked
  sleep 1
  echo note >docs/notes.md
  out=$(echo '{"session_id":"t"}' | CLAUDE_PROJECT_DIR="$P" bash "$K/hooks/stop.sh")
  check "правка .md не запускает проверки" is "$out" ""
  echo code >>src/app.txt
  out=$(echo '{"session_id":"t"}' | CLAUDE_PROJECT_DIR="$P" bash "$K/hooks/stop.sh")
  check "правка кода запускает проверки" has "$out" "tw ▸ тесты"
fi

echo
[ "$fail" -eq 0 ] && printf '\033[32mвсе %d проверок прошли\033[0m\n' "$pass" || printf '\033[31mупало %d из %d\033[0m\n' "$fail" $((pass + fail))
[ "$fail" -eq 0 ]
