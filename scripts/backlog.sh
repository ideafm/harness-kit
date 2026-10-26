#!/bin/bash
dir="${CLAUDE_PROJECT_DIR:-$PWD}"
root=""
while [ "$dir" != "/" ]; do
  [ -f "$dir/.claude/tw.json" ] && { root="$dir"; break; }
  dir=$(dirname "$dir")
done
[ -n "$root" ] || { echo "tw не подключён к $PWD" >&2; exit 2; }

backlog="$root/docs/backlog"
state="$root/.claude/tw-state"
queue="$state/queue"
mkdir -p "$state"

file() {
  local f="$backlog/$1.md"
  [ -f "$f" ] || { echo "нет задачи $1" >&2; exit 2; }
  echo "$f"
}

field() {
  perl -CSD -Mutf8 -ne 'if (/\*\*\Q'"$2"'\E:\*\* ([^·\n]*?)\s*(·|$)/) { print "$1\n"; exit }' "$1"
}

journal() {
  local f=$1 line="- $(date +%F) · $2"
  grep -q '^## Журнал' "$f" || printf '\n## Журнал\n' >>"$f"
  printf '%s\n' "$line" >>"$f"
}

cmd=$1; shift
case "$cmd" in
  list)
    for f in "$backlog"/B-*.md; do
      [ -f "$f" ] || continue
      id=$(basename "$f" .md)
      title=$(head -1 "$f" | sed -E 's/^# B-[0-9]+ · //')
      printf '%s\t%s\t%s\t%s\n' "$id" "$(field "$f" Приоритет)" "$(field "$f" Статус)" "$title"
    done | sort -t$'\t' -k2,2 -k1,1
    ;;
  get)
    f=$(file "$1") || exit 2
    field "$f" "$2"
    ;;
  set)
    f=$(file "$1") || exit 2
    name=$2; value=$3; note=$4
    old=$(field "$f" "$name")
    NAME="$name" VALUE="$value" perl -CSD -Mutf8 -i -pe 'BEGIN { $n = $ENV{NAME}; $v = $ENV{VALUE}; utf8::decode($n); utf8::decode($v) } s/(\*\*\Q$n\E:\*\* )[^·\n]*?(\s*·|\s*$)/$1$v$2/' "$f"
    if [ "$name" = "Статус" ]; then
      journal "$f" "$old → $value${note:+ · $note}"
    elif [ -n "$note" ]; then
      journal "$f" "$note"
    fi
    ;;
  log)
    f=$(file "$1") || exit 2
    journal "$f" "$2"
    ;;
  queue-add)
    for id in "$@"; do file "$id" >/dev/null || exit 2; grep -qx "$id" "$queue" 2>/dev/null || echo "$id" >>"$queue"; done
    ;;
  queue-next)
    head -1 "$queue" 2>/dev/null
    ;;
  queue-pop)
    [ -f "$queue" ] && sed -i '' -e '1d' "$queue"
    ;;
  queue)
    cat "$queue" 2>/dev/null
    ;;
  clean)
    [ -z "$(git -C "$root" status --porcelain --untracked-files=no)" ]
    ;;
  root)
    echo "$root"
    ;;
  *)
    echo "backlog.sh list | get B-NNN Поле | set B-NNN Поле значение [заметка] | log B-NNN текст | queue-add B-NNN… | queue-next | queue-pop | queue | clean | root" >&2
    exit 2
    ;;
esac
