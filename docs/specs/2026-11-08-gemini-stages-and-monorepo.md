# Спецификация: Поддержка Gemini для этапов plan/implement/review и архитектура монорепозитория Harness Kit

Дата: 2026-11-08. Статус: реализовано в изолированной задаче `TASK-001` (ожидает ревью и приёмки человеком).

---

## 1. Контекст и проблема

В ходе выполнения `TASK-010` (проект `web`, backend `gemini`) этап `plan` завершился сбоем CLI `agy`:
`Error: --settings: unknown setting "mcpServers"`.

Технический разбор (`task-010-gemini-incident-review.md`) и живая контрактная проверка `agy` (`1.5.3`, SHA-256 `5e4b545bff4a83a93354fc50c54631cf3e8cd02e1a469087af00929f3fdc4d51`) во временном каталоге с канарейками выявили следующие расхождения между адаптером `harness/gemini.py` / `harness/tw.py` и фактическим контрактом `agy`:

1. **Неподдерживаемые ключи `--settings`:** `agy` валидирует ключи верхнего уровня JSON по структуре `settings.json` и отвергает `mcpServers`, `workspace`, `sandbox`, `seatbeltProfile`, `ignoreUserConfig`, `mode`, `permissionPreset`. Поддерживаемый ключ политики — `permissions` (`{"allow": [...], "ask": [...], "deny": [...]}`).
2. **Семантика `-p` и потокового ввода:** `agy -p -` передаёт буквальную строку `"-"` как запрос, а не читает `stdin`. Подтверждённый headless-контракт чтения `stdin` без ограничения длины аргументов командной строки:
   `--input-format stream-json --output-format stream-json --json-schema <schema> -p ""` с подачей NDJSON-события `{"event": "user", "message": {"content": "<prompt>"}}` в `stdin`.
3. **Опасные флаги на этапе `implement` и поведение `--mode plan`:**
   - `--mode auto` и `--dangerously-skip-permissions` отключают подтверждения и позволяют агенту выходить за пределы `workspace`.
   - `--mode plan` при `--disable-slash-commands` игнорируется с предупреждением, а без `--disable-slash-commands` порождает асинхронный `invoke_subagent(TypeName="research")` и завершает ход до готовности ответа.
   - Подтверждённый безопасный режим для всех этапов (`plan`, `implement`, `review`) — `--sandbox --mode accept-edits --disable-slash-commands` в сочетании с явными правилами `permissions.deny`:
     - Для `plan` и `review` (`writable=False`): `"write_file(*)"` в `permissions.deny` блокирует любые записи и правки файлов (`write_file`, `edit_file`, `replace_file_content`).
     - Для всех этапов: `"mcp(*)"`, `"read_url(*)"`, `"execute_url(*)"`, `"command(*)"` блокируют MCP, сетевые инструменты агента и запуск произвольных shell-команд (проверки `check` контроллер выполняет сам в отдельном Seatbelt-песочнице).
     - Для `implement` (`writable=True`): запись разрешена только в файлы утверждённого списка `files` внутри `workspace` (все остальные существующие файлы рабочей области и все защищённые маски добавляются в `permissions.deny` как `write_file(<rel>)` и `write_file(<abs>)`), а выход за `cwd` блокируется `--mode accept-edits` и `--sandbox`.
4. **Несовместимость флага `-c` и `mcp list` в `harness/tw.py`:** в `agy` короткий флаг `-c` означает `--continue` (продолжение прошлой сессии), а не настройку конфигурации; вызов `agy ... mcp list --json` не поддерживается.
5. **Размещение `workspace` и `git-worktree`:** каталоги задач размещаются вне основного git-дерева (`<toplevel.parent>/<toplevel.name>-harness-tasks/<project_id>-<ino>/tasks/TASK-NNN`), чтобы родительский `.git` никогда не оказывался выше рабочей копии задачи (при сохранении обратной совместимости для уже существующих каталогов `.harness/tasks/TASK-NNN`).
6. **Монорепозиторий и `scope`:** задачи поддерживают ограничение области путей `path_scope` / `scope` (например, `web` или `harness`), проверку принадлежности всех планируемых и изменённых файлов выбранному `scope`, блокировку чтения/записи файлов вне `scope` в `stage_settings` и запуск проверок `check` из каталога `workspace / scope`.

---

## 2. Целевая архитектура

### 2.1. Расширяемый выбор backend и модели по этапам

