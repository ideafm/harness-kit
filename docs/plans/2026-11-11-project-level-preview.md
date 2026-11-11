# План: перенос управления запуском приложения на уровень проекта

## Этап 1. Backend / Контроллер
- [ ] Обновить `ProjectView.control_revision(ident=None)` в `harness/project_view.py` для безопасной работы без `ident`.
- [ ] Добавить методы `get_project()` и `perform_project()` в `ViewControl` (`harness/view_control.py`).
- [ ] Подключить маршруты `GET /api/v1/view` и `POST /api/v1/view` в `harness/web.py` с проверками CSRF, If-Match и Idempotency-Key.
- [ ] Добавить тесты на проектный API в `tests/codex/test_project_view.py`.
- [ ] Проверить выполнение тестов: `python3 -m unittest discover -s tests/codex -v`.

## Этап 2. Frontend хуки и контракты
- [ ] Расширить `ProjectViewResponse` в `web/lib/contracts.ts` (допустить `task_id: number | null`).
- [ ] Обновить `useProjectView` (`web/hooks/use-project-view.ts`):
  - Поддержать `task?: number` (когда `task` не передан — опрашивать и отправлять команды на `view`).
  - Сохранить изоляцию scope, отмену запросов и проверку ответов.
  - Поддержать `viewReady` как для задачи, так и для уровня проекта.

## Этап 3. Компоненты интерфейса
- [ ] Создать `ProjectPreviewBar` (`web/components/project-preview-bar.tsx`):
  - Индикатор и статусы: «Остановлен», «Запускается», «Запущен», «Ошибка».
  - Подпись активного результата: «TASK-xxx · проверенная версия» / «Версия не выбрана».
  - Адрес приложения (`address.host`).
  - Кнопки «Запустить», «Остановить», «Открыть» с иконками и текстом.
  - Состояния disabled, загрузки, ошибок, светлая и тёмная темы.
  - Адаптивность для узких экранов.
- [ ] Встроить `ProjectPreviewBar` в верхнюю панель (`TopHeader` рядом с переключателем проектов).
- [ ] Обновить `ProjectView` в карточке задачи (`web/components/project-view.tsx`):
  - Оставить действие «Показать результат этой задачи».
  - Сохранить выбор проверенной/рабочей версии и подробности.
  - Убрать дублирующие кнопки запуска, остановки и открытия.

## Этап 4. Тестирование и верификация
- [ ] Обновить и добавить frontend-тесты: `npm --prefix web test`.
- [ ] Запустить `python3 -m unittest discover -s tests/codex -v`.
- [ ] Выполнить production-сборку: `npm --prefix web run build`.
- [ ] Пересобрать и перезапустить работающий демон (`./bin/tw-web stop && ./bin/tw-web start`).
- [ ] Проверить в браузере.
- [ ] Предоставить отчёт без коммита (согласно указанию пользователя).
