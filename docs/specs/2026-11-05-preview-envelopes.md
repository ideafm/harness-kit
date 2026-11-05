# Исправление envelope read-only preview

Browser QA TASK-006 обнаружил: custom session/capabilities preview возвращают
data без обязательного request_id. HTTP transport отвергает ответ целиком,
панель показывает пустую очередь с ошибкой протокола, хотя status API доступен.

Добавить request_id в оба ответа и project_id в capabilities. Не выдавать
операторские права: actions пуст, apply false, csrf_token/confirmation_origin
пусты, control не содержит trusted widgets. Проверить реальные API и браузер.
