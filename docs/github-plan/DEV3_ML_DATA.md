# Разработчик №3 — ML / Данные

Свои задачи: D1, D2, D3, D4, D5, D, M1, M2, M3, M4, M, E.

## Как исполнять этот план через GitHub

Это перенос существующего плана, а не новый граф. ID, исполнители, files, acceptance и зависимости сохранены.
Последняя свежая сверка Aster недоступна из-за ошибки связи. Состояние задач здесь НЕ считается подтверждённым: сначала проверить имеющиеся ветки, коммиты и PR. Не повторять уже доказанную работу и не объявлять её готовой по старому снимку.

1. Каждый разработчик работает только в своей ветке и отдельном checkout/worktree. Номер направления постоянный; другие разработчики того же аккаунта могут работать параллельно. GitHub не запускает и не пробуждает чаты.
2. №1 владеет контрактом K, backend, общей интеграцией и финальной сдачей. №2 — frontend, №3 — ML/data, №4 — rules/infra. Общие файлы изменяет один заранее назначенный владелец.
3. K и O1 не имеют зависимостей. После проверенного K открываются соответствующие ветки; O1 может идти параллельно K. Затем выполнять только собственные задачи с закрытыми depends, а при блокере брать другую собственную готовую задачу.
4. Принятый prerequisite здесь означает проверенный результат в согласованной интеграционной ветке/PR с точным SHA. Открытый PR или локальный commit сами по себе не означают принятие. После интеграции брать актуальный контракт из Git, а не продолжать навечно от исходного initial commit.
5. Результаты передавать через обычные Git-коммиты и PR при действующем разрешении пользователя. Главный проверяет точные коммиты, объединяет совместимые изменения и выполняет финальные сквозные проверки. Защиту веток и требуемые проверки GitHub соблюдать.
6. Каждый редактирует только свой status/DEV-N.md: task ID, состояние, branch, commit/PR, реально запущенные проверки, блокер и следующее действие. Главный ведёт STATUS.md. Не давать четырём разработчикам одновременно менять один общий журнал.
7. Продолжать последовательно по своему направлению без вопроса на каждую задачу в пределах разрешённого запуска. Если ждёшь чужую работу, проверять Git/PR ограниченными интервалами в активном ходе; не изображать фоновое выполнение после остановки чата.
8. Ресёрч только для текущего обязательного пробела, с контрольной точкой после двух бесплодных заходов. Не добавлять карточки, не ослаблять acceptance и не заменять проверки формальным отчётом. Конфликты разрешать по контракту и фактическому коду, сохраняя чужие изменения.
9. Обучение модели остаётся на другом локальном ПК. Сейчас нужны CLI, tiny CPU smoke, инструкции и честный model_not_ready без весов. Не запускать полное обучение и не объявлять качество/производительность подтверждёнными без реальных данных.

### Что меняется относительно Aster

MCP-claim заменяется закреплённым разработчиком, веткой и собственным журналом. Aster accepted заменяется проверенной интеграцией точного Git-коммита. Heartbeat не нужен для разрешения работать через GitHub. Не вызывать Aster MCP ради регистрации, ожидания, смены статуса или сдачи в этом режиме.

Исходные описания ниже дословные и содержат исторические указания «сейчас только план», manual, MCP и запрет push/PR/merge. Экспорт сам по себе не даёт разрешения исполнять код или публиковать что-либо. После явного нового запуска пользователем административный порядок задаётся его текущей инструкцией и этим GitHub-процессом; продуктовые требования и acceptance сохраняются. Новая инструкция не отменяет ограничения на обучение, секреты, данные и внешнюю публикацию.

### D1 — Аудит данных и среды

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `ml/__init__.py`
- `ml/preflight.py`
- `tests/ml/test_preflight.py`
- `docs/model/MISSING_MATERIALS.md`
- `docs/model/DATA_INVENTORY.md`

Критерии приёмки:

