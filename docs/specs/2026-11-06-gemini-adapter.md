# Адаптер Gemini (Antigravity) и перенос навыка commit

Дата: 2026-11-06. Статус: готов.

## Цель

Подключить Gemini (через Antigravity CLI `agy` и Antigravity Python SDK `google-antigravity`) как поддерживаемый исполнитель этапов `plan`, `implement`, `review` и интерактивного режима `tw`, сохранив полную обратную совместимость с существующим адаптером `codex` и всеми 214 тестами. Перенести пользовательский навык `$commit` в глобальную конфигурацию Antigravity.

## Требования и инварианты безопасности

1. **Два поддерживаемых бэкенда (`gemini` и `codex`):**
   - `Runner` выбирает адаптер `Gemini` при `backend == "gemini"` в `.harness/config.json` и сохраняет `Codex` для существующих конфигураций без поля `backend` или с `backend == "codex"`.
   - `harness init` и `tw init` поддерживают `--backend gemini|codex` и `--agy PATH`. По умолчанию при наличии `--backend gemini` (или автоопределении) инициализируется `gemini`, при явном `--codex` или существующих сценариях — совместимый режим.
2. **Изоляция и песочница (Fail-Closed):**
   - Для `gemini` проверка `doctor` и запуск проектных проверок (`check`) используют нативный macOS `/usr/bin/sandbox-exec` со строгим Seatbelt-профилем (`seatbelt_profile`), запрещающим сеть, чтение и запись скрытых файлов (`.*`), `.env*`, ключей, `credentials*`, `secret*`, а также запись вне рабочей копии.
   - На этапах `plan` и `review` рабочая копия открыта только на чтение; запись разрешена только на этапе `implement`.
   - Если проверка песочницы не проходит или бинарник/SDK недоступен, выполнение блокируется (fail-closed) без неограниченного fallback.
3. **Адаптер `Gemini` (`harness/gemini.py`):**
   - Поддерживает вызов через CLI `agy` (`-p`, `--output-format json`, `--json-schema`, `--sandbox`, `--dangerously-skip-permissions`, `--disable-slash-commands`) с распаковкой JSON-конверта ответа и проверкой по `SCHEMA`.
   - Поддерживает вызов через Python SDK `google.antigravity` (`LocalAgentConfig`, `CapabilitiesConfig`, `BuiltinTools.read_only()` для `plan`/`review`) в изолированном дочернем процессе под управлением `execute` (с учётом `active.json`, таймаута и остановки группы процессов).
   - Ошибки квот и лимитов (`resource_exhausted`, `429`, `quota_exceeded`, `rate_limit_exceeded`, `usage limit`) переводят задачу в состояние `rate_limited` с сохранением этапа и попыток.
4. **Перенос навыка `commit`:**
   - Навык `$commit` перенесён из `~/.codex/skills/commit/SKILL.md` в глобальный каталог Antigravity `~/.gemini/config/skills/commit/SKILL.md`.
