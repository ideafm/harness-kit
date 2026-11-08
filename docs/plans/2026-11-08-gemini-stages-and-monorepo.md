# План реализации: Поддержка Gemini (agy 1.5.3) для этапов plan/implement/review и архитектура монорепозитория

**Спецификация:** `docs/specs/2026-11-08-gemini-stages-and-monorepo.md`
**Статус:** реализовано в изолированной задаче `TASK-001` (ожидает ревью и приёмки человеком)

---

## Этапы реализации

### Этап 1. Спецификация и план
- [x] 1.1. Изучить `task-010-gemini-incident-review.md`, исходный код `harness/` и тесты `tests/codex/`.
- [x] 1.2. Сохранить спецификацию и план, опубликовать краткое резюме.

### Этап 2. Верификация фактического контракта `agy` (1.5.3) на временном проекте с канарейками
- [x] 2.1. Проверить в отдельном временном каталоге (`/tmp/agy-canary-*` вне `harness-kit`) фактическое поведение `agy` (версия `1.5.3`, SHA-256 `5e4b545bff4a83a93354fc50c54631cf3e8cd02e1a469087af00929f3fdc4d51`):
  - потоковая подача промпта через `stdin`: `--input-format stream-json --output-format stream-json --json-schema <schema> -p ""`;
  - проверка поддерживаемых ключей `--settings`: подтверждён `permissions` (`deny`), отвергнуты `mcpServers`, `workspace`, `sandbox`, `seatbeltProfile`, `ignoreUserConfig`, `mode`;
  - проверка изоляции файловых инструментов (`read_file`, `write_file`, `edit_file`), запрета `command(*)`, `mcp(*)`, `read_url(*)`, `execute_url(*)` и блокировки выхода за пределы `workspace` (`../outside.txt`, `.env`, `.env.local`, `private.key`, неплановые файлы).

### Этап 3. Очистка и ужесточение адаптера Gemini (`harness/gemini.py`, `harness/tw.py`)
- [x] 3.1. Удалить из `stage_settings()`, `Gemini.build_command()` и `tw.chat_command()` неподдерживаемые ключи `--settings`, флаги `--dangerously-skip-permissions`, `--mode auto`, `-c` и вызов `mcp list --json`.
- [x] 3.2. Реализовать `verify_agy_contract()` с проверкой версии (`SUPPORTED_AGY_VERSIONS = ("1.5.3",)`), SHA-256 и обязательных флагов CLI (`--sandbox`, `--mode`, `--disable-slash-commands`, `--settings`, `--input-format`, `--output-format`, `--json-schema`).
- [x] 3.3. Реализовать формирование `permissions.deny` для read-only (`plan`, `review` с `"write_file(*)"`) и writable (`implement` с запретом записи во все файлы вне `allowed_files` и вне `scope`), а также проверку неизменности файлов рабочей копии на этапах `plan` и `review`.
- [x] 3.4. Реализовать поддержку потокового ввода `stream-json` и извлечения структурированного ответа из событий `result.structured_output`, `result.response` и `step_update(finish)`.

### Этап 4. Расширяемый выбор backend/модели по этапам, внешние `workspace`/`worktree` и `scope` монорепозитория
- [x] 4.1. Реализовать в `Runner`, `Store` и `TaskService` поддержку `stage_backends`, `stage_models` и `path_scope` / `scope` с сохранением выбранного `backend` при `pause`, `resume` и `answer` и поэтапной проверкой квот `Guard`.
- [x] 4.2. Обеспечить в `Store.folder()` / `external_tasks_root()` размещение `workspace` (snapshot) и `git-worktree` новых задач вне основного git-дерева с сохранением совместимости для существующих задач.
- [x] 4.3. Обеспечить в `Runner.step("plan")`, `Runner.report()` и `Runner.step("check")` проверку принадлежности файлов выбранному `scope` и запуск проверок (`check` / `node.check`) из каталога `workspace / scope`.

### Этап 5. Модульные и контрактные тесты + сквозной прогон на синтетическом проекте
- [x] 5.1. Обновить и расширить `tests/codex/test_gemini.py`: тесты команды, `--settings`, `stream-json` stdin/ответа, fail-closed отказа при неподдерживаемой версии или нарушении контракта sandbox, сохранения backend/stage_backends при паузе и возобновлении, изоляции квот, размещения `workspace`/`worktree` вне git-дерева и работы `scope` в сценарии монорепозитория (`web/` + корневой `harness/`).
- [x] 5.2. Прогнать полный набор `python3 -m unittest discover -s tests/codex -v` без регрессий Codex.
- [x] 5.3. Выполнить безопасный сквозной прогон Gemini (`plan` -> `implement` -> `check` -> `review`) на временном синтетическом проекте с канарейками.
- [x] 5.4. Оформить изменения в изолированной задаче `TASK-001` проекта `Harness Kit` в состоянии `review` (`stage = done`), без `accept`, `apply-result` и `git commit`.