- Для каждого материала указаны источник, path/hash, тип, доступность, права использования и неизвестное; отсутствующие приложения не выдумываются.
- Видео, фото, annotations и release учтены раздельно; фото без порядка не считаются temporal GRU выборкой.
- Preflight собирает Python3.11/PyTorch/Torchvision/CUDA/device/RAM/VRAM с реальным output; недоступный другой ПК не называется проверенным.
- CPU-only self-test на tiny fixture работает; full train/fine-tune/GPU search/dataset evaluation не запускаются.
- Отчёт различает tools_ready/data_missing/annotation_missing/hardware_unverified/license_unknown; training gate закрыт при отсутствии условий.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Инвентарь исходников/разметки/прав использования и CPU/GPU preflight CLI без обучения.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Инвентарь и preflight команды готовы. | noData: Нет видео/labels — data_missing, synthetic только code smoke. | imagesOnly: Только фото — object/frame dataset возможен, temporal training ждёт видео. | hardware: Нет CUDA/другого ПК — CPU smoke, hardware gate unverified. | license: Права данных неизвестны — не использовать для train, указать конкретный пробел.

</details>

### D2 — Классы и инструкция разметки

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `ml/data/taxonomy.py`
- `ml/config/object_taxonomy.draft.json`
- `ml/config/action_taxonomy.draft.json`
- `tests/ml/test_taxonomy.py`
- `docs/model/ANNOTATION_GUIDE.md`
- `docs/model/CASE_DATA_MAP.md`

Критерии приёмки:

- Кандидаты объектов: пачка денег, документ, ключ, печать, сумка, сосуд, хранилище, дверь, экран. Это draft по кейсам; неизвестные25 ID не придумываются.
- Для класса определены включения/исключения, похожие negatives, visibility/occlusion/truncation, small-object limits и unknown; ID append-only.
- Bbox объекта не равен действию или юридическому вердикту; action score не actor ID. Role/track/party links nullable/unknown без данных.
- Для C01–C15 записаны наблюдения, нужные объекты/интервалы/состояния и недоказуемое по видео. Нормативная применимость принадлежит R1.
- Гайд задаёт human review/disagreement resolution, explicit negatives vs unlabeled, сложные примеры и отдельный holdout. Псевдоразметка не gold.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Отдельные versioned taxonomies объектов, действий и состояний; гайд разметчика и связь с C01–C15.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Определения и гайд позволяют начать локальную разметку. | noCase: Нет исходного кейса — draft и gap report, не окончательный набор. | ambiguous: Не различимы объект/действие — unknown/needs_review. | architecture: Датасет объектов не означает готовый detector. Его обучение/интеграция — отдельный этап.

</details>

### D3 — Импорт и split без утечки

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `ml/data/__init__.py`
- `ml/data/manifest.py`
- `ml/data/splits.py`
- `ml/data/safe_archive.py`
- `ml/data/deduplicate.py`
- `ml/config/data.example.yaml`
- `tests/ml/test_manifest.py`
- `tests/ml/test_splits.py`
- `tests/ml/test_safe_archive.py`
- `tests/ml/test_deduplicate.py`

Критерии приёмки:

- ZIP traversal/absolute/symlink escape/zip bomb/лимит файлов отвергаются; вложенные scripts не выполняются, originals не меняются.
- Manifest содержит source/video IDs,SHA256,метаданные,доступность и quarantine reason. Битый источник не попадает в train молча.
- Exact duplicates и кандидаты near-duplicate имеют проверяемые clusters/config threshold; оригиналы автоматически не удаляются.
- Все сцены/кадры исходного видео и duplicate cluster находятся в одном partition. Split детерминирован seed+manifest; independent final не участвует в train/thresholds.
- 30/10 и минимальный объём не выдумываются. Нет источников/групп — data_not_ready; synthetic fixture хранится отдельно.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Read-only импорт, manifest/hashes, дубли и grouped split до формирования кадров/окон.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Versioned manifest/split без утечки source groups. | invalidArchive: Небезопасный архив отвергнут без скрытого частичного импорта. | corrupt: Источник quarantine с причиной, original сохранён. | leakage: Группы/дубли пересекают partitions — split invalid, train gate закрыт. | empty: Инструмент проверен на fixture; пустой manifest не объявляется реальным датасетом.

</details>

### D4 — Кадры и клипы по PTS

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: D3. Состояние: не сверено с Git.

Файлы:

- `ml/data/pts_index.py`
- `ml/data/scenes.py`
- `ml/data/extract_frames.py`
- `ml/data/extract_clips.py`
- `tests/ml/test_pts_index.py`
- `tests/ml/test_extraction.py`
- `docs/model/EXTRACTION.md`

Критерии приёмки:

