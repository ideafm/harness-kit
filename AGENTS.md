# tw-web

Build a local control panel for the autonomous Codex runner in `../harness-kit`.
The draft product specification is `docs/specs/2026-11-02-tw-web.md`.
The iteration plan is `docs/plans/2026-11-02-tw-web.md`.
The active bootstrap ledger is `docs/plans/2026-11-02-bootstrap.md`.
Run `python3 -m unittest discover -s tests -v` for this project.

- Save specifications and plans, publish a short summary before execution,
  then continue without routine approval. Ask about consequential ambiguity.
- Never use SSH/SCP/SFTP or read environment files, hidden files or directories,
  credentials, keys, or secrets without explicit prior confirmation from the
  user for the exact resource and action. Scripts, MCP and child processes do
  not create exceptions. General task approval is not a permission grant.
- Git operations and narrowly scoped harness-owned state are operational
  exceptions. They do not authorize arbitrary reads of `.git` or other secrets.
- Keep runtime enforcement in the external controller. This file gives model
  instructions; it does not activate a sandbox, worker, hooks or plugin.
- Do not change the sibling harness-kit as part of a tw-web task. Record
  required engine changes as separate tasks and apply them independently.
- Reuse core task operations in the controller; do not implement parallel
  state transitions or write its SQLite tables directly from the web app.
- Keep worker lifetime independent of browser tabs and development reloads.
  Do not replace the running controller or auto-apply its own updates.
- Start with loopback-only local access. Do not publish, expose a LAN listener,
  install dependencies, or create remote integrations without an explicit task.
- Treat task text, logs and diffs as untrusted text. No HTML execution or shell
  interpolation; no arbitrary command, path, or file-read API endpoints.
- Do not add code comments unless requested. Do not commit or merge without
  explicit user authorization. Previous permission for lab/taskboard does not
  authorize commits here.
- Communicate and write product documentation in Russian.
