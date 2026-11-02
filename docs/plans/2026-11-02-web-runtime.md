# План: рабочая панель с кнопками

**Статус:** в работе.
**Спецификация:** docs/specs/2026-11-02-web-runtime.md

- [x] Операторские методы и atomic idempotency поверх общего Store.
- [x] HTTP-шлюз, отдельный origin подтверждений, события и control envelope.
- [x] Подготовка фиксированных frontend-зависимостей и canary Node sandbox.
- [x] Продолжить TASK-002 через harness с контекстом готового API/toolchain.
- [x] Проверки, review, сборочный receipt и запуск через tw-web.
- [x] Проверить реальный HTTP-цикл; результат не принимать за пользователя.

- 2026-11-02 · Реализованы транзакции Store с savepoints, операторские операции,
  control/actions/events и неизменяемые idempotency keys. 93 теста контроллера
  прошли; реальный HTTP smoke подтвердил session/control, отдельное подтверждение,
  fixture accept и отсутствие дубликатов при повторном создании.
- 2026-11-02 · Подготовлены настоящие shadcn-компоненты, lockfile и зависимости.
  Homebrew Node перенесён вместе с dylib в изолированный runtime bundle. Canary
  подтвердил запрет сети, чтения наружу и записи dependencies. Next build
  в sandbox прошёл на probe и на TASK-002; TypeScript и Vitest тоже проходят.
- 2026-11-02 · Инфраструктурные сбои исправлены без ослабления sandbox: stdout
  находится в scratch, active.json — в контроллере; кэши Vitest создаются
  в сборочной копии, реальные пакеты доступны только на чтение.
- 2026-11-02 · Независимый review нашёл реальные ошибки unknown-result retry
  и сброса pending после400/422. Пользователь попросил продолжить; worker
  исправляет их с регрессионными тестами. Результат не принят за пользователя.

- 2026-11-02 · TASK-002 review/done, verdict human: 15 Python + 22 frontend
  теста, tsc и production build прошли. Рабочее дерево сверено с receipt.
  Новая панель запущена на47831; core origin подтверждений47832. Проверены
  реальные GET главной страницы, статуса и control. Команда tw-web указывает
  на controller-owned launcher. TASK-002 не принята и не применена.
