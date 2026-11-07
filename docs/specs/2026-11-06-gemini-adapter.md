# Адаптер Gemini / Codex и изоляция запуска backend

Дата: 2026-11-07. Статус: в работе.

## Цель

Реализовать надёжный выбор backend (`codex` | `gemini`) через `tw --backend=codex|gemini` и `harness`, сохранив `codex` как backend по умолчанию, разделив специфику запуска каждого backend от общей логики `Runner`/worker и закрыв выявленные на аудите коммита `8742d0a` уязвимости изоляции, MCP allowlist, Seatbelt-профиля, границы `workspace`/сети в `Gemini` и проверки лимитов `Guard`.

## Результаты аудита коммита `8742d0a`

1. **`tw.chat_command()` и `tw.verify_servers()` (`harness/tw.py`) — ПОДТВЕРЖДЕНО:**
   - Для `gemini` в `chat_command()` терялась конфигурация MCP-сервера `tw` (`bin/tw-mcp --project <root>`) и read-only профиль (`permission_args(root, False)` / `--mode plan`).
   - В `verify_servers()` стоял обход `if Path(command[0]).name == "agy": return`, полностью пропускавший проверку разрешённых MCP-серверов по имени исполняемого файла.
   - Вызов `tw --backend=codex|gemini` без позиционного аргумента `chat` не распознавался как запуск чата.
