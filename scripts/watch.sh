#!/bin/bash
self="$(cd "$(dirname "$0")" && pwd)/watch.sh"
B="$(dirname "$self")/backlog.sh"
root=$(bash "$B" root) || exit 2
state="$root/.claude/tw-state"
runs="$state/run"

alive() { pgrep -if "scripts/watch\.sh .*$root" | grep -vx "$$" | grep -q .; }

if [ "$1" = open ]; then
  alive && { echo "tw: просмотр уже открыт"; exit 0; }
  cmd="bash '$self' '$root'"
  if [ -n "$TMUX" ]; then
    tmux split-window -h -c "$root" "$cmd" && { echo "tw: просмотр открыт справа (tmux)"; exit 0; }
  elif [ "$TERM_PROGRAM" = ghostty ]; then
    osascript - "$cmd" "$root" >/dev/null 2>&1 <<'EOF' && { echo "tw: просмотр открыт справа"; exit 0; }
on run argv
  tell application "Ghostty"
    set cfg to new surface configuration
    set command of cfg to item 1 of argv
    set initial working directory of cfg to item 2 of argv
    set wait after command of cfg to true
    split (focused terminal of selected tab of front window) direction right with configuration cfg
  end tell
end run
EOF
  elif [ "$TERM_PROGRAM" = iTerm.app ]; then
    osascript - "$cmd" >/dev/null 2>&1 <<'EOF' && { echo "tw: просмотр открыт справа"; exit 0; }
on run argv
  tell application "iTerm2" to tell current session of current window
    set s to (split vertically with same profile)
    tell s to write text (item 1 of argv)
  end tell
end run
EOF
  fi
  echo "tw: открой рядом окно терминала и запусти: $cmd"
  exit 0
fi

[ -n "$1" ] && [ -d "$1" ] && cd "$1"
tp=""
trap 'exit 0' INT TERM

filter='
  def t: (.timestamp // "" | sub("\\.[0-9]+Z$"; "Z") | (try (fromdate | strflocaltime("%H:%M:%S")) catch "        "));
  def one: gsub("\\s+"; " ") | if length > 160 then .[:159] + "…" else . end;
  if .type == "system" and .subtype == "init" then "\u001b[2m── модель \(.model) · сессия \(.session_id)\u001b[0m"
  elif .type == "assistant" then
    t as $t | (.message.content[]? |
      if .type == "text" and (.text | test("\\S")) then "\($t) \u001b[1m· \(.text | one)\u001b[0m"
      elif .type == "tool_use" then "\($t) \u001b[2m→ \(.name) \((.input.command // .input.skill // .input.file_path // .input.pattern // .input.description // "") | tostring | one)\u001b[0m"
      else empty end)
  elif .type == "result" then "\u001b[2m── итог: ходов \(.num_turns), $\(.total_cost_usd * 100 | round / 100), \(.duration_ms / 60000 | floor) мин\u001b[0m"
  else ([.. | strings | select(test("tw ▸"))] | unique[] | split("\n")[] | select(test("^(Stop says: )?tw ▸")) | sub("^Stop says: "; "") | "         \u001b[33m\(.)\u001b[0m")
  end'

follow() { tail -n +1 -f "$1" 2>/dev/null | jq -R --unbuffered -r --arg id "$2" "fromjson? // empty | $filter | \"\\(\$id) \\(.)\"" 2>/dev/null; }

echo "tw · просмотр исполнителя · ${root/#$HOME/~} · выход — ctrl+c"
from=$(grep -n ' · старт · ' "$state/run.log" 2>/dev/null | tail -1 | cut -d: -f1)
bash "$B" running || from=$(($(wc -l <"$state/run.log" 2>/dev/null || echo 0) + 1))
( tail -n +"${from:-1}" -f "$state/run.log" 2>/dev/null | perl -CSD -Mutf8 -pe 'BEGIN { $| = 1 } chomp; my $c = / · старт · / ? "\e[2J\e[3J\e[H" : ""; my $end = / · итог · / ? "\e[2m   прогон закончен · окно можно оставить: следующий /tw:run очистит его; закрыть — ctrl+c\e[0m\n" : ""; $_ = "$c\e[36m$_\e[0m\n$end"' ) 2>/dev/null &
lp=$!; disown $lp
stopf() { local p; for p in $tps; do pkill -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; done; tps=""; }
trap 'stopf; pkill -P $lp 2>/dev/null; kill $lp 2>/dev/null; wait 2>/dev/null' EXIT
tps=""; seen=" "
if bash "$B" running; then
  seen=" $(find "$runs" -name 'B-*.jsonl' ! -newer "$state/run.pid" 2>/dev/null | tr '\n' ' ')"
else
  seen=" $(ls "$runs"/B-*.jsonl 2>/dev/null | tr '\n' ' ')"
fi
while :; do
  for f in $(ls -tr "$runs"/B-*.jsonl 2>/dev/null); do
    case "$seen" in *" $f "*) continue ;; esac
    seen="$seen$f "
    id=$(basename "$f" .jsonl); id=${id%%-2*}
    echo
    echo $'\033[1m'"── $(basename "$f" .jsonl)"$'\033[0m'
    follow "$f" "$id" 2>/dev/null &
    p=$!; disown $p; tps="$tps $p"
  done
  sleep 2
done
