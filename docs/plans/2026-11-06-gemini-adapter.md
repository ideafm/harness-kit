# План: адаптер Gemini (Antigravity) и перенос навыка commit

**Спецификация:** `docs/specs/2026-11-06-gemini-adapter.md`
**Статус:** готов

## Задачи

- [x] 1. Перенос навыка `$commit` в `~/.gemini/config/skills/commit/SKILL.md`.
- [x] 2. Seatbelt-профиль macOS (`sandbox-exec`) в `harness/security.py` и поддержка `doctor` / `sandbox_command` без зависимости от `codex`.
- [x] 3. Реализация `harness/gemini.py` (CLI `agy` и SDK `google.antigravity`, валидация `SCHEMA`, обработка лимитов `RateLimited`, read-only ограничения для `plan`/`review`).
- [x] 4. Подключение выбора бэкенда `gemini | codex` в `harness/runner.py`, `harness/cli.py`, `harness/tw.py`, `harness/installation.py`.
- [x] 5. Модульные и сценарные тесты в `tests/codex/test_gemini.py` и прогон набора тестов (`tests/codex`).