- Кадр связан с video_id/scene_id/sourcePTS/time_base/origin offset/rotation/sourcehash;0-based время обратимо соответствует original.
- Частота configurable. Базовые2fps не гарантируют быстрые передачи/мелкие объекты; object frame export может иметь иную версионированную частоту.
- Temporal window:32 samples при2fps, шаг16 samples(8с), padding/known masks хвоста. Длительность покрытия окна16с и span между первым/последним sample различаются явно.
- Окно/клип не пересекает сцену/split; clipstart/decoded boundaries проверяются. VFR не index/fps, stream-copy seek по keyframe не называется точной нарезкой.
- Frame/clip/crop artifacts воспроизводимы по sourcehash+config и вне Git; bbox/crop сохраняет transform к original, crop не заменяет temporal sequence.
- Тесты покрывают VFR/rotation/nonzeroPTS/короткий/битый clip/re-run/диск и decode limits. Без исходников — только synthetic smoke.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: CLI извлечения сцен, кадров и клипов с source PTS и provenance для object/action datasets.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Кадры/клипы и mapping manifest готовы для разметки. | short: Хвост получает padding mask; неполный интервал не даёт false absence. | scene: Смена сцены разрывает окно/память. | missingPTS: Невосстановимое время — quarantine/unsupported, не вымышленные timecodes. | noData: CLI проверен на synthetic; реальные clips ждут originals.

</details>

### D5 — Разметка объектов и событий

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: D2, D4. Состояние: не сверено с Git.

Файлы:

- `ml/data/annotations.py`
- `ml/data/objects.py`
- `ml/data/coco_io.py`
- `ml/data/annotation_tasks.py`
- `ml/data/quality.py`
- `tests/ml/test_annotations.py`
- `tests/ml/test_objects_coco.py`
- `tests/ml/test_annotation_quality.py`
- `docs/model/ANNOTATION_WORKFLOW.md`

Критерии приёмки:

- Object record:video/scene/frame/sourcePTS,class_id,bbox_xyxy в original decoded coordinates,visibility/occluded/truncated,nullable track_id,annotator/reviewer/status/taxonomy version.
- COCO roundtrip проверяет image/category IDs,xyxy→xywh,границы/площадь и rotation/crop mapping. Temporal/unknown metadata сохраняется sidecar, а не теряется молча.
- Action record:video_id/scene_id/start_sec/end_sec/event_type,known/visibility и explicit negatives. Unlabeled не negative; независимые действия могут пересекаться.
- Гайд/taskbundle/import validators проверены на tiny fixture; совместимость COCO не означает установленный CVAT. Данные не отправляются в облачную разметку.
- QA показывает per-class/per-case/per-video coverage,small objects/occlusion/truncation,unknown rate,disagreement/duplicates/leakage/review status; достигнутые объём/точность не выдумываются.
- Без human-approved реальных labels data_ready=false; objects-only не GRU dataset. Псевдоразметка не gold, изменения labels версионируют dataset.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Локальные annotation bundles, canonical JSONL/interval CSV, COCO roundtrip и QA без выдуманного gold.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Annotation/COCO/QA инструменты готовы; dataset_ready только по реальным reviewed labels. | noLabels: Есть кадры без labels — annotation_missing и очередь ручной разметки. | badLabels: Неверные bbox/time/class/split — validation failure, train gate закрыт. | objectsOnly: Object annotation ready; temporal gate остаётся закрыт. | disagreement: Расхождения — needs_review, не автоматический gold. | toolAbsent: Нет локального annotation UI — bundles/validators доступны, ручная разметка отложена.

</details>

### D — Данные и preflight

Разработчик: №3. Тип: code. Фаза: integration.
Зависимости: D1, D5. Состояние: не сверено с Git.

Файлы:

