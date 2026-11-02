# Операторский контракт /api/v1

Контракт предоставлен внешним контроллером. Его реализация находится вне workspace. Все ответы имеют {data,request_id}, ошибки — {error:{code,message,retryable,details},request_id}. Ошибки не преобразуются в пустые успешные ответы.

GET status → {project,tasks,worker}; GET tasks/{id} → Task; GET tasks/{id}/artifacts/{name} → {task,artifact,text,truncated}. Имена артефактов: specification, plan, summary, diff, checks, review.

GET capabilities → {project_id,operator_api_version:'1',actions,events:true,apply:false,human_confirmation:'separate-origin'}. GET session → {csrf_token,confirmation_origin}. Сессия и серверная проверка полномочий принадлежат gateway; launcher token браузеру не передаётся.

GET tasks/{id}/control → {task,revision,allowed_actions,pending_question_id,plan,result,confirmation_urls}. plan/result содержат точную version и digest. Только allowed_actions определяет доступность действия; state сам по себе не предоставляет полномочий.

POST tasks: {request,approval_mode:'auto'|'approve-plan'}, X-CSRF-Token, Idempotency-Key; ответ 201 {task,revision,operation_id}. Request обязателен, максимум 50 КиБ UTF-8. По умолчанию approve-plan.

POST tasks/{id}/actions: {action:'start'|'pause'|'resume'} либо {action:'answer',question_id,text}. Обязательны X-CSRF-Token, Idempotency-Key, If-Match revision; Content-Type application/json, браузерный Origin проверяет gateway. Ответ 202 {operation_id,status:'pending',task_id}. Ответ не пустой, максимум 16 КиБ UTF-8; question_id берётся из control.pending_question_id.

GET operations/{id} → {operation_id,status:'pending'|'succeeded'|'failed',task_id,revision,error?}. Только succeeded позволяет показать успех и перечитать snapshot. После сетевой неопределённости используется прежний ключ; ключ не должен заменяться для того же запроса. Engine атомарно сохраняет идемпотентность, сериализует команды и отклоняет stale revision.

approve_plan, revise_plan, accept_result, request_changes, reject_result не отправляются обычным POST. control.confirmation_urls[action] открывается в новой вкладке с rel=noopener noreferrer только после проверки точного http://127.0.0.1:47832 и pathname /confirm. В диалоге показаны версия плана, риск, объём и причина утверждения. Причина окончательного отклонения и замечания вводятся на странице контроллера. Финальное подтверждение и привязка точных версий принадлежат контроллеру. Frontend не хранит токенов приёмки. Обычная ссылка остаётся доступна при блокировке открытия новой вкладки.

GET tasks/{id}/events?after=0&limit=100 → {items,next_cursor,has_more}. Items содержат id,cursor,task_id,revision,type,occurred_at,message. Клиент последовательно получает страницы, удаляет дубликаты по id и продолжает polling. При ошибке сохраняет историю; ручное перечитывание сбрасывает cursor. 410 cursor_expired сбрасывает cursor и запускает повторное чтение истории; snapshot независимо обновляется общим polling.

400 — параметры, 403 — полномочия/CSRF, 404 — ресурс, 409 — конфликт, 422 — переход, 503 — недоступность. Отказ отображается явно. Приёмка, интеграция diff и разрешение доступа различаются; обычный ответ не создаёт grant. Preview не запускается, применение недоступно.
