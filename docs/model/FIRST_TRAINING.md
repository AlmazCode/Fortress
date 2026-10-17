# Первое обучение на локальном annotation package

Поручение от 18 октября 2026: подготовить первый запуск обучения с целью качества 80%+.
Целевая первая задача — бинарный вердикт **по целому видео**, как в исходном кейсе ForteBank.
Реализован MobileNetV3-Small IMAGENET1K_V1 → 576 признаков при 2 fps → causal GRU 1×256 →
masked mean/max pooling → один logit. Рамки объектов и приблизительные action intervals
для этой задачи не требуются. Вердикт — предоставленная метка сценария, а не юридическое заключение.

Существующие action train/export/production gates сохранены. Новый формат
`video-baseline-checkpoint-v1` они не принимают за production release. Он предназначен для
воспроизводимого первого обучения и проверки подхода. Детекция действий, точная локализация,
кадры событий и применимые правила требуют собственной размеченной выборки и приёмки.

## Подготовка в Windows

Python 3.11; NVIDIA RTX 5060 8 GB; достаточно места для CUDA wheel (~2.6 GiB), исходников и checkpoint.
Запускать из отдельного checkout ветки с этим workflow. Пользовательские данные остаются вне Git.

```powershell
& .\tools\setup_training.ps1 -DatasetPackage 'D:\data\dataset_final_v1' -ArtifactsRoot 'D:\FortressArtifacts\training-v1'
```

`uv` должен быть установлен; если он вне PATH, передать `-UvPath 'D:\tools\uv.exe'`.
Для CPU допустим `-Device cpu`, но CUDA extra и CPU extra взаимоисключающие.
Setup выполняет `uv sync --locked --extra ml-cuda --group test --no-build`, включая
официальные torch 2.11.0+cu128 / torchvision 0.26.0+cu128 для Windows/Linux.
Существующие CPU-команды `uv sync --locked --extra ml ...` сохраняются.
Драйвер Windows должен поддерживать выбранный CUDA runtime; окончательный критерий —
реальный GRU forward/backward в `baseline preflight`, не наличие `nvidia-smi`.