- `ml/__init__.py`
- `ml/data/__init__.py`
- `ml/data/manifest.py`
- `ml/data/annotations.py`
- `ml/data/splits.py`
- `ml/data/safe_archive.py`
- `ml/data/pts_index.py`
- `ml/preflight.py`
- `ml/config/data.example.yaml`
- `tests/ml/test_manifest.py`
- `tests/ml/test_annotations.py`
- `tests/ml/test_splits.py`
- `tests/ml/test_safe_archive.py`
- `tests/ml/test_preflight.py`
- `docs/model/DATA.md`
- `docs/model/MISSING_MATERIALS.md`
- `docs/model/DATA_INVENTORY.md`
- `ml/data/taxonomy.py`
- `ml/config/object_taxonomy.draft.json`
- `ml/config/action_taxonomy.draft.json`
- `tests/ml/test_taxonomy.py`
- `docs/model/ANNOTATION_GUIDE.md`
- `docs/model/CASE_DATA_MAP.md`
- `ml/data/deduplicate.py`
- `tests/ml/test_deduplicate.py`
- `ml/data/scenes.py`
- `ml/data/extract_frames.py`
- `ml/data/extract_clips.py`
- `tests/ml/test_pts_index.py`
- `tests/ml/test_extraction.py`
- `docs/model/EXTRACTION.md`
- `ml/data/objects.py`
- `ml/data/coco_io.py`
- `ml/data/annotation_tasks.py`
- `ml/data/quality.py`
- `tests/ml/test_objects_coco.py`
- `tests/ml/test_annotation_quality.py`
- `docs/model/ANNOTATION_WORKFLOW.md`
- `ml/data_cli.py`
- `docs/model/DATA_READINESS.json`
- `tests/ml/test_data_pipeline.py`

Критерии приёмки:

- Аудит отмечает фактическое наличие/отсутствие TECHNICAL_SPEC.md, DATA_AND_TRAINING.md, CASE_COVERAGE.md, исходного кейса, контрактов, taxonomy, видео и аннотаций. Для текущего чистого base с одним README приложения считаются отсутствующими; старые результаты не выдумываются.
- Manifest CLI формирует SHA-256,video_id/scene_id,медиаметаданные и provenance без изменения оригиналов; validators ловят повреждения, дубли и неподходящие медиа; большие данные остаются вне Git.
- ZIP обработчик тестируется на traversal, absolute/symlink escape и превышение распакованного размера/количества; ничего из архива не выполняется.
- Аннотации video_id,scene_id,start_sec,end_sec,event_type валидируются с visibility,unknown и explicit negatives. Не размеченное не трактуется как negative; фотографии без временного порядка не выдаются за GRU sequence.
- Split строится по исходным видео/сценам, без пересечения групп и дублей train/dev/final. Финальные независимые видео другого ракурса не используются для подбора thresholds; старое 30/10 не фиксируется без manifest.
- PTS index сохраняет исходное время,VFR/rotation и scene boundaries; тесты на tiny synthetic clips проверяют порядок/диапазоны и masks, без утверждения предметного качества.
- Preflight CLI печатает Python/PyTorch/Torchvision/CUDA/device/доступную RAM/VRAM и проверяет 576 feature shape; CPU-only режим работает. Команда для RTX 5060 8 ГБ/RAM16/Ryzen5 8400 документирована, наличие этого оборудования и совместимость CUDA локально не выдумываются.
- Выполнен только короткий CPU smoke validators на synthetic fixture; GPU train/fine-tune/подбор и датасетная оценка не запускаются. DATA.md/MISSING_MATERIALS.md различают проверенное, неизвестное и внешние зависимости.
- Проверен единый CLI import/split/extract/annotation-import/validate/report. Отдельные readiness поля для tools/object annotations/temporal annotations/training, с reasons и evidence; отсутствие реальных данных не считается готовым датасетом.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: собранные D1–D5 и единый data preparation CLI: inventory→safe import/dedup/group split→PTS/scenes/frame/clip export→object/action annotation import→QA/readiness. Документировать команды в DATA.md и отдельный data readiness report. Tools ready, object dataset ready и temporal dataset ready — разные состояния. Без оригиналов/labels инструменты проверяются tiny synthetic, а реальные gates остаются закрыты.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Все инструменты подготовки проверены, readiness report воспроизводим. | noData: Tools ready/data_missing — UI/API и ML tooling могут продолжаться; реальные clips/dataset не существуют. | objectsOnly: Object annotation ready, temporal dataset ещё not_ready. | invalid: Leakage/bad labels/missing human review — training gate закрыт, исправить D2–D5. | readyData: Только реальные reviewed видео/labels и valid split позволяют data_ready; полный train всё равно отдельное поручение.

</details>

### M1 — Preprocessing и кэш

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: D. Состояние: не сверено с Git.

Файлы:

- `ml/preprocessing.py`
- `ml/windows.py`
- `ml/cache.py`
- `tests/ml/test_pts_preprocessing.py`
- `tests/ml/test_cache_resume.py`
- `docs/model/PREPROCESSING.md`

Критерии приёмки:

