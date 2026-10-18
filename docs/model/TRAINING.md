# Передача ML-инструментов на другой локальный ПК

> Обновление 18 октября 2026: пользователь поручил подготовить реальный первый запуск.
> Новый [FIRST_TRAINING.md](FIRST_TRAINING.md) описывает готовый Windows/CUDA video-verdict baseline,
> import текущего annotation package, locked `ml-cuda`, cache и checkpoint/resume.
> Ниже сохранён отдельный строгий путь событийной модели; его human-review/independent/production
> требования не снимаются запуском video classifier. Старые наблюдения CPU-only относятся к прежнему окружению.

Исходная событийная поставка проверялась на tiny synthetic CPU. Её полное обучение,
fine-tuning и независимая оценка требуют отдельных reviewed данных. Новый video-verdict
baseline и разрешённый пользователем короткий real-data smoke описаны в FIRST_TRAINING.md.
Validated production release пока отсутствует; приложение сохраняет503 model_not_ready.

## 1. Checkout и окружение

На другом ПК получить проверенный интегрированный commit Fortress из AlmazCode/Fortress, сохранить SHA и проверить clean tree. Не подменять чужую working copy. Команды из корня отдельного checkout:

Для полного software набора нужен локальный FFmpeg/ffprobe: `uv sync` устанавливает Python-зависимости, но не эти executables. Проверить `ffprobe -version`; если он вне PATH, перед тестами задать `FORTRESS_TEST_FFPROBE` абсолютным путём. Backend/worker и финальная I требуют Linux; Windows ML checks используют явно описанную в CLI.md адаптацию только POSIX directory fsync/pipe polling.

```powershell
git remote get-url origin
git rev-parse HEAD
uv sync --locked --group test --extra ml --no-build
uv run --locked --group test --extra ml python -m ml.cli --help
uv run --locked --group test --extra ml python -m pytest tests/contracts/test_schemas.py tests/ml -q
```

Для последующих примеров активировать `.venv\Scripts\Activate.ps1` или указывать полный путь `.venv\Scripts\python.exe`. На Linux соответствующий путь `.venv/bin/python`. Python3.11 обязателен по общему pyproject. Исторический CPU runtime: Python3.11.14, torch2.14.1+cpu/torchvision0.29.1+cpu, NumPy2.4.6, PyAV17.1.0, Pillow12.3.0. CPU extra сохранён; новый CUDA extra зафиксирован отдельно в общем lock.

Полный software test suite включает backend video validation и требует локальный `ffprobe`:
если он вне PATH, задать `$env:FORTRESS_TEST_FFPROBE = 'D:\tools\ffprobe.exe'`.
`uv sync` не устанавливает system executable. Новый video-verdict baseline использует PyAV;
для его prepare/cache/train Docker и FFmpeg CLI не требуются.

Extra `ml` выбирает **CPU wheels** для Windows/Linux. Extra `ml-cuda` выбирает
torch2.11.0/torchvision0.26.0 с CUDA12.8; extras взаимоисключающие.
На RTX5060 проверяются GRU forward/backward и новый baseline cache/train workflow.
Это не подтверждает независимое качество или compatibility событийного production release.

```powershell
New-Item -ItemType Directory -Path D:\FortressArtifacts
python -m ml.cli preflight --project-root . --self-test --output D:\FortressArtifacts\preflight.json
python -m ml.cli smoke --output-dir D:\FortressArtifacts\tiny-v1
```

Preflight фиксирует actual RAM/VRAM/CUDA/device/runtime; CPU self-test не подтверждает CUDA. Smoke должен дать три generated sources, partition train/dev/final, optimizer1+resume2, dev thresholds, final diagnostics, measured export/import и unknown timeline. Ожидаются data_ready=false/trained=false/validated=false/production_ready=false. Сохранить stdout, exit code и SHA summary/package/model. Повторить на другом ПК — отдельная проверка, не выполненная здесь удалённо.

## 2. Подготовить данные до окон и обучения

