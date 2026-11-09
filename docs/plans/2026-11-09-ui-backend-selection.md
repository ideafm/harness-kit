# План реализации: Ручной выбор ИИ-агента (backend) в веб-интерфейсе Twist Web

Спецификация: `docs/specs/2026-11-09-ui-backend-selection.md`

## Шаг 1. Контроллер: `TaskService` и реестр проектов
1. В `harness/service.py`:
   - Добавить свойство `default_backend` в `TaskService`, читающее `backend` из `.harness/config.json` проекта (по умолчанию `"codex"`).
   - В `TaskService.view(task)` гарантировать наличие ключа `backend` в возвращаемом представлении задачи (если не сохранён явно в `data`, подставлять `self.default_backend`).
2. В `harness/projects.py`:
   - В `Projects.listing()` дополнять каждый проект полем `backend` из его конфигурации.
3. В `harness/web.py`:
   - В `GET /api/v1/status` передавать `'backend': service.default_backend` в объекте `project`.

## Шаг 2. Контроллер: `Operator` (submit и switch_backend)
1. В `harness/operator.py`:
   - Добавить `switch_backend` в список `ACTIONS`.
   - В `Operator.control(ident)`: добавлять `switch_backend` в `allowed_actions` для задач в состояниях `paused`, `rate_limited`, `waiting`, `queued`, `blocked`.
   - В `Operator.validate()`:
     - Для `submit`: разрешить опциональное поле `backend` со значениями `'codex'` или `'gemini'`.
     - Для `switch_backend`: требовать поля `{'action', 'backend'}`, где `backend` строго `'codex'` или `'gemini'`.
   - В `Operator.dispatch()`:
     - Для `submit`: передавать `backend=payload.get('backend')` в `self.service.submit()`.
     - Для `switch_backend`: переключать `task['data']['backend']`, снимать паузу `rate_limited` при смене на другой бэкенд, логировать событие `backend_switched`.

## Шаг 3. Тестирование контроллера
1. Добавить тесты в `tests/codex/test_operator.py`:
   - Создание задачи с явным `backend='gemini'` и `backend='codex'`.
   - Отклонение невалидного `backend` при создании (защита fail-closed).
   - Выполнение `switch_backend` для задач в состояниях `paused`, `rate_limited`, сброс ожидания квоты.
2. Прогнать весь набор тестов `python3 -B -m unittest discover -s tests/codex -v`.

## Шаг 4. Веб-интерфейс (`web/`)
1. Контракты (`web/lib/contracts.ts`, `web/lib/transport.ts`):
   - Добавить поле `backend?: string` в интерфейсы `Task`, `Status.project`, `Projects.items[number]`, `PendingCreation.body`.
2. Форма создания задачи (`web/components/create-task-sheet.tsx`):
   - Принимать пропс `defaultBackend?: string`.
   - Разблокировать выбор агента / модели.
   - Опции:
     - `default`: `По умолчанию (${defaultBackendName})`
     - `gemini`: `Gemini (Google)`
     - `codex`: `Codex (OpenAI)`
   - Передавать `backend` при создании, если выбрано не `default`.
3. Отображение и переключение (`web/components/task-table.tsx`, `web/components/task-card.tsx`):
   - Передавать `defaultBackend` из текущего проекта в `CreateTaskSheet`.
   - Отображать бейдж агента (`Codex` / `Gemini`) в строке таблицы и в заголовке карточки задачи.
   - В карточке задачи предоставить переключатель/кнопку смены бэкенда при доступности действия `switch_backend`.
4. Сборка и верификация:
   - Прогнать тесты фронтенда `npm test` или `vitest run`.
   - Проверить сквозную работу через API и UI.