2. **`seatbelt_profile()` (`harness/security.py`) — ПОДТВЕРЖДЕНО (включая 3 дефекта реального `sandbox-exec`):**
   - `hidden_regex` и `secret_regex` были ограничены префиксом `^{escaped}/` (только внутри `workspace`), оставляя открытыми секреты и скрытые пути в системных и дополнительных (`extra_read`) каталогах.
   - Префикс `(?i)^` в `secret_regex` вызывал ошибку компиляции `/usr/bin/sandbox-exec` (`unexpected ^ operator in middle of expression`, код 65).
   - Форматирование `#{json.dumps(...)}` удваивало обратные слеши (`\\.` вместо `\.`), из-за чего Seatbelt искал литеральный символ `\` и пропускал `.env`, `.hidden` и `*.key` даже внутри `workspace`.
   - Отсутствие `(literal "/")` в `(allow file-read* ...)` приводило к `SIGABRT (-6)` в `dyld` при старте дочернего процесса.
3. **`harness/node.py` (`command()`) — ПОДТВЕРЖДЕНО:**
   - Ветка `if Path(str(driver)).name in {"sandbox-exec", "gemini", "agy"}` вручную дописывала `(allow file-read* ...)` в конец профиля **после** `(deny file-read* file-write* ...)`, что в Seatbelt перекрывает запреты и обходит `security.py`.
4. **Gemini runtime (`Gemini.build_command()` → `run_sdk()` в `harness/gemini.py`) — ПОДТВЕРЖДЕНО:**
   - Весь клиент `agy` / `python -m harness.gemini` оборачивался во внешний `sandbox-exec` с `(deny default)` без сети и без доступа к каталогу задачи `folder`, блокируя обращение клиента к API модели и чтение/запись `schema`/`answer`.
   - В `run_sdk()` параметр `workspace` не передавался в `LocalAgentConfig` и не ограничивал выполнение инструментов, а при отсутствии `BuiltinTools.read_only()` на этапах `plan`/`review` происходил откат к `capabilities = None` вместо fail-closed отказа.
5. **`harness/quota.py` (`Guard.check()`) — ПОДТВЕРЖДЕНО:**
   - `Guard.check()` читал только `self.config['codex']`, а отсутствие или невалидность конфигурации выбранного backend перехватывалось общим `except` и превращалось в `QuotaPause(..., now + 60)` вместо явной ошибки конфигурации.
6. **Выбор и сохранение backend (`harness/cli.py`, `harness/runner.py`, `harness/state.py`, `harness/service.py`) — ПОДТВЕРЖДЕНО:**
   - В `cli.py` дефолтом `init` стал `gemini` вместо `codex`.
   - `create_backend()` молча откатывался к `Codex` при неизвестном `backend`.
   - `backend` задачи не сохранялся в `task["data"]["backend"]` и не восстанавливался при `resume` / `answer` / перезапуске worker.

## Требования к исправлению

1. **Выбор, валидация и сохранение backend:**
   - Поддерживаемые значения: `BACKENDS = ("codex", "gemini")`; по умолчанию везде используется `"codex"`.
   - Неизвестное значение `--backend` или `config["backend"]` / `task["data"]["backend"]` немедленно отклоняется (`ValueError`) до создания задачи, запуска чата или старта worker.
   - `tw` поддерживает `--backend=codex|gemini` для `tw` (чат по умолчанию), `tw chat`, `tw init`, `tw add`, `tw run`, `tw worker`.
   - При создании и первом запуске задачи выбранный `backend` сохраняется в `task["data"]["backend"]` и неизменно используется при `resume`, `answer` и повторных проходах `Runner`.
2. **Изоляция `tw.chat_command()` и `tw.verify_servers()`:**
   - Для обоих backend `chat_command()` включает read-only ограничение на каталог проекта (`permission_args(root, False)` для `codex`; `--sandbox`, `--mode plan`, `--disable-slash-commands` и read-only профиль в `--settings` для `gemini`) и обязательную конфигурацию MCP-сервера `tw`.
   - `verify_servers()` никогда не пропускает проверку по имени бинарника (`agy`): проверяет наличие read-only sandbox и конфигурации `tw`, запрашивает `mcp list --json`, отключает посторонние серверы в интерактивном режиме с повторной проверкой и завершается fail-closed (`RuntimeError`), если изоляцию или список MCP-серверов нельзя подтвердить.
3. **`seatbelt_profile()` и `harness/node.py`:**
   - `seatbelt_profile(workspace, writable, extra_read=())` формирует валидный профиль `/usr/bin/sandbox-exec` с `(literal "/")`, корректным экранированием regex без `json.dumps` удвоения слешей и без неподдерживаемого `(?i)^`.
   - Все правила `(allow file-read* ...)` (включая `extra_read`) располагаются строго **до** финального правила `(deny file-read* file-write* ...)`.
   - Запрет секретов (`secret_regex`) действует глобально по всей файловой системе (`^/(.*/)?...`), а запрет скрытых путей (`hidden_rules`) покрывает `workspace`, все `extra_read` и открытые системные корни.
   - `harness/node.py` использует `sandbox_command(..., extra_read=(runtime_dir, dep_dir))` и `profile(..., extra_read=...)` без обходных веток по `Path(driver).name` и без дописывания `allow` после `deny`.
4. **Граница `workspace` и сети в `Gemini` (`harness/gemini.py`):**
   - Клиент `Gemini` (`agy` или `run_sdk`) запускается с `cwd=workspace`, а изоляция файловой системы и запрет сети применяются к инструментам и командам, исполняемым агентом в `workspace` (через `--sandbox`, `--mode plan|auto`, `--settings` с `profile(workspace, writable)` и `sandbox_command` для SDK-инструментов), не блокируя соединение самого клиента модели с API.
   - В `run_sdk()` `workspace` валидируется, передаётся в `LocalAgentConfig(workspace=str(workspace), ...)` и `CapabilitiesConfig(workspace=str(workspace), sandbox_command=...)`; на этапах `plan` и `review` при недоступности `BuiltinTools.read_only()` выполнение завершается fail-closed (`RuntimeError`).
5. **Проверка лимитов `Guard` (`harness/quota.py`):**
   - `Guard.check()` определяет активный backend (`task` или `config`), проверяет наличие его конфигурации до чтения лимита и при отсутствии конфигурации или неизвестном backend выбрасывает явную ошибку (`RuntimeError` / `ValueError`), а не `QuotaPause`.
   - Для `codex` читается `config["codex"]`, для `gemini` — `config["agy"]` / `config["gemini"]` через `read(driver, backend=backend)`.