Порядок и реализованные команды — [DATA.md](DATA.md). Папки originals/annotations/frames/clips/cache/releases держать вне Git; absolute paths настраиваются. ZIP импортировать только через bounded `data unpack`; scripts из архивов не выполнять. `data import` read-only проверяет source hashes/PTS/decode; corruption остаётся quarantine с причиной, originals сохраняются.

Grouped split назначить **до** кадров/окон. Один source/scene/duplicate component относится к одному partition. Первоначальный independent final выбирается один раз, затем D3 сохраняет его при любом повторном split; поздний перевод уже assigned train/dev в final отвергается. Ракурс/previously unseen final подтверждает человек, не имя каталога. Не создавать вымышленные30/10 или минимальный объём; проверять actual counts/source groups.

`data extract`/index/scenes/frames/clips извлекают actual source PTS; VFR нельзя заменять index/fps. Reviewed cuts передаются явно; raw inference не обнаруживает склейки автоматически. Baseline: RGB letterbox224,2fps,window32,stride16, coverage16с/span15.5с. Отдельные object crops/более частые кадры допустимы для annotation, но не заменяют raw global temporal pixels. Проверить rotation/crop inverse и совпадение source SHA.

Object/action/state taxonomies раздельны, append-only и versioned. Текущие project candidates — draft; неизвестные official IDs не выдумывать. `annotation_tasks.prepare_tasks` поддерживает несколько index/scenes pairs; tasks/objects/actions должны относиться к общему manifest. CLI `data tasks` создаёт bundle одной пары, API — нескольких. Для cache выбранного partition нужны все его pairs и общий task context всех annotated источников.

Разметка: [ANNOTATION_GUIDE.md](ANNOTATION_GUIDE.md), [ANNOTATION_WORKFLOW.md](ANNOTATION_WORKFLOW.md), [CASE_DATA_MAP.md](CASE_DATA_MAP.md). COCO export/import требует обязательный hash sidecar; edited/new/deleted labels сбрасывают review и получают новую annotation version. Canonical JSONL/CSV сохраняет source/time/reviewer/provenance/nullable identities. Автоматические proposals/pseudo labels не gold. Неизвестное не negative; actor-specific absence не глобальное отсутствие.

QA должен проверить original/image hashes, права, человеческую review taxonomies/scenes/labels, disagreements, explicit negatives, реальность данных и независимость final. Object frames без ordered temporal labels не дают GRU readiness. Пример independence evidence для `data report`/`cache --readiness-evidence` содержит actual manifest_sha256, reviewer, final_viewpoint_independent=true и previously_unseen=true **только после реальной проверки человеком**. Иначе сохранить false/unknown.

## 3. Локальные pretrained weights и cache

Для production baseline необходим заранее подготовленный локальный полный state_dict **MobileNet_V3_Small_Weights.IMAGENET1K_V1**. Его официальный источник указан установленным torchvision: `https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth`. Сетевое получение/передача выполняется отдельно до offline runtime; trainer/loader/cache сами ничего не скачивают. Здесь pretrained файл не загружался и положительная real-weights ветка не проверялась.

Получить доверенный полный SHA-256 файла из проверенной передачи, сверить `Get-FileHash`, затем передать `--encoder-weights/--encoder-sha256`. Prefix047dcff4 также сверяется с publisher filename, но prefix не заменяет доверенный полный SHA. Случайный encoder допускается только explicit test-only synthetic smoke. ImageNet classifier отбрасывается, остаются `.features`+spatial mean576, encoder/BatchNorm frozen.

Создать train/dev/final cache командами из [CLI.md](CLI.md). Входы всех partitions используют один полный manifest/canonical annotations/taxonomies/tasks/evidence. Повторить --index/--scenes для каждого источника partition. Cache заново вызывает data QA по текущим files/labels, сохраняет report и fingerprints в readiness_binding, хэш которого входит в config. Меняются source/dataset/split/annotation/taxonomy/encoder/preprocessing/config/windows/classes — создавать новую generation.

