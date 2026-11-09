# План реализации автоматической очистки Git worktree

## План работ

- [x] 1. Добавить `remove_worktree(store, ident)` в `harness/git_results.py` и поддержать восстановление в `prepare_worktree`.
- [x] 2. Подключить вызов `remove_worktree` в `harness/integration.py:apply_accepted` после успешного merge.
- [x] 3. Подключить вызов `remove_worktree` при отклонении задачи в `harness/cli.py` и `harness/operator.py`.
- [x] 4. Добавить unit-тесты в `tests/codex/test_integration.py` и `tests/codex/test_git_preview.py`.
- [x] 5. Запустить полный тестовый набор `python3 -B -m unittest discover -s tests/codex -v`.