- Letterbox 224, ImageNet normalization, порядок каналов и masks совпадают в train/inference; размеры, rotation и inverse transform проверены.
- Окна имеют исходные timestamps, scene/split IDs и padding/known masks; объединение перекрытий не смешивает сцены и partitions.
- Ключ кэша включает source/dataset/split/annotation/taxonomy/encoder/preprocessing/config hashes. Смена любого значимого входа инвалидирует кэш.
- Прерванная запись не создаёт valid cache marker; resume не принимает повреждённый или чужой кэш. Paths и объём настраиваемы, данные вне Git.
- CPU tiny fixture подтверждает детерминизм и invalidation; реальный feature cache без исходников и pretrained local weights не объявляется построенным.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: единый train/inference preprocessing и воспроизводимый кэш последовательностей с полным происхождением.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Единый preprocessing и проверяемый cache готовы для M2. | changedInput: Версия/хэш изменились — пересчитать затронутый кэш, не использовать старый marker. | interrupted: Неполная запись — восстановить из source manifest, не принять за готовую. | dataMissing: Code smoke возможен; cache_ready=false до реальных данных и локальных weights.

</details>

### M2 — GRU и CPU train/resume

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: M1. Состояние: не сверено с Git.

Файлы:

- `ml/models/__init__.py`
- `ml/models/encoder.py`
- `ml/models/temporal.py`
- `ml/train.py`
- `tests/ml/test_shapes_masks.py`
- `tests/ml/test_training_resume.py`

Критерии приёмки:

- Shape assertions: [B,T,3,224,224]→[B,T,576]→[B,T,C]; ImageNet classifier удалён, production encoder IMAGENET1K_V1 загружается из локального подготовленного пути без runtime download.
- Frozen encoder baseline, AdamW и BCEWithLogitsLoss учитывают unknown/padding masks; неизвестные labels не отрицательные.
- Scene reset и состояния последовательности проверены; action score не является actor ID. Дополнительные views/backbone/object detector не вводятся.
- Короткий CPU smoke на tiny synthetic data проверяет loss/gradient/checkpoint/resume, seed/config/runtime metadata и согласованность после возобновления.
- Random-init smoke weights имеют test-only provenance и не могут активировать production readiness. Полный train, fine-tuning, GPU search и оценка реального датасета не выполняются.
- Окно, где все labels неизвестны/padded, корректно пропускается или маскируется без NaN/деления на ноль; тест не превращает его в negative example.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: MobileNetV3-Small features + pooling → 576 → GRU 1×256 → Linear и работоспособный ограниченный CPU train/resume.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Код модели и CLI train/resume работает на CPU fixture. | mismatch: Несовместимые shape/config/taxonomy — отказ resume с причиной. | oom: Smoke OOM/NaN/invalid loss — blocked, исправить размер tiny fixture/код; не объявлять train успешным. | futureTraining: Реальное обучение ждёт отдельного поручения, готовых данных и другого локального ПК.

</details>

### M3 — Оценка и экспорт пакета

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: M2. Состояние: не сверено с Git.

Файлы:

- `ml/evaluate.py`
- `ml/thresholds.py`
- `ml/export.py`
- `ml/config/train.example.yaml`
- `ml/config/release.example.json`
- `tests/ml/test_evaluation_export.py`
- `tests/ml/test_export_format.py`

Критерии приёмки:

- Evaluator считает verdict accuracy, balanced accuracy, macro-F1, support/FP/FN/coverage/unknown/абсолютные ошибки; события — precision/recall/F1 по заранее фиксированному tolerance, базово 0,5 с с версией.
- Thresholds подбираются только на dev; train/dev/final groups не пересекаются, final другого ракурса не используется для обучения или настройки.
- Release включает state_dict/config/backbone/576/taxonomy/preprocessing/thresholds/model card/metrics/dataset+split+annotation+rules versions и hashes. Новый release не затирает предыдущий.
- Измеряется весь FP32 encoder+GRU+head ≤12 МБ и все модели ≤35 МБ без optimizer; encoder/head/training checkpoint и единицы отдельно. Smoke taxonomy не подтверждает бюджет неизвестной production taxonomy.
- CPU fixture проверяет вычисления и export format; реальные цели ≥0,80 и performance остаются not evaluated. Ни один smoke metric не публикуется как качество реальной модели.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: реализованные evaluator/calibration/export CLI и неизменяемый release со всеми версиями и SHA-256.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: CLI оценки/thresholds/export готов и проверен на synthetic. | leakage: Final использован в настройке или split пересекается — оценка invalid, training/validation gate закрыт. | overBudget: Реальный экспорт превысил бюджет — честный failure/ограничение, не исключать encoder из подсчёта. | noWeights: Production release отсутствует, модель not trained/not validated; current software delivery возможна с503.