Numeric NPZ: features[T,576]FP32, targets[T,C]FP32, known/image/padding bool; без object pickle. Baseline loader читает проверенные arrays в RAM. Default limits: source≤2GiB, frame≤16777216 pixels, cache≤2GiB, windows≤2048/partition; это пределы кода, не измерение RAM/VRAM. Для большого набора сначала проверить actual memory на малом real cache, не обходить byte limits молча. Sources не удалять; real train перепроверяет raw source SHA до/после run.

## 4. Будущий train/resume после отдельного поручения

Ниже реализованные команды для будущего этапа; они **не запускались на реальных данных**. Требуются matching bound data_ready report, real non-test cache, локальные pretrained weights, проверенный runtime/hardware и отдельное поручение на обучение. Trainer отвергнет draft/synthetic/unbound readiness и train на dev/final.

```powershell
python -m ml.cli train --cache D:\cache\train-v1 --source-root D:\data\originals --encoder-weights D:\weights\mobilenet_v3_small-047dcff4.pth --encoder-sha256 FULL_TRUSTED_SHA256 --config ml/config/train.example.yaml --steps 100 --allow-real-training --output-dir D:\runs\run-100
python -m ml.cli resume --cache D:\cache\train-v1 --source-root D:\data\originals --encoder-weights D:\weights\mobilenet_v3_small-047dcff4.pth --encoder-sha256 FULL_TRUSTED_SHA256 --config ml/config/train.example.yaml --steps 200 --allow-real-training --resume D:\runs\run-100\checkpoint.pt --output-dir D:\runs\run-200
```

100/200 — пример общего optimizer budget, не рекомендация достаточного обучения и не epochs. Baseline: batch1 frozen features→causal GRU1×256→LinearC, masked BCEWithLogitsLoss, AdamW, gradient clipping. Unknown/padded/missing не supervised; all-unknown windows пропускаются без NaN. Scene state сбрасывается; overlapping windows агрегируются по actual PTS.

Config example — JSON-compatible YAML, CPU, seed42. CUDA device требует отдельно выбранного
`ml-cuda` runtime. Resume событийного trainer требует точный прежний cache/config/classes/runtime:
changing device/lr/seed/taxonomy создаёт новую несовместимую run. Сохраняются optimizer moments,
RNG и sampler order/cursor. Событийный trainer сохраняет checkpoint в конце run; новый
video-verdict trainer из FIRST_TRAINING.md сохраняет его после каждой эпохи.

OOM/NaN/decode/hash mismatch → failure, новая незавершённая generation не публикуется. Сохранить причину, проверить source/byte/RAM budgets и последнюю завершённую immutable generation. Увеличить disk/free-space, уменьшить будущий bounded step budget; менять batch/model/feature576 вне выбранной архитектуры нельзя молча. При изменении существенной config начать новую run; старый checkpoint хранить. Полный train не означает validated production model.

## 5. Dev calibration и independent final

После фиксации checkpoint получить scores dev, подобрать thresholds, затем один раз оценить untouched final — команды CLI.md. Любой другой checkpoint/taxonomy/split/annotation/protocol требует новой согласованной calibration/evaluation. Нельзя выбирать thresholds, tolerance или checkpoint по final quality.

Action sample metrics и reviewed verdict metrics раздельны. Для verdict accuracy/balanced accuracy/macro-F1 нужны реальные independent reviewed verdicts после rules workflow; action score не юридический вывод. Event precision/recall/F1 используют заранее фиксированный boundary tolerance0.5с с версией и reviewed comparable events, неизвестное не negative. Scores-only input не выдумывает truth events/verdicts. Все support/error/coverage/unknown counts должны сохраняться, undefined metrics остаются null.

Реальная цель≥0.80 на независимых видео здесь **not evaluated**. Synthetic метрики нельзя переносить в отчёт качества. Performance/latency/RAM/VRAM другого ПК тоже не измерены. Release review должен сопоставить actual data rights/review/independence, достаточность evaluation coverage и качество по кейсам; это последующий этап с человеком.

## 6. Export, безопасная передача и rollback

