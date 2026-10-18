# Документация Fortress

Начните с [корневого README](../README.md).

| Задача | Документ |
| --- | --- |
| Запуск на Windows, зависимости, CPU/CUDA | [LOCAL_SETUP.md](LOCAL_SETUP.md) |
| Web/API URL, ключ, запросы и публичная сдача | [JURY_HANDOFF.md](JURY_HANDOFF.md) |
| Устройство сервиса и ограничения профилей | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Фактическое состояние и проверки | [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| Быстрая человеческая разметка кадров | [HUMAN_REVIEW.md](HUMAN_REVIEW.md) |
| API и данные | [OpenAPI](../contracts/openapi.yaml), [контракты](../contracts/STACK.md) |
| Linux/PostgreSQL/Celery | [backend](../backend/README.md), [operations](operations/SETUP.md) |
| Frontend/dev/сборка | [frontend](../frontend/README.md) |
| Первое обучение и воспроизведение | [FIRST_TRAINING.md](model/FIRST_TRAINING.md) |
| Обучение подробных событий и итоговые метрики | [TEMPORAL_EVENT_TRAINING.md](model/TEMPORAL_EVENT_TRAINING.md), [EVENT_TRAINING_RESULTS.json](model/EVENT_TRAINING_RESULTS.json) |
| Подключённый ансамбль75%, установка и возврат к контролю | [SEED_VOTE.md](model/SEED_VOTE.md) |
| Новые головы действий/присутствия и контекст описаний | [SOURCE_ACTIONS.md](model/SOURCE_ACTIONS.md), [метрики](model/SOURCE_ACTIONS_RESULTS.json) |
| Предыдущие эксперименты границ объектов | [OBJECT_BOUNDARIES_RESULTS.json](model/OBJECT_BOUNDARIES_RESULTS.json) |
| Правила и источники | [RULES.md](operations/RULES.md), [CASE_SUPPORT.md](operations/CASE_SUPPORT.md) |

`docs/model/` сохраняет протоколы и отрицательные результаты исследований, а не набор готовых production-моделей. `docs/github-plan/` — исторический план четырёх разработчиков и журналы с привязкой к прошлым commits. Эти записи не заменяют текущее состояние и не требуют продолжать старую административную координацию.
