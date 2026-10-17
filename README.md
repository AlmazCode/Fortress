# Fortress

Локальный прототип анализа кассового видео: React/FastAPI, очередь, правила и ML-инструменты.

Первое обучение вердикта по целому видео: [проверенный Windows/CUDA workflow](docs/model/FIRST_TRAINING.md).
`tools/setup_training.ps1` устанавливает locked окружение, проверяет GPU, подготавливает локальные
ImageNet-веса, импортирует annotation package и считает feature cache. `tools/train_first.ps1`
запускает MobileNetV3-Small + GRU с checkpoint/resume, dev early stopping и отдельной holdout-оценкой.
Цель 80% проверяется по accuracy, balanced accuracy и macro-F1; заранее она не гарантируется.

Следующий этап с целью 95%+: [эксперименты на имеющихся видео](docs/model/SMALL_DATA.md).
Grouped nested CV сравнивает linear/GRU/MIL и ограниченный fine-tuning на исходных train/dev;
тестовые семьи остаются вне обучения. Независимые 95% на новых ракурсах пока не подтверждены.

**С 17 октября 2026 года работаем через обычный Git/GitHub. Aster больше не используется для координации.**

- [Инструкция всем агентам](AGENTS.md)
- [Начало работы и состав пакета](docs/github-plan/README.md)
- [Общая инструкция GitHub](docs/github-plan/WORKFLOW.md)
- [План: 36 задач / 4 разработчика](docs/github-plan/PLAN.md)
- [ТЗ №1 — Главный / Backend](docs/github-plan/DEV1_BACKEND.md)
- [ТЗ №2 — Frontend](docs/github-plan/DEV2_FRONTEND.md)
- [ТЗ №3 — ML / Данные](docs/github-plan/DEV3_ML_DATA.md)
- [ТЗ №4 — Правила / Инфраструктура](docs/github-plan/DEV4_RULES_INFRA.md)
- [Сообщения для передачи агентам](docs/github-plan/PROMPTS.md)
- [Проверка плана и миграции](docs/github-plan/AUDIT.md)

Без проверенного событийного release сервис возвращает `503 model_not_ready`.
Первый video-verdict baseline сохраняется отдельно от production событийной модели:
он не подтверждает таймкоды, нормативные правила или качество на другой камере.
