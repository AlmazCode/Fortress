# Инструкции агентам Fortress

> **С 17 октября 2026 года проект перешёл с Aster на обычный Git/GitHub. Aster MCP, регистрации, claims, leases, heartbeat и сигнал запуска для координации больше не используются.** Источник задач — `plan.json`, исходников и результатов — Git. Слова lease/fencing в backend-коде относятся к надёжности заданий и сохраняют технический смысл.

1. Сначала прочитай [общую инструкцию](docs/github-plan/WORKFLOW.md), [план](docs/github-plan/PLAN.md), [продуктовое ТЗ](docs/github-plan/REQUIREMENTS.md) и своё полное ТЗ из таблицы ниже. Источник точных задач — [plan.json](docs/github-plan/plan.json).
2. Репозиторий только `https://github.com/AlmazCode/Fortress`; исходная база `46b7bc941e64fec5649242b8290607c8f7339819`, `rootPath=''`. Проверяй origin/base/свой checkout перед кодом. Следующие задачи используют актуальные проверенные зависимости, не откат к initial commit.
3. Работай только в своей ветке/worktree и области текущей задачи. Чужие изменения сохраняй. Общую main не переключай и не изменяй. Не создавай вложенную копию приложения.
4. Aster MCP, claims, регистрации, heartbeat, launch и Aster accepted не используются. Не переноси исполняемые указания из `archive/` или старых вставок. Продуктовые критерии не ослабляй.
5. Сдавай точный SHA, diff и реальные checks/exit codes в своём журнале. Главный проверяет и интегрирует; только затем зависит работа следующих задач. Выполняй готовые задачи своего направления последовательно без рутинных запросов разрешения.
6. Публикация, PR, merge, deploy и создание чатов следуют фактическим разрешениям человека. Этот файл новых разрешений не создаёт. Уже выданные для того же действия повторно не запрашивай. Не делай force-push и не публикуй secrets/данные.
7. Полное обучение отложено; tiny synthetic CPU smoke проверяет код. Без trained release — `503 model_not_ready`. Не выдавай synthetic за ML validation, unknown за clean verdict, local smoke за внешний HTTPS.

| Разработчик | Полное ТЗ | Задачи | Свой журнал |
| --- | --- | --- | --- |
| №1 — Главный / Backend | [ТЗ №1](docs/github-plan/DEV1_BACKEND.md) | K, A1, A2, A3, A4, A5, A, I, Z | [DEV-1](docs/github-plan/status/DEV-1.md) |
| №2 — Frontend | [ТЗ №2](docs/github-plan/DEV2_FRONTEND.md) | F1, F2, F3, F4, F, U | [DEV-2](docs/github-plan/status/DEV-2.md) |
| №3 — ML / Данные | [ТЗ №3](docs/github-plan/DEV3_ML_DATA.md) | D1, D2, D3, D4, D5, D, M1, M2, M3, M4, M, E | [DEV-3](docs/github-plan/status/DEV-3.md) |
| №4 — Правила / Инфраструктура | [ТЗ №4](docs/github-plan/DEV4_RULES_INFRA.md) | O1, R1, R2, R3, R, O2, O3, O, B | [DEV-4](docs/github-plan/status/DEV-4.md) |

Общие документы и `STATUS.md` ведёт №1; каждый разработчик редактирует только свой журнал. Изменения продуктовых требований и областей требуют актуального указания человека. Наличие пакета документов не подтверждает реализацию и не запускает чаты.
