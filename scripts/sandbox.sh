sandbox_cfg() { jq -r "$1" "$root/.claude/tw.json" 2>/dev/null; }

sandbox_on() { [ "$(sandbox_cfg '.runSandbox')" != false ]; }

sandbox_srt() {
  local s=${TW_SRT_BIN:-$(command -v srt)}
  [ -n "$s" ] && [ -x "$s" ] && echo "$s"
}

sandbox_secrets() {
  jq -nc --arg h "$HOME" '[".ssh", ".aws", ".config/gh", ".gnupg", ".docker", ".kube", ".netrc", ".npmrc", ".claude"] | map($h + "/" + .)'
}

sandbox_claude() {
  jq -nc --argjson dom "$(sandbox_cfg '.runNetwork // []')" --argjson sec "$(sandbox_secrets)" \
    '{sandbox: {enabled: true, failIfUnavailable: true, allowUnsandboxedCommands: false, autoAllowBashIfSandboxed: false,
      network: {allowedDomains: $dom, allowLocalBinding: true}, filesystem: {denyRead: $sec}}}'
}

sandbox_profile() {
  mkdir -p "$(dirname "$2")"
  jq -n --arg wt "$1" --arg h "$HOME" --argjson dom "$(sandbox_cfg '.runNetwork // []')" --argjson sec "$(sandbox_secrets)" \
    '{network: {allowedDomains: $dom, deniedDomains: [], allowLocalBinding: true},
      filesystem: {allowWrite: [$wt, ($h + "/Library/Caches"), ($h + "/.cache"), "/tmp", "/private/tmp", "/private/var/folders"], denyRead: $sec, denyWrite: []}}' >"$2"
}

sandboxed() {
  if [ -n "$TW_SANDBOX" ]; then
    (cd "$1" && "$TW_SRT" -s "$TW_SANDBOX" -c "$2")
  else
    (cd "$1" && eval "$2")
  fi
}
