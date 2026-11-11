# План

- [x] Изолированный npm dev runtime, снимок результата, проверка sandbox и proxy.
- [x] Автоопределение dev при init и явная настройка/диагностика.
- [x] Отключение проекта в реестре, API и CLI, включая пустой список.
- [x] Диалог удаления и обновление выбора проекта в UI.
- [ ] Core/frontend/build, живой npm smoke и browser QA.

325 core, 169 frontend, 20 web Python, TypeScript/build и настоящий npm HTTP smoke прошли.
Browser QA нового диалога и live framework/WebSocket smoke ещё не выполнены.

По прямому поручению пользователя сборка опубликована и панель перезапущена.
Browser QA реальной панели: два проекта, открытие диалога удаления и отмена успешны.
