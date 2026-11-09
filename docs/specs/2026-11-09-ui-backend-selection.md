# Спецификация: Ручной выбор ИИ-агента (backend) в веб-интерфейсе Twist Web

## 1. Контекст и бизнес-цель
Пользователь использует двух автономных ИИ-агентов (Gemini и Codex) с разными подписками и лимитами квот. Чтобы эффективно распределять нагрузку и чередовать агентов при исчерпании лимитов, требуется возможность явного выбора исполнителя задачи прямо в веб-интерфейсе Twist Web при её создании.

При этом:
- Вариант «По умолчанию» должен явно показывать, какой именно агент будет назначен из текущей конфигурации проекта (например, `По умолчанию (Gemini)` или `По умолчанию (Codex)`).
- Автоматическое переключение по исчерпанию квоты на данном этапе намеренно не делается (только принудительный/ручной выбор).
- Задачи должны сохранять выбранный бэкенд на всех своих этапах (`plan`, `implement`, `check`, `review`).
- Для задач, оказавшихся на паузе или упёршихся в лимит квот (`rate_limited`), должна быть предусмотрена возможность переключить бэкенд на альтернативный.

---

## 2. Архитектура решения

### 2.1. Контроллер (`harness/`)
1. **Предоставление информации о бэкенде проекта (`harness/service.py`, `harness/web.py`):**
   - В метод `TaskService` добавляется свойство `default_backend`, возвращающее значение `backend` из `config.json` проекта (`"gemini"` или `"codex"`).
   - Эндпоинт `GET /api/v1/status` возвращает объект `project`:
     `{"id": "<id>", "name": "<name>", "backend": "<default_backend>"}`.
   - Эндпоинт `GET /api/v1/projects` в элементах `items` возвращает:
     `{"id": "<id>", "name": "<name>", "backend": "<default_backend>"}`.
2. **Приём выбора бэкенда при создании задачи (`harness/operator.py`):**
   - В `Operator.validate('submit', payload)` разрешается опциональное поле `backend`:
     `payload['backend'] in ('codex', 'gemini')`.
   - В `Operator.dispatch('submit', None, payload)` значение `backend` передаётся в `TaskService.submit(..., backend=payload.get('backend'))`.
3. **Действие смены бэкенда у существующей задачи (`harness/operator.py`, `harness/service.py`):**
   - Добавляется действие `switch_backend` в `ACTIONS`:
     разрешено для задач в состояниях `paused`, `rate_limited`, `waiting`.
   - В `validate`: `payload = {'action': 'switch_backend', 'backend': 'codex'|'gemini'}`.
   - В `dispatch`: обновляет `task['data']['backend']`, сбрасывает `retry_at` и сохраняет событие `backend_switched`.

### 2.2. Веб-интерфейс (`web/`)
1. **Типы контрактов (`web/lib/contracts.ts`, `web/lib/transport.ts`):**
   - В `Task` добавляется поле `backend?: string`.
   - В `Status.project` и `Projects.items[number]` добавляется поле `backend?: string`.
   - В `PendingCreation.body` добавляется поле `backend?: string`.
2. **Форма создания задачи (`web/components/create-task-sheet.tsx`):**
   - Разблокируется элемент выбора модели/агента (убирается `disabled` и надпись `скоро`).
   - Варианты выбора:
     - `default`: `По умолчанию (${defaultBackendName})`
     - `gemini`: `Gemini (Google)`
     - `codex`: `Codex (OpenAI)`
   - Значение по умолчанию: `default`.
   - При отправке запроса, если выбрано не `default`, в `body` передаётся `backend: selectedBackend`.
3. **Отображение в карточке и таблице (`web/components/task-card.tsx`, `web/components/task-table.tsx`):**
   - В карточке задачи и в таблице отображается бейдж исполнителя (`Gemini` или `Codex`).
   - Если задача находится в состоянии `paused` или `rate_limited`, отображается кнопка «Переключить на Codex / Gemini».

---

## 3. Критерии приёмки
1. Эндпоинт `GET /api/v1/status` и `GET /api/v1/projects` возвращают текущий `backend` проекта.
2. При создании задачи через API и форму `CreateTaskSheet` с `backend='codex'` или `backend='gemini'` задача создаётся с соответствующим бэкендом.
3. В форме `CreateTaskSheet` пункт «По умолчанию» явно содержит имя активного бэкенда проекта (например, `По умолчанию (Gemini)` или `По умолчанию (Codex)`).
4. Все тесты `tests/codex` проходят без ошибок (0 регрессий).
