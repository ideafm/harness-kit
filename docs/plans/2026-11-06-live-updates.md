# SSE без моргания

- [x] Поток sync/changed и heartbeat с ограничением соединений и lifecycle.
- [x] Origin/scope/cursor, изменения из другого процесса, runtime и shutdown tests.
- [x] Реальный HTTP smoke без вызова модели.
- [ ] Frontend через отдельную Tw-задачу после результата TASK-008.
- [ ] Browser QA сохранения фокуса, прокрутки и черновика; приёмка человеком.

203 core-теста прошли. tests/codex/live_updates_smoke.py подтвердил настоящий
HTTP sync/changed, изменение SQLite другим соединением, обычный GET status
при открытом потоке, отказ чужому Origin и штатное закрытие при shutdown.
Число потоков ограничено 16, повторное close не возвращает слот дважды.
Наблюдение использует data_version и metadata только allowlisted state;
не читает тексты задач и не вызывает модель. При каждом reconnect — sync
и полная сверка GET, без обещания replay пропущенных уведомлений.
