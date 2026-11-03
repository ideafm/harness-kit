# Операторский контракт /api/v1

Контракт предоставлен внешним контроллером. Его реализация находится вне workspace. Все ответы имеют {data,request_id}, ошибки — {error:{code,message,retryable,details},request_id}. Ошибки не преобразуются в пустые успешные ответы.

GET status → {project,tasks,worker}; GET tasks/{id} → Task; GET tasks/{id}/artifacts/{name} → {task,artifact,text,truncated}. Имена артефактов: specification, plan, summary, diff, checks, review.

GET capabilities → {project_id,operator_api_version:'1',actions,events:true,apply:false,human_confirmation:'separate-origin'}. GET session → {csrf_token,confirmation_origin}. Сессия и серверная проверка полномочий принадлежат gateway; launcher token браузеру не передаётся.

GET tasks/{id}/control → {task,revision,allowed_actions,pending_question_id,plan,result,confirmation_urls}. plan/result содержат точную version и digest. Только allowed_actions определяет доступность действия; state сам по себе не предоставляет полномочий.

POST tasks: {request,approval_mode:'auto'|'approve-plan'}, X-CSRF-Token, Idempotency-Key; ответ 201 {task,revision,operation_id}. Request обязателен, максимум 50 КиБ UTF-8. По умолчанию approve-plan.

POST tasks/{id}/actions: {action:'start'|'pause'|'resume'} либо {action:'answer',question_id,text}. Обязательны X-CSRF-Token, Idempotency-Key, If-Match revision; Content-Type application/json, браузерный Origin проверяет gateway. Ответ 202 {operation_id,status:'pending',task_id}. Ответ не пустой, максимум 16 КиБ UTF-8; question_id берётся из control.pending_question_id.

GET operations/{id} → {operation_id,status:'pending'|'succeeded'|'failed',task_id,revision,error?}. Только succeeded позволяет показать успех и перечитать snapshot. После сетевой неопределённости используется прежний ключ; ключ не должен заменяться для того же запроса. Engine атомарно сохраняет идемпотентность, сериализует команды и отклоняет stale revision.

approve_plan, revise_plan, accept_result, request_changes, reject_result не отправляются обычным POST. Используются только confirmation_widgets с проверками, описанными ниже. Ввод замечаний, причины отклонения, подтверждение и привязка версий принадлежат контроллеру. Frontend не хранит токенов приёмки и не предлагает отдельные страницы как обход.

GET tasks/{id}/events?after=0&limit=100 → {items,next_cursor,has_more}. Items содержат id,cursor,task_id,revision,type,occurred_at,message. Клиент последовательно получает страницы, удаляет дубликаты по id и продолжает polling. При ошибке сохраняет историю; ручное перечитывание сбрасывает cursor. 410 cursor_expired сбрасывает cursor и запускает повторное чтение истории; snapshot независимо обновляется общим polling.

400 — параметры, 403 — полномочия/CSRF, 404 — ресурс, 409 — конфликт, 422 — переход, 503 — недоступность. Отказ отображается явно. Приёмка, интеграция diff и разрешение доступа различаются; обычный ответ не создаёт grant. Frontend показывает поддерживаемый task.preview.url, но самостоятельно не запускает preview и не применяет изменения.

## TASK-004: встроенные решения и чтение

Актуальная UI-интеграция использует confirmation_widgets вместо confirmation_urls для HIGH_ACTIONS. Точный origin session.confirmation_origin и путь /confirm/embed, http loopback без credentials/fragment обязательны. Iframe имеет sandbox allow-forms allow-scripts allow-same-origin. Подтверждение и авторизация остаются в контроллере. Сообщения tw:decision проверяют origin/source/task/project/action/status и инициируют refresh, без локальной приёмки. tw:widget-size ограничивается конечными 40..420 px. Старые формы демонтируются при смене контекста.

Сессия без csrf разрешает чтение, но не команды и не widgets. Preview берётся только из task.preview.url. Worker использует task_id и observation {task_id,terminal_command,mode:events,interactive:false}; команда копируется неизменённой и никогда не исполняется frontend. Нет observation — нет придуманной команды. Данные другого проекта не используются.

B-002 и отдельные backend-контракты нужны для scheduler/зависимостей, структурированных причин, рекомендаций, событий процесса и сообщений агенту. История задачи не выдаётся за историю worker. Проверка не означает приёмку; применение подтверждается только данными integration без ошибок.

## TASK-005: применение результата

Task дополнен optional integration:{source_commit:string,commit:string,branch:string}, integration_error:string, commit_error:string. Для accepted сначала проверяется непустой integration_error («Принято, применение остановлено»), затем commit_error («Принято, коммит не создан»), затем полная непустая integration («Принято и применено»). Иначе — «Принято, применение не подтверждено». Обе причины показываются дословно безопасным текстом с предложением передать их оператору для устранения в контроллере. Детали успешного применения раскрывают первые восемь символов commit и branch без самостоятельного поиска.

Перед приёмкой preview проверяется существующей loopbackUrl. Без поддерживаемого адреса явно сообщается о недоступности. accept_result / request_changes / reject_result представлены как «Принять» / «Доработать» / «Отклонить»; соответствующие trusted widgets сохраняют все проверки полномочий и сообщений. Принять означает коммит и merge через контроллер, доработать — продолжение рабочей копии, отклонить — убрать предпросмотр без изменения основной версии.
