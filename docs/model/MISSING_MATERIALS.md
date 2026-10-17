# D1 — пробелы и закрытые training gates

Проверено по контракту K `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`.
Источники: действующий REQUIREMENTS.md, локально предоставленный исходный case,
явно заданные медиа/материалы разметки, общий lock и схемы K.
Факты инвентаризации приведены в DATA_INVENTORY.md; исходники не изменяются.

| Условие | Наблюдение | Следующий владелец/этап |
| --- | --- | --- |
| Исходные приложения | TECHNICAL_SPEC.md, DATA_AND_TRAINING.md, CASE_COVERAGE.md отсутствуют | не выдумывать прежнее содержимое; реализовать свои docs по текущему ТЗ |
| Закрытая официальная taxonomy | не предоставлена; K taxonomy=draft | D2: собственные явно draft определения, без выдуманных 25 ID |
| Исходное видео | 42 локальных файла доступны и хэшированы | D3/D4: decode/quarantine, дубли, group split, PTS; 42 не означает 42 уникальных |
| Объектная разметка | файлы разметки/метаданных есть, gold review не проверен | D5: bbox/class/PTS/COCO QA и reviewer status |
| Temporal GRU dataset | неизвестен: фотографии и точечные метки не подтверждают интервальную разметку | D3–D5: explicit negatives/unknown/visibility, сцены и grouped split |
| Independent final другого ракурса | не выделен и не проверен | запретить final для train/thresholds; будущая независимая оценка |
| Права использования | CLI по умолчанию rights=unknown | явное подтверждение допустимого использования; не трактовать файлы как разрешение training |
| Training PC / GPU | другой ПК не проверен; локальная torch-сборка CPU | O1 и команды preflight на целевом ПК, без выдуманной CUDA/VRAM |
| Локальные pretrained weights | в self-test weights=None | будущая явная подготовка ImageNet encoder, без runtime download |
| Trained validated release | не предоставлен и не проверен | M tools сейчас; полный train/evaluate/import позже отдельным поручением |
| Нормативная применимость | D1 не исследует и не подтверждает нормы | R1/R3; не выводить юридическое нарушение по объекту/score |

Присутствие JSON/CSV ещё не доказывает наличие валидной разметки. В отчёте
annotation_files_present отделено от annotation_missing=null и review=unverified.
Неизвестные labels не отрицательные; данные objects-only не GRU sequence;
псевдоразметка не становится gold. Данные жюри не используются для обучения.

D1 tools_ready относится только к инвентарю/CPU preflight. Dataset readiness,
annotation review, групповые split, target hardware и production model quality
не получают ready от синтетического self-test. Общий training_ready=false.

Сейчас разрешены инструменты и короткий CPU smoke. Полный train, fine-tuning,
GPU search, реальная ML-оценка и подтверждение production-бюджетов остаются
будущим отдельным этапом. Без usable trained release ожидается 503 model_not_ready.

## Обновление инструментов D

Data CLI и PTS/extraction/annotation/COCO/QA реализованы и проверены на tiny synthetic.
Команды — DATA.md; DATA_READINESS.json — наблюдённый synthetic smoke report,
а не повторный аудит пользовательских 42 видео. Их существование по D1 snapshot
не отрицается, reviewed dataset/rights/independent final всё ещё не подтверждены.
Новые scene/annotation bundles имеют frame provenance anchors; старые bundles
без них нужно подготовить заново. Следующие M-инструменты не снимают этих gaps.