</details>

### M4 — Loader и inference adapter

Разработчик: №3. Тип: code. Фаза: implementation.
Зависимости: M3. Состояние: не сверено с Git.

Файлы:

- `ml/release.py`
- `ml/inference.py`
- `ml/intervals.py`
- `tests/ml/test_release_loader.py`
- `tests/ml/test_inference_timeline.py`

Критерии приёмки:

- Loader валидирует manifest/hashes, версии, architecture/576/shapes/taxonomy/thresholds/preprocessing/rules и обязательные metadata; произвольный best.pt не принимается.
- Загружается tensor state_dict с явным weights_only=True и ограничениями размера/структуры; нет автоматического weights_only=False, произвольных allowlist imports или выполнения checkpoint-кода. weights_only не считается защитой от всех DoS.
- Untrained/test-only/неполный/повреждённый/несовместимый пакет даёт model_not_ready, без случайных предсказаний и runtime скачивания весов.
- Inference объединяет overlapping scores по исходному времени, учитывает masks/scene reset, выдаёт интервалы, visibility и unknown relations через K.
- Локальное переключение release атомарно, прежний работоспособный пакет доступен для отката. CPU fixture проверяет код, но не ML качество; production не активируется synthetic release.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: строгая локальная загрузка release, ActionTimeline и безопасные отказы до production анализа.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Совместимый подтверждённый release может быть загружен после отдельного обучения/передачи. | missing: Нет пакета — model_not_ready/503 через backend. | invalid: Hash/version/shape/test-only mismatch — отказ с причиной и сохранение прежнего пакета. | failure: OOM/decode/inference exception — failed с причиной, не no_violation. | uncertain: Непроверенная наблюдаемость/actors остаются unknown в timeline.

</details>

### M — ML CLI и загрузка release

Разработчик: №3. Тип: code. Фаза: integration.
Зависимости: M4. Состояние: не сверено с Git.

Файлы:

- `ml/cli.py`
- `ml/models/__init__.py`
- `ml/models/encoder.py`
- `ml/models/temporal.py`
- `ml/preprocessing.py`
- `ml/windows.py`
- `ml/cache.py`
- `ml/train.py`
- `ml/evaluate.py`
- `ml/thresholds.py`
- `ml/export.py`
- `ml/release.py`
- `ml/inference.py`
- `ml/intervals.py`
- `ml/config/train.example.yaml`
- `ml/config/release.example.json`
- `tests/ml/test_shapes_masks.py`
- `tests/ml/test_pts_preprocessing.py`
- `tests/ml/test_cache_resume.py`
- `tests/ml/test_tiny_pipeline.py`
- `tests/ml/test_release_loader.py`
- `docs/model/TRAINING.md`
- `docs/model/CLI.md`
- `docs/model/PREPROCESSING.md`
- `tests/ml/test_training_resume.py`
- `tests/ml/test_evaluation_export.py`
- `tests/ml/test_export_format.py`
- `tests/ml/test_inference_timeline.py`

Критерии приёмки:

