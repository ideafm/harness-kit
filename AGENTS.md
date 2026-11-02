# Harness Kit

Read `docs/PROJECT-CONTEXT.md` at the start of a session for the user's product
goal, current handoff and next steps. The first-pass runner below is a foundation,
not the full product scope. Preserve the safety rules in this file.

Build an autonomous Codex development runner. The active design is in
`docs/specs/2026-11-02-codex-harness.md`; the implementation ledger is in
`docs/plans/2026-11-02-codex-harness.md`.

- Save specifications and plans, publish a short summary, then continue without
  asking for routine approval. Ask about consequential ambiguity.
- Never use SSH/SCP/SFTP, read environment files, hidden files or directories,
  credentials, keys, or secrets without the user's explicit prior confirmation
  for that resource and action. Do not evade this through scripts or MCP.
- Git operations and harness-owned state are narrow operational exceptions;
  they do not authorize arbitrary reading of `.git` or other hidden files.
- General approval of a task or plan is not permission to access protected data.
- Keep enforcement outside agent-writable code. Fail closed when isolation
  cannot be verified. Never add a fallback to unrestricted execution.
- Do not add code comments unless requested. Do not commit or merge without
  explicit user authorization. Keep the legacy Claude implementation intact
  during the initial Codex implementation.
- Run `python3 -m unittest discover -s tests/codex -v` for the new runner.
  Run `bash tests/run.sh` when changing legacy components.