1. **Конфигурация задачи и проекта:**
   - Сохраняется обратная совместимость с полями `task["data"]["backend"]` (`"codex"` | `"gemini"`) и `config["backend"]` (по умолчанию `"codex"`).
   - Поддерживаются поэтапные переопределения `stage_backends` (`{"plan": "gemini", "implement": "codex", "review": "gemini"}`) и `stage_models` (`{"plan": "...", "implement": "...", "review": "..."}`) на уровне задачи и конфигурации проекта.
   - Метод `Runner.task_backend(task, stage=None)` разрешает backend для активного этапа в порядке приоритета:
     1. `task["data"]["stage_backends"][stage]`
     2. `task["data"]["backend"]`
     3. `Runner.backend_name` (переданный через CLI `--backend`)
     4. `config["stage_backends"][stage]`
     5. `config["backend"]` (по умолчанию `"codex"`)
   - Метод `Runner.task_model(task, stage=None)` аналогично разрешает модель этапа (`stage_models[stage]` -> `task["data"]["model"]` -> `config["stage_models"][stage]` -> `config["model"]`).
2. **Сохранение при паузе и возобновлении:**
   - Выбранные `backend`, `stage_backends`, `model`, `stage_models` и `path_scope` сохраняются в `task["data"]` при создании и старте задачи и остаются неизменными при `pause`, `resume`, `answer` и перезапуске воркера.
3. **Изоляция квот по backend этапа:**
   - `Guard.check(starting=..., backend=stage_backend)` проверяет лимиты именно того backend, который выполняет текущий этап (`plan`, `implement`, `check`, `review`).

### 2.2. Подтверждённый контракт `agy` (1.5.3) и fail-closed защита

1. **Проверка версии и контракта (`verify_agy_contract`):**
   - Поддерживаемая версия CLI закреплена константой `SUPPORTED_AGY_VERSIONS = ("1.5.3",)`.
   - В `Gemini.preflight()` проверяется:
     - `doctor({**self.config, "backend": "gemini"})` (канареечная проверка Seatbelt);
     - наличие исполняемого файла `agy`, его SHA-256 дайджест и точное совпадение версии `agy --version` с `SUPPORTED_AGY_VERSIONS`;
     - наличие обязательных флагов (`--sandbox`, `--mode`, `--disable-slash-commands`, `--settings`, `--input-format`, `--output-format`, `--json-schema`, `stream-json`, `accept-edits`) в `agy --help`.
   - При несовпадении версии или отсутствии обязательных флагов выбрасывается `RuntimeError` до запуска модели (fail-closed).
2. **Формирование `--settings` (`stage_settings`):**
   - Передаётся только подтверждённый ключ верхнего уровня `{"permissions": {"deny": [...]}}`.
   - В `deny` всегда включаются:
     - `"mcp(*)"`, `"read_url(*)"`, `"execute_url(*)"`, `"command(*)"`;
     - защищённые шаблоны чтения и записи (`.env`, `.env.*`, `*.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `credentials*`, `secret*`, `id_rsa*`, `id_ed25519*`, `id_ecdsa*`, `.*`) и точные пути любых защищённых файлов или файлов вне `scope`;
     - при `writable=False` (`plan`, `review`): `"write_file(*)"`;
     - при `writable=True` (`implement`): запрет `write_file(<rel>)` и `write_file(<abs>)` для всех существующих файлов рабочей копии, не входящих в утверждённый список `files` плана.
3. **Команда запуска этапа (`Gemini.build_command`):**
   - `[agy, "--sandbox", "--mode", "accept-edits", "--disable-slash-commands", "--settings", json.dumps(settings, sort_keys=True), "--input-format", "stream-json", "--output-format", "stream-json", "--json-schema", str(schema), *(["--model", model] if model else []), "-p", ""]`.
   - Полный запрет `--dangerously-skip-permissions`, `--mode auto`, `-c`, `--continue` и неподтверждённых ключей `--settings`.
4. **Контроль неизменности рабочей копии:**
   - На этапах `plan` и `review` `Gemini.call()` сверяет дайджесты всех файлов `workspace` до и после вызова `agy` и выбрасывает `RuntimeError` при любой попытке модификации.
   - На этапе `implement` `Runner.report()` проверяет отсутствие защищённых путей, симлинков, жёстких ссылок, изменений вне ` data["files"]` и вне `scope`.

---

## 3. Судьба `TASK-010` и `TASK-009`

- `TASK-010` в `web/.harness` сохраняется в состоянии `blocked` (`stage = plan`) как заблокированный артефакт инцидента; её статус, backend и ветка `tw/TASK-010` не изменяются.
- `TASK-009` в `web/.harness` сохраняется в состоянии `waiting` (`stage = implement`) без изменений.