Официальные источники: [PyTorch installation commands](https://pytorch.org/get-started/previous-versions/),
[MobileNetV3 weights](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.mobilenet_v3_small.html).
Pretrained state скачивается с `download.pytorch.org` только на этапе подготовки.
Publisher prefix `047dcff4` проверяется, полный SHA-256 сохраняется в `weights/weights_receipt.json`.
Cache/train не обращаются к интернету.

Результат setup:

- `weights/`: локальные IMAGENET1K_V1 веса и receipt полного SHA-256.
- `prepared/`: canonical manifest, индексы исходных PTS, сцены без выдуманной human review,
  расширенная draft taxonomy, canonical action proposals, исходные метки и readiness.
- `prepared/key_annotation_tasks.json`: очередь реальных эпизодов взятия ключа без придуманных bbox.
  `key` с нулевой поддержкой выключен для обучения детектора; на обучение вердикта это не влияет.
- `cache-three_crop/`: по одному numeric NPZ на видео, features[T,576] и исходные PTS; без pickle.
- `train_config.json`, `launch.json`, `START_TRAINING.cmd`: готовый запуск.

По умолчанию `video-views-v1`: полный кадр и два крупных квадратных кропа после исходного
поворота. В портретном видео это верх/низ; в горизонтальном — лево/право. Каждый получает
тот же letterbox224 и **тот же** frozen encoder; три вектора усредняются в576 признаков.
Дополнительных моделей нет. Режим и preprocessing входят в SHA кэша/checkpoint;
`-Views global` оставляет только полный кадр и создаёт отдельный `cache-global`.

Исходный пакет не изменяется. Сохраняются 32 train / 4 val / 4 internal holdout, exact duplicate aliases
не возвращаются в обучение, scenario families не пересекаются. Все source SHA проверяются до/после
подготовки и обучения; completion marker и SHA защищают кэш от частичной записи и случайной порчи.
Повтор setup переиспользует только полностью совпадающие артефакты. При изменении данных/настроек
выбрать новый `ArtifactsRoot`, сохранив прошлую generation.

Прежние 50 типов действий не переименовываются молча в 14 несвязанных классов.
Новые source meanings добавляются как draft candidates без выдуманного маршрута нормативного кейса.
`reviewed=true` из assistant package не становится human approval. Неизвестное остаётся unknown,
а отсутствие записи не становится negative. Для первого video classifier отрицательные примеры
дают именно видео с предоставленным вердиктом `no_violation`.

Четыре исходных расхождения user/organizer verdict сохраняются и перечисляются в readiness;
обучение следует явно заданным ранее пользовательским меткам. Это не независимая переоценка истинности.

## Запуск и восстановление

```powershell
& .\tools\train_first.ps1 -ArtifactsRoot 'D:\FortressArtifacts\training-v1'
```

Можно открыть `START_TRAINING.cmd` из каталога артефактов. Скрипт создаёт новый run-directory,
сохраняя прежние runs. Конфигурация: seed42, максимум80 epochs, batch4, AdamW3e-5,
weight_decay0.1, dropout0.6, gradient clipping1, ReduceLROnPlateau и early stopping patience20.
Веса энкодера заморожены; обучаются GRU и video head. Feature normalization считается **только по train**.
Loss взвешен по частотам video verdict в train. Наблюдённые val/test labels не попадают в optimizer.

Короткая проверка на реальных данных:

```powershell
& .\tools\train_first.ps1 -ArtifactsRoot 'D:\FortressArtifacts\training-v1' -RunName 'cuda-smoke' -StopAfterEpochs 2
```

После каждой эпохи атомарно сохраняется `last.pt` с optimizer/scheduler/RNG/sampler и history.
`best.pt` выбирается по dev balanced accuracy, затем macro-F1, затем меньшему BCE;
threshold подбирается только по dev. Scheduler использует dev BCE, early stopping — критерий выбора checkpoint.
Проверяются середины между соседними dev scores: фиксированная сетка0.01 способна пропустить
корректную границу близких вероятностей. Test scores в эту процедуру не входят.
Код тестирует равенство прерванного и непрерывного обучения. Возобновление:

```powershell
& .\tools\train_first.ps1 -ArtifactsRoot 'D:\FortressArtifacts\training-v1' -RunName 'continued' -Resume 'D:\FortressArtifacts\training-v1\cuda-smoke\last.pt'
```

Нужны тот же cache/config/runtime; суммарный epoch budget можно увеличить. Изменение dropout/lr/device
означает новый эксперимент. После уже сработавшего early stopping resume отвергается.
OOM/nonfinite loss дают ошибку и `failure.json`; последняя завершённая эпоха остаётся для resume.
Сначала проверить другие GPU-процессы и свободную RAM/VRAM. Уменьшение batch требует нового run.
Системные настройки Docker/WSL/HTTPS для этого локального обучения не нужны.

## Что означает 80%+

Смотреть accuracy, balanced accuracy и macro-F1 вердикта, а не accuracy на тренировочных кадрах.
Цель выполнена на конкретном наборе, когда **все три** метрики ≥0.80. Дисбаланс25/15 делает
одну accuracy недостаточной. Dev используется для выбора checkpoint и порога, его оценка оптимистична.
Полный `training_report.json` включает train/dev scores, memory, время и SHA checkpoint.

После завершения выбора модели выполнить один финальный прогон отложенных видео:

```powershell
.\.venv\Scripts\python.exe -m ml.cli baseline evaluate --cache 'D:\FortressArtifacts\training-v1\cache-three_crop' --checkpoint 'D:\FortressArtifacts\training-v1\RUN\best.pt' --output 'D:\FortressArtifacts\training-v1\RUN\internal_holdout.json' --device cuda
```

Либо `train_first.ps1 ... -EvaluateHoldout` для полного запуска; короткому smoke это запрещено.
Нельзя исправлять модель/порог по этому результату и продолжать называть набор независимым final.
При изменении подхода потребуется новый untouched набор.

Имеющиеся4 test-видео — внутренний holdout с той же камеры, а не ранее невиденные данные другого ракурса.
На4 видео одна ошибка даёт75%, поэтому 80%+ требует4/4. Даже4/4 имеет широкий Wilson95% интервал
и не подтверждает80% в новых условиях. Отчёт показывает этот интервал и всегда сохраняет
`independent_80_confirmed=false`, `production_ready=false` для текущего набора.
Жюри-тесты не использовать для обучения или подбора порогов. 80%+ первого запуска нельзя гарантировать
изменением кода; при недостижении сохранить реальные ошибки и дополнить независимые обучающие наблюдения.

Для event/rules release продолжать отдельный [TRAINING.md](TRAINING.md): проверенная temporal разметка,
явные отрицательные интервалы, независимые данные, события, источники и production compatibility.

## Фактически полученный результат 18 октября 2026

CUDA12.8/torch2.11.0 на RTX5060: подготовлены40 видео и2621 sampled source frames.
Development сравнил полный кадр, три представления и усиленную регуляризацию.
Набор test в выборе представлений/конфигурации/порога не участвовал. Выбранный вариант
остановился на21 эпохе, checkpoint эпохи1, threshold0.4643677920103073.

| Набор | Видео | Accuracy | Balanced accuracy | Macro-F1 |
| --- | ---: | ---: | ---: | ---: |
| Dev, использован для выбора | 4 | 1.00 | 1.00 | 1.00 |
| Internal holdout, один финальный прогон | 4 | 0.75 | 0.75 | 0.7333 |

На holdout получен один ложный сигнал, пропусков0; 95% Wilson interval accuracy≈[0.301,0.954].
**Цель80%+ на отложенных видео не достигнута.** Это не production-ready модель.
Checkpoint и отчёты сохранены локально вне Git. После этой оценки конфигурация и порог
не подстраивались по test. Для дальнейшего подтверждения улучшений нужен новый untouched набор,
включая другой ракурс. Исходные approximate action labels не заменяют полноценную разметку процедур.

Технический inference проверяется отдельной командой; он выдаёт только video prediction:

```powershell
$weights = Get-Content 'D:\FortressArtifacts\training-v1\weights\weights_receipt.json' -Raw | ConvertFrom-Json
.\.venv\Scripts\python.exe -m ml.cli baseline infer --video 'D:\samples\new.mov' --checkpoint 'D:\FortressArtifacts\training-v1\RUN\best.pt' --encoder-weights $weights.path --encoder-sha256 $weights.sha256 --device cuda
```

Score на заново декодированном тренировочном исходнике совпал с cached scoring.
Inference не выдаёт выдуманных событий, рамок, нормативов или независимой ML-приёмки.

Следующий разрешённый пользователем этап без новых исходников —
[SMALL_DATA.md](SMALL_DATA.md): аудит ошибок, grouped nested CV, оконная модель и
ограниченный fine-tuning. Он сохраняет исходный baseline и существующие test семьи;
его исследовательская оценка не заменяет независимый набор с другим ракурсом.
