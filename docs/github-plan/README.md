# Fortress: инструкции и ТЗ для GitHub

> **С 17 октября 2026 года проект перешёл с Aster на обычный Git/GitHub. Aster MCP, регистрации, claims, leases, heartbeat и сигнал запуска для координации больше не используются.** Источник задач — `plan.json`, исходников и результатов — Git. Слова lease/fencing в backend-коде относятся к надёжности заданий и сохраняют технический смысл.

Пакет размещается в ветке `codex/github-transition` репозитория [AlmazCode/Fortress](https://github.com/AlmazCode/Fortress/tree/codex/github-transition). Прежний экспорт находится в `codex/github-plan`. Новая ветка основана на его commit `bc139562beb1d4bdf306669a4cd7bdfd6332a62c` и общей базе `46b7bc941e64fec5649242b8290607c8f7339819`. Публикация документов не означает реализацию 36 задач или merge в main.

1. Сохрани текущие изменения и прекрати прежние Aster-вызовы. Получи ветку обычным `git fetch origin`; существующий чужой checkout не переключай.
2. Прочитай [AGENTS.md](../../AGENTS.md), [общую инструкцию](WORKFLOW.md), [полный план](PLAN.md) и [продуктовое ТЗ](REQUIREMENTS.md).
3. Открой своё ТЗ: [№1 Backend/главный](DEV1_BACKEND.md), [№2 Frontend](DEV2_FRONTEND.md), [№3 ML/data](DEV3_ML_DATA.md), [№4 Rules/infra](DEV4_RULES_INFRA.md). Для передачи существующим чатам есть [готовые сообщения](PROMPTS.md).
4. №1 начинает K и ведёт интеграцию. №4 начинает O1 параллельно K. Все следующие задачи выполняются только по принятым зависимостям. Статусы реализации первоначально `unverified`; старые claims и Aster accepted не переносятся автоматически.

Каждый пишет только свой `status/DEV-N.md`; главный ведёт [STATUS.md](STATUS.md). [plan.json](plan.json) — точные текущие определения; [AUDIT.md](AUDIT.md) и [AUDIT.json](AUDIT.json) — фактическая проверка миграции. [PROVENANCE.json](PROVENANCE.json) подтверждает сверку всех четырёх присланных личных ТЗ; `archive/` хранит исходный экспорт для сравнения и не содержит исполняемых инструкций.

Проверить пакет из корня checkout:

```sh
python docs/github-plan/validate_plan.py
```

Это проверка полноты, графа, файлов и согласованности инструкций; приложение, Docker, GPU, HTTPS и ML она не проверяет. GitHub не запускает агентов автоматически, и эти сообщения другим чатам не отправлялись.
