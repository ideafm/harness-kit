# Бэклог и группа задач

- [x] Состояние backlog и создание placement через service/CLI/MCP/API.
- [x] Атомарный enqueue с сохраняемым порядком и проверкой всей группы.
- [x] Worker берёт только runnable; API версии и идемпотентность.
- [x] Проверки работающего worker, restart, двойного запуска и rollback группы.
- [ ] Отдельная UI-задача после TASK-008 и дальнейшее подключение зависимостей.

GET/POST /api/v1/queue, также scoped projects/{id}; группа tasks/start,
CSRF/If-Match/Idempotency-Key, operations для сохранённого результата.
Pending после сбоя запуска worker не переставляет группу заново.
Состояние backlog не равно queued без запуска процесса. Старые клиенты
с start=false сохраняют прежнее поведение, placement делает выбор явным.
CLI add --backlog / enqueue ... --start и MCP tw_submit/tw_enqueue работают.
tests/codex/live_queue_smoke.py прошёл: настоящий отдельный worker-процесс
с подменённым исполнителем, enqueue во время первой задачи, порядок 1/3/2,
нетронутый backlog 4 и повторное подключение. Вызовов модели нет.
211 core-тестов прошли, включая HTTP scope/CSRF/If-Match и повтор операции.
Текущий worker TASK-008 загружен до этой правки; новый scheduler вступит
в силу после его штатной остановки и запуска, активную реализацию не прерывать.
