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
pidfile="$state/run.pid"
mkdir -p "$state"
git() { command git -C "$root" "$@"; }
base() { jq -r '.runBase // "main"' "$root/.claude/tw.json"; }

busy() {
  git worktree list --porcelain | grep -qx "branch refs/heads/$1"
}

commit_to() {
  local branch=$1 msg=$2 idx parent tree c pair blob
  shift 2
  parent=$(git rev-parse -q --verify "refs/heads/$branch") || { echo "нет ветки $branch" >&2; return 2; }
  busy "$branch" && { echo "ветка $branch открыта в worktree — сначала освободи её" >&2; return 2; }
  idx=$(mktemp -u "${TMPDIR:-/tmp}/tw-index.XXXXXX")
  GIT_INDEX_FILE=$idx git read-tree "$parent" || return 2
  for pair in "$@"; do
    blob=$(git hash-object -w -- "${pair#*=}") || { rm -f "$idx"; return 2; }
    GIT_INDEX_FILE=$idx git update-index --add --cacheinfo "100644,$blob,${pair%%=*}"
  done
  tree=$(GIT_INDEX_FILE=$idx git write-tree)
  rm -f "$idx"
  [ "$tree" = "$(git rev-parse "$parent^{tree}")" ] && return 0
  c=$(git commit-tree "$tree" -p "$parent" -m "$msg") && git update-ref "refs/heads/$branch" "$c" "$parent"
}

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
      printf '%s\t%s\t%s\t%s\t%s\n' "$id" "$(field "$f" Приоритет)" "$(field "$f" Размер)" "$(field "$f" Статус)" "$title"
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
  queue-del)
    [ -f "$queue" ] && { grep -vx "$1" "$queue" >"$queue.tmp"; mv "$queue.tmp" "$queue"; }
    ;;
  queue-front)
    { echo "$1"; grep -vx "$1" "$queue" 2>/dev/null; } >"$queue.tmp"; mv "$queue.tmp" "$queue"
    ;;
  deps)
    f=$(file "$1") || exit 2
    field "$f" "Зависит от" | grep -oE 'B-[0-9]+' | while IFS= read -r d; do
      s=$(field "$(file "$d")" Статус) || { echo "$d нет"; continue; }
      case "$s" in принята|"в эпике"*) ;; *) echo "$d $s" ;; esac
    done
    ;;
  area)
    f=$(file "$1") || exit 2
    a=$(field "$f" Область | tr ',' '\n' | sed 's/`//g; s/^ *//; s/ *$//' | grep .)
    if [ -z "$a" ] || [ "$a" = "—" ]; then
      p=$(field "$f" План); b=$(field "$f" Ветка)
      [ -n "$p" ] && [ -n "$b" ] && a=$(git show "$b:$p" 2>/dev/null | grep -oE '`[^` ]+`' | tr -d '`' | grep -E '/|\.[a-z]{1,5}$' | grep -vE '^(docs/|https?:)' | sort -u)
    fi
    [ -n "$a" ] && [ "$a" != "—" ] && echo "$a" || echo '*'
    ;;
  next-id)
    n=$(ls "$backlog"/B-*.md 2>/dev/null | sed -E 's/.*B-0*([0-9]+)\.md$/\1/' | sort -n | tail -1)
    printf 'B-%03d\n' $(( ${n:-0} + 1 ))
    ;;
  epics)
    for f in "$backlog"/E*.md; do
      [ -f "$f" ] || continue
      m=$(basename "$f" .md)
      tasks=$(grep -l -E "\*\*Эпик:\*\* $m([^0-9]|$)" "$backlog"/B-*.md 2>/dev/null)
      total=$(grep -c . <<<"$tasks"); done=0
      for t in $tasks; do case "$(field "$t" Статус)" in принята|"в эпике"*) done=$((done + 1)) ;; esac; done
      printf '%s\t%s\t%s/%s\t%s\n' "$m" "$(field "$f" Статус)" "$done" "$total" "$(head -1 "$f" | sed -E 's/^# E[0-9]+ · //')"
    done
    ;;
  epic-tasks)
    grep -l -E "\*\*Эпик:\*\* $1([^0-9]|$)" "$backlog"/B-*.md 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/\.md$//'
    ;;
  queue-pop)
    [ -f "$queue" ] && sed -i '' -e '1d' "$queue"
    ;;
  queue)
    cat "$queue" 2>/dev/null
    ;;
  clean)
    [ -z "$(git status --porcelain --untracked-files=no -- . ':!docs/backlog')" ]
    ;;
  running)
    pid=$(cat "$pidfile" 2>/dev/null)
    [ -n "$pid" ] && ps -p "$pid" -o command= 2>/dev/null | grep -q 'scripts/run\.sh'
    ;;
  commit-to)
    commit_to "$@"
    ;;
  prepare)
    id=$1; spec=${2#./}; plan=${3#./}
    f=$(file "$id") || exit 2
    for p in "$spec" "$plan"; do [ -f "$root/$p" ] || { echo "нет файла $p" >&2; exit 2; }; done
    branch="tw/$id"
    from=$(base)
    m=$(field "$f" Эпик | grep -oE '^E[0-9]+')
    if [ -n "$m" ]; then
      [ -f "$backlog/$m.md" ] || { echo "нет эпика $m (docs/backlog/$m.md)" >&2; exit 2; }
      git rev-parse -q --verify "refs/heads/tw/$m" >/dev/null || git branch "tw/$m" "$from" || exit 2
      from="tw/$m"
    fi
    if ! git rev-parse -q --verify "refs/heads/$branch" >/dev/null; then
      git branch "$branch" "$from" || exit 2
      old=$(ls "$state/run/$id"-*.jsonl "$state/run/$id".* 2>/dev/null)
      [ -n "$old" ] && mkdir -p "$state/run/old" && mv $old "$state/run/old/"
    fi
    commit_to "$branch" "docs: add spec and plan for $id" "$spec=$root/$spec" "$plan=$root/$plan" || exit 2
    for p in "$spec" "$plan"; do
      if ! git ls-files --error-unmatch -- "$p" >/dev/null 2>&1 && cmp -s "$root/$p" <(git show "$branch:$p"); then
        rm -f "$root/$p"
      fi
    done
    CLAUDE_PROJECT_DIR="$root" bash "$0" set "$id" Спека "$spec"
    CLAUDE_PROJECT_DIR="$root" bash "$0" set "$id" План "$plan"
    CLAUDE_PROJECT_DIR="$root" bash "$0" set "$id" Ветка "$branch"
    CLAUDE_PROJECT_DIR="$root" bash "$0" set "$id" Статус готова "спека и план в $branch"
    echo "$id · спека и план в $branch"
    ;;
  wt-sync)
    wt=$1; cfg="$root/.claude/tw.json"
    mkdir -p "$wt/.claude/tw-state"
    cp "$cfg" "$wt/.claude/tw.json"
    jq -r '.runCopy // empty | .[]' "$cfg" | while IFS= read -r f; do
      [ -n "$f" ] && [ -e "$root/$f" ] && mkdir -p "$(dirname "$wt/$f")" && cp -R "$root/$f" "$wt/$f"
    done
    ;;
  deps-changed)
    wt=$1; ref=$2; to=$3
    set -- ':(glob)**/pnpm-lock.yaml' ':(glob)**/yarn.lock' ':(glob)**/package-lock.json' \
      ':(glob)**/pnpm-workspace.yaml' ':(glob)**/.npmrc' ':(glob)**/.yarnrc.yml' ':(glob)**/.pnpmfile.cjs'
    k='{dependencies, devDependencies, optionalDependencies, peerDependencies, bundledDependencies, pnpm, overrides, resolutions, workspaces} | with_entries(select(.value != null))'
    if [ -n "$to" ]; then
      git -C "$wt" diff --name-only "$ref" "$to" -- "$@"
      for f in $(git -C "$wt" diff --name-only "$ref" "$to" -- ':(glob)**/package.json'); do
        [ "$(git -C "$wt" show "$ref:$f" 2>/dev/null | jq -Sc "$k" 2>/dev/null)" = "$(git -C "$wt" show "$to:$f" 2>/dev/null | jq -Sc "$k" 2>/dev/null)" ] || echo "$f"
      done
    else
      { git -C "$wt" diff --name-only "$ref" -- "$@"; git -C "$wt" ls-files --others --exclude-standard -- "$@"; } | sort -u
      for f in $( { git -C "$wt" diff --name-only "$ref" -- ':(glob)**/package.json'; git -C "$wt" ls-files --others --exclude-standard -- ':(glob)**/package.json'; } | sort -u); do
        [ "$(git -C "$wt" show "$ref:$f" 2>/dev/null | jq -Sc "$k" 2>/dev/null)" = "$(jq -Sc "$k" "$wt/$f" 2>/dev/null)" ] || echo "$f"
      done
    fi
    ;;
  deps-ref)
    id=$1; b=$2; br="tw/$id"
    mb=$(git merge-base "$b" "$br" 2>/dev/null) || { echo "$b"; exit 0; }
    c=$(git log -1 --format=%H --fixed-strings --grep="chore: add dependencies for $id" "$mb..$br")
    echo "${c:-$mb}"
    ;;
  add-deps)
    id=$1; ws=$2; shift 2
    dev=""; [ "$1" = --dev ] && { dev=1; shift; }
    [ -n "$id" ] && [ -n "$ws" ] && [ $# -gt 0 ] || { echo "backlog.sh add-deps B-NNN <путь пакета или .> [--dev] имя@версия…" >&2; exit 2; }
    for d in "$@"; do [[ "$d" =~ ^(@[a-z0-9._-]+/)?[a-z0-9._-]+@[0-9][0-9A-Za-z.+-]*$ ]] || { echo "нужна точная версия: $d (имя@1.2.3)" >&2; exit 2; }; done
    br="tw/$id"
    git rev-parse -q --verify "refs/heads/$br" >/dev/null || { echo "нет ветки $br" >&2; exit 2; }
    tmp=$(mktemp -d)
    git worktree add -q --detach "$tmp/w" "$br" || { rm -rf "$tmp"; exit 2; }
    if [ -f "$tmp/w/pnpm-lock.yaml" ]; then
      cmd=(pnpm); [ "$ws" = . ] || cmd+=(--filter "$ws")
      cmd+=(add --lockfile-only --save-exact); [ "$ws" = . ] && cmd+=(-w)
    elif [ -f "$tmp/w/package-lock.json" ]; then
      cmd=(npm install --package-lock-only --ignore-scripts --save-exact); [ "$ws" = . ] || cmd+=(-w "$ws")
    else
      git worktree remove --force "$tmp/w"; rm -rf "$tmp"
      echo "add-deps умеет pnpm и npm с lock-файлом — поставь сам и закоммить в $br" >&2; exit 2
    fi
    [ -n "$dev" ] && cmd+=(-D)
    if ! (cd "$tmp/w" && "${cmd[@]}" "$@") >"$tmp/log" 2>&1; then
      tail -15 "$tmp/log" >&2; git worktree remove --force "$tmp/w"; rm -rf "$tmp"; exit 1
    fi
    pairs=()
    for f in $(git -C "$tmp/w" status --porcelain --untracked-files=no | awk '{print $2}'); do pairs+=("$f=$tmp/w/$f"); done
    commit_to "$br" "chore: add dependencies for $id" ${pairs[@]+"${pairs[@]}"}; rc=$?
    git worktree remove --force "$tmp/w"; rm -rf "$tmp"
    [ $rc = 0 ] || exit $rc
    f=$(file "$id")
    prev=$(field "$f" Зависимости)
    list="$*${ws:+ → $ws}${dev:+ (dev)}"
    if [ -n "$prev" ] && [ "$prev" != "—" ]; then list="$prev; $list"; fi
    if grep -q '^- \*\*Зависимости:\*\*' "$f"; then
      L="$list" perl -CSD -Mutf8 -i -pe 's/^- \*\*Зависимости:\*\* .*/- **Зависимости:** $ENV{L}/' "$f"
    else
      L="$list" perl -CSD -Mutf8 -i -pe 'print "- **Зависимости:** $ENV{L}\n" if /^- \*\*Спека:\*\*/' "$f"
    fi
    journal "$f" "зависимости утверждены и добавлены в $br: $*"
    echo "добавлено в $br: $*"
    ;;
  wt-deps)
    wt=$1
    if [ -n "$2" ]; then
      changed=$(bash "$0" deps-changed "$wt" "$2" | tr '\n' ' ' | sed 's/ $//')
      [ -z "$changed" ] || { echo "ветка меняет зависимости ($changed) — их установка запускает чужой код, проверь и поставь сам"; exit 3; }
    fi
    install=$(jq -r '.runInstall // empty' "$root/.claude/tw.json")
    pm=npm; [ -f "$wt/pnpm-lock.yaml" ] && pm=pnpm; [ -f "$wt/yarn.lock" ] && pm=yarn
    lock=""; for l in pnpm-lock.yaml yarn.lock package-lock.json; do [ -f "$wt/$l" ] && { lock=$l; break; }; done
    if [ -z "$install" ] && [ -f "$wt/package.json" ]; then
      case "$pm" in
        pnpm) install="pnpm install --frozen-lockfile --prefer-offline" ;;
        yarn) install="yarn install --frozen-lockfile" ;;
        *) [ -n "$lock" ] && install="npm ci" || install="npm install" ;;
      esac
    fi
    [ -n "$install" ] || exit 0
    sum=$( { echo "$install"; [ -n "$lock" ] && cat "$wt/$lock"; } | shasum | cut -c1-16)
    [ "$(cat "$wt/.claude/tw-state/installed" 2>/dev/null)" = "$sum" ] && exit 0
    echo "зависимости: $install"
    mkdir -p "$wt/.claude/tw-state"
    (cd "$wt" && eval "$install") >"$wt/.claude/tw-state/install.log" 2>&1 || exit 1
    echo "$sum" >"$wt/.claude/tw-state/installed"
    ;;
  root)
    echo "$root"
    ;;
  *)
    echo "backlog.sh list | get B-NNN Поле | set B-NNN Поле значение [заметка] | log B-NNN текст | queue-add B-NNN… | queue-next | queue-pop | queue | clean | running | commit-to ветка сообщение путь=файл… | prepare B-NNN спека план | root" >&2
    exit 2
    ;;
esac