- Shape tests подтверждают [B,T,3,224,224]→[B,T,576]→[B,T,C], feature_dim assertion=576; базово letterbox224,2 fps,window32,overlap50%,GRU1×256. Train/inference используют одну версию preprocessing/normalization; four-view тензор автоматически не вводится.
- Masked BCEWithLogitsLoss не учитывает unknown labels и padded frames; scene reset обнуляет temporal state, overlapping windows агрегируются по исходным PTS с masks. Frame preprocessing, padding, unknown и scene boundaries покрыты targeted tests.
- Реальные CLI cache/train/resume/evaluate/thresholds/export работают на tiny synthetic CPU fixture: frozen encoder+GRU baseline, AdamW, checkpoint/resume,seed/config/runtime metadata. Полный train/fine-tuning/GPU search/оценка реального датасета не запускаются; случайные smoke weights помечены test-only и отвергаются production loader.
- Кэш инвалидируется при смене dataset/encoder/preprocessing версии и хэшей; resume проверяет совместимость конфигурации. Пороги выбираются только на dev, final split заблокирован от обучения/подбора.
- Evaluator реализует accuracy,balanced accuracy,macro-F1 verdict, support/FP/FN/coverage/unknown/числа ошибок и event precision/recall/F1 с конфигурируемым заранее записанным временным допуском; реальная цель ≥0,80 на независимых видео остаётся not evaluated, метрики не выдумываются.
- Release неизменяем и включает checkpoint/config/backbone/576/taxonomy/preprocessing/thresholds/metrics/model card/dataset+split+annotation+rules versions/SHA-256 manifest. Классы append-only, unconfirmed predictions не gold; новые release не затирают старые.
- Loader отвергает случайный best.pt, untrained/test package, hash mismatch, неизвестные/несовместимые taxonomy/preprocessing/rules версии и недостающие файлы; загрузка локальная и безопасная без выполнения произвольного checkpoint-кода. Отсутствие validated usable release даёт model_not_ready, не synthetic predictions.
- Бюджеты экспорта измеряются как весь MobileNetV3-Small+GRU+head ≤12 МБ FP32 и все модели ≤35 МБ без optimizer; encoder/head/training checkpoint отражены отдельно с явными единицами. На synthetic taxonomy измеряется только smoke variant; фактический budget production taxonomy и latency/VRAM/RAM не объявляются подтверждёнными.
- docs/model/TRAINING.md содержит проверенные реализованными CLI команды установки другого локального ПК,CUDA preflight,manifest/annotations/split/cache/train+resume/evaluate/thresholds/export/SHA-256/переноса/импорта/отката и smoke; пример config,OOM/recovery,настраиваемые пути,ресурсы и ограничения. Доступ к тому ПК не prerequisite текущей сдачи.
- CLI и TRAINING.md включают реальную нарезку по sourcePTS, object/temporal annotation workflow, COCO exchange и training-readiness validation. Отдельный object detector не обучается и не подменяет выбранный MobileNet+GRU.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: собранные M1–M4 и реальные CLI cache/train/resume/evaluate/thresholds/export/import. ml/cli.py, CLI.md и TRAINING.md дают другому локальному ПК точные команды подготовки данных/окружения, CUDA preflight, annotation QA, обучение/оценку, export/hash/import и rollback. Проверяется только короткий CPU tiny pipeline; полное обучение/fine-tune/GPU search/реальная ML-оценка отложены.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: CPU pipeline и handoff работают, production пока not trained/not validated. | missing: Нет real data/pretrained local weights/другого ПК — условие будущего этапа, не выдуманный success. | failure: Smoke/loader/schema/CLI regression — blocked до исправления M1–M4. | future: Отдельное разрешение+данные+hardware→train/evaluate/export→import; до этого503.

</details>

### E — Передача ML-инструментов

Разработчик: №3. Тип: test. Фаза: verification.
Зависимости: I. Состояние: не сверено с Git.
Исходный helperFor: Z. Это существующая задача №3; новый чат не обязателен, если пользователь не разрешил дочерние чаты.

Файлы:

