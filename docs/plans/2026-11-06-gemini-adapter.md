# План: исправление адаптера Gemini / Codex и guard'ов изоляции

**Спецификация:** `docs/specs/2026-11-06-gemini-adapter.md`
**Статус:** выполнено

## Задачи

- [x] 1. `harness/security.py` и `harness/node.py`: исправить `seatbelt_profile(workspace, writable, extra_read=())` (глобальный `secret_regex`, корректное экранирование regex для `sandbox-exec`, `(literal "/")`, `extra_read` строго до `deny`), убрать выбор модели изоляции по `Path(driver).name` и конкатенацию `allow` после `deny` в `node.py`.
- [x] 2. `harness/gemini.py`: отделить сетевой клиент модели от песочницы инструментов в `workspace`, передавать `workspace` и `sandbox_command` в `LocalAgentConfig` / `CapabilitiesConfig`, обеспечить fail-closed на `plan`/`review` при отсутствии `BuiltinTools.read_only()`.
- [x] 3. `harness/tw.py`: добавить в `chat_command()` для `gemini` read-only профиль (`--sandbox`, `--mode plan`, `--disable-slash-commands`, `profile(root, False)`) и обязательный MCP-сервер `tw`; убрать пропуск `agy` в `verify_servers()` и обеспечить fail-closed проверку MCP allowlist и sandbox; поддержать `tw --backend=codex|gemini`.
- [x] 4. `harness/quota.py`: адаптировать `Guard.check()` и `read()` под `codex` и `gemini`, выбрасывать явную ошибку конфигурации при отсутствии настроек выбранного backend вместо ложного `QuotaPause`.
- [x] 5. `harness/cli.py`, `harness/runner.py`, `harness/state.py`, `harness/service.py`, `harness/installation.py`: вернуть `codex` как backend по умолчанию, валидировать `--backend` до запуска worker, сохранять `task["data"]["backend"]` при создании/запуске и восстанавливать его при `resume`/`answer`.
- [x] 6. `tests/codex/test_gemini.py`: добавить целевые тесты на выбор и сохранение backend, отклонение неизвестного `--backend`, MCP allowlist для `gemini`, блокировку секретов вне `workspace`, порядок правил Seatbelt в `node.py`, границу `workspace`/сети в `Gemini` и `Guard` для каждого backend; прогнать полный `python3 -m unittest discover -s tests/codex -v`.