Smoke export/import/activation — CLI.md. Production export имеет дополнительный `--production --approval review.json`. Approval связывает checkpoint_sha256, metrics_sha256 (stable JSON content hash), taxonomy_sha256 и dataset_sha256; требует approved/reviewer/independence_verified/rights_verified/real_data_verified. Эти поля фиксируют проведённую проверку, не создают её. Actual independent verdict accuracy/balanced accuracy/macro-F1/all-known accuracy должны быть≥0.80; uncalibrated classes и synthetic provenance закрывают production gate. Normative rules applicability остаётся у R, model package хранит совместимую версию без автоматического юридического подтверждения.

Exporter всегда считает весь FP32 encoder+GRU+head, включая buffers/serialization, и все модели: limits12MB/35MB, без optimizer. Для двух smoke classes реально measured model.pt6385243 bytes, encoder tensors3756752 и GRU/head2564104; checkpoint с optimizer11543771 bytes. Это не замер неизвестной production taxonomy. В card/metrics сохранить реальные неизвестные, не подставлять ожидаемые показатели.

```powershell
Get-FileHash -Algorithm SHA256 D:\releases\release-v1\release.json
python -m ml.cli import --package D:\transfer\release-v1 --manifest-sha256 FULL_TRUSTED_MANIFEST_SHA256 --expected-taxonomy REVIEWED_TAXONOMY_VERSION --expected-rules VERIFIED_COMPATIBLE_RULES_VERSION --output-dir D:\installed\release-v1
python -m ml.cli activate --package D:\installed\release-v1 --manifest-sha256 FULL_TRUSTED_MANIFEST_SHA256 --expected-taxonomy REVIEWED_TAXONOMY_VERSION --expected-rules VERIFIED_COMPATIBLE_RULES_VERSION --pointer D:\installed\active.json
python -m ml.cli rollback --pointer D:\installed\active.json --expected-taxonomy REVIEWED_TAXONOMY_VERSION --expected-rules VERIFIED_COMPATIBLE_RULES_VERSION
```

Передавать каталог целиком; отдельно сверить manifest SHA по доверенному каналу и каждый artifact loader-ом. В K release — state_dict/config/backbone576/taxonomy/preprocessing/thresholds/card/metrics/dataset+split+annotations+rules versions/hashes. Strict loader принимает только локальный bounded tensor state (`weights_only=True`, mmap CPU), без pickle fallback/allowlist imports/downloads. Это не полная защита от DoS; неизвестный непроверенный checkpoint не импортировать как release.

Runtime compatibility сейчас строгая, включая torch/torchvision build descriptor; перенос GPU build→CPU build не заявлен проверенным. Другой ПК с тем же CPU lock — воспроизводимый software target, его actual прогон ещё требуется. Candidate сначала валидируется целиком, затем atomic pointer switch; прежняя directory остаётся для rollback. При ошибке new package старый snapshot/pointer сохраняется. Restart restore active не уничтожает previous.

## 7. Наблюдаемость и границы сдачи

CLI inference без отдельного подтверждённого visibility context сохраняет unknown для любых scores. Низкий score не означает absence; только explicit visible+complete interval может дать known negative. Partial visibility допускает predicted positive, actor_id=null и relations known=false. Интервалы не пересекают reviewed scene boundaries; raw port использует одну unreviewed scene. Дополнительный detector/views/face recognition/actor matching не добавлены.

Decode/OOM/deadline/inference failure возвращается как failed, coverage=none как insufficient evidence на уровне A/I, не no_violation. HTTP integration с backend, external HTTPS, Docker/GPU/offline deployment и реальная ML validation здесь не проверялись. Финальная E передача после интеграции I остаётся отдельной зависимостью. Собственные exact commits/реальные checks и gaps — [DEV-3](../github-plan/status/DEV-3.md).

Для проверки соответствия примеров актуальному CLI без чтения данных и без выполнения train/import: `python -m pytest tests/ml/test_cli_handoff.py -q`. Этот тест извлекает команды из TRAINING.md/CLI.md и останавливается после настоящего argparse; включая будущие real-training команды, он проверяет только flags/types/required arguments. Выполнение tiny pipeline и отрицательные release/holdout checks подтверждаются отдельно записанными проверками на точном SHA.