- `ml/__init__.py`
- `ml/data/__init__.py`
- `ml/data/manifest.py`
- `ml/data/annotations.py`
- `ml/data/splits.py`
- `ml/data/safe_archive.py`
- `ml/data/pts_index.py`
- `ml/preflight.py`
- `ml/config/data.example.yaml`
- `tests/ml/test_manifest.py`
- `tests/ml/test_annotations.py`
- `tests/ml/test_splits.py`
- `tests/ml/test_safe_archive.py`
- `tests/ml/test_preflight.py`
- `docs/model/DATA.md`
- `docs/model/MISSING_MATERIALS.md`
- `ml/cli.py`
- `ml/models/__init__.py`
- `ml/models/encoder.py`
- `ml/models/temporal.py`
- `ml/preprocessing.py`
- `ml/windows.py`
- `ml/cache.py`
- `ml/train.py`
- `ml/evaluate.py`
- `ml/thresholds.py`
- `ml/export.py`
- `ml/release.py`
- `ml/inference.py`
- `ml/intervals.py`
- `ml/config/train.example.yaml`
- `ml/config/release.example.json`
- `tests/ml/test_shapes_masks.py`
- `tests/ml/test_pts_preprocessing.py`
- `tests/ml/test_cache_resume.py`
- `tests/ml/test_tiny_pipeline.py`
- `tests/ml/test_release_loader.py`
- `docs/model/TRAINING.md`
- `docs/model/CLI.md`
- `tests/ml/test_cli_handoff.py`
- `tests/ml/test_release_compatibility.py`
- `tests/ml/test_export_budgets.py`
- `docs/model/EVALUATION.md`
- `docs/model/MODEL_CARD.template.md`
- `docs/model/HANDOFF.md`
- `docs/model/ACCEPTANCE.json`
- `docs/model/DATA_INVENTORY.md`
- `ml/data/taxonomy.py`
- `ml/config/object_taxonomy.draft.json`
- `ml/config/action_taxonomy.draft.json`
- `tests/ml/test_taxonomy.py`
- `docs/model/ANNOTATION_GUIDE.md`
- `docs/model/CASE_DATA_MAP.md`
- `ml/data/deduplicate.py`
- `tests/ml/test_deduplicate.py`
- `ml/data/scenes.py`
- `ml/data/extract_frames.py`
- `ml/data/extract_clips.py`
- `tests/ml/test_pts_index.py`
- `tests/ml/test_extraction.py`
- `docs/model/EXTRACTION.md`
- `ml/data/objects.py`
- `ml/data/coco_io.py`
- `ml/data/annotation_tasks.py`
- `ml/data/quality.py`
- `tests/ml/test_objects_coco.py`
- `tests/ml/test_annotation_quality.py`
- `docs/model/ANNOTATION_WORKFLOW.md`
- `ml/data_cli.py`
- `docs/model/DATA_READINESS.json`
- `tests/ml/test_data_pipeline.py`
- `docs/model/PREPROCESSING.md`
- `tests/ml/test_training_resume.py`
- `tests/ml/test_evaluation_export.py`
- `tests/ml/test_export_format.py`
- `tests/ml/test_inference_timeline.py`

Критерии приёмки:

- Все команды TRAINING.md/CLI.md --help и короткий CPU путь manifest→validation→split→PTS/windows→cache→train/resume→evaluate→thresholds→export→hash→test import воспроизведены на tiny synthetic data; команды и точный commit записаны.
- Пример конфигурации и release schema валидны; hashes/backbone/576/taxonomy/preprocessing/thresholds/dataset+split+rules versions проверяются loader. Неполный,повреждённый,несовместимый,untrained/test release production не загружает.
- Инструкция другого ПК включает Python3.11/CUDA preflight,ресурсы,настраиваемые paths,данные/аннотации/групповой split,seed/версии,OOM/resume/откат,локальный перенос и проверку SHA-256; не содержит требований дать доступ к тому ПК сейчас.
- EVALUATION.md заранее фиксирует event tolerance (базовое обратимое значение 0,5 с с версией, до любых реальных оценок), независимый video/scene split другого ракурса и цели verdict accuracy/balanced accuracy/macro-F1 ≥0,80; support/FP/FN/coverage/unknown/числа ошибок и event P/R/F1 обязательны.
- MODEL_CARD.template явно not trained/not validated без выдуманных цифр; отсутствующий реальный dataset/taxonomy,исходные приложения,нормативные материалы и весь последующий training/evaluation перечислены.
- Команда измерения всего FP32 export проверена на smoke taxonomy с явными единицами и отдельными encoder/head/checkpoint; цели≤12МБ основной комплект/≤35МБ все модели и production-taxonomy budget пока не заявлены достигнутыми.
- Не запускались полный train/fine-tune/GPU search и реальная датасетная ML-оценка. Отчёт передаёт только наблюдённую программную готовность и конкретные ограничения; manual review сохраняется.
- Воспроизведены extraction/COCO import-export/annotation QA/split leak checks на tiny synthetic; исходные frames/clip provenance сохранены. Objects-only/data_missing/annotation_missing не активируют temporal training gate.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: проверенная передача всех data/annotation/ML инструментов другого локального ПК: CLI, object COCO roundtrip, temporal labels/split/windows, preprocessing/cache/model/train-resume/evaluation/export/import, readiness gates и документация. CPU tiny fixture подтверждает код, не датасет/обучение/качество. Образец model card содержит реальные неизвестные, а не выдуманные metrics.
Исполнитель №3. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Инструменты/команды/форматы переданы и воспроизведены на CPU tiny. | noDataset: Реальные объекты/temporal labels не предоставлены — readiness=false, без выдуманного датасета. | future: Full training/independent ML evaluation/production size budget отложены. | failure: Инструкция не соответствует CLI/format или leakage — blocked до исправления D/M.

</details>
