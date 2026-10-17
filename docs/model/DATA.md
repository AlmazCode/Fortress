# Локальная подготовка данных — D

Единый entrypoint: python -m ml.data_cli. Команды inventory, import, split, index, scenes, frames, clips, tasks и taxonomy вызывают проверенные модули D1–D5. Команды unpack, extract, annotation-import, annotation-export, validate и report объединяют безопасный импорт, извлечение и QA. У каждой есть --help.

Все media/weights/артефакты остаются локально вне Git. Source root читается без изменения originals; output files/directories новые, существующие результаты не перезаписываются. Source/video/canonical/group IDs и SHA сохраняются. Исходный набор другого чата не импортировался и не делился во время code smoke.

## Что известно о материалах

DATA_INVENTORY.md — реальный D1 snapshot 17 октября 2026: 42 video files и 2621 image files доступны локально; это не 42 уникальных/валидных видео и не reviewed dataset. Исходный case предоставлен локально. TECHNICAL_SPEC.md, DATA_AND_TRAINING.md, CASE_COVERAGE.md не предоставлены в рабочем корне. В наличии K contracts и наши явно draft object/action/state taxonomies; official 25 IDs неизвестны.

DATA_READINESS.json — отдельно сохранённый наблюдённый отчёт **tiny synthetic code smoke**, не новый аудит тех 42 originals. В нём real data_missing=true относится только к synthetic manifest; это не утверждение, что локальные пользовательские видео исчезли. Нулевые annotation counts означают пустые templates, unknown_rate=null. Rights, человеческий review, independent final и production weights исходного набора всё ещё не подтверждены.

## Окружение и preflight

Python 3.11; зависимости из общего K lock:

```powershell
uv sync --locked --group test --extra ml --no-build
$python = '.venv/Scripts/python.exe'
& $python -m ml.data_cli inventory --project-root . --data-root $sourceRoot --annotation-root $annotationRoot --self-test --output (Join-Path $workRoot 'inventory.json')
```

sourceRoot/annotationRoot/workRoot — явно выбранные существующие локальные каталоги. При наличии исходного case добавить --case с его реальным путём; отсутствие параметра не подтверждает отсутствие case во всём компьютере. CLI печатает Python/PyTorch/Torchvision/CUDA/device и доступную RAM/VRAM; CPU self-test weights=None проверяет [1,3,224,224]→[1,576], без обучения/скачивания весов.

На целевом RTX 5060 8 ГБ / RAM16 / Ryzen5 8400 выполнить тот же preflight после подготовки согласованного CUDA runtime №1/№4. CPU lock сейчас не подтверждает CUDA или другое оборудование; VRAM unavailable остаётся unknown. Команды не требуют доступа к тому ПК сейчас. Full train/fine-tune/GPU search/реальная ML-оценка позже по отдельному поручению.

## ZIP, manifest и split до кадров

unpack использует bounded transactional ZIP handler; никакой код архива не выполняется. Traversal/absolute/drive/UNC/symlink/special files/case+Unicode collisions, file count, compressed/uncompressed bytes и compression ratio отвергаются до публикации output. ZIP64 и split archives не поддержаны. Плохой deflate/CRC откатывает staging; originals не меняются.

```powershell
& $python -m ml.data_cli unpack --input $archivePath --output-dir (Join-Path $workRoot 'unpacked')
& $python -m ml.data_cli import --config $configPath --output (Join-Path $workRoot 'import.json')
& $python -m ml.data_cli split --input (Join-Path $workRoot 'import.json') --seed 17 --final-video-id $finalId --output (Join-Path $workRoot 'split.json')
```

configPath следует ml/config/data.example.yaml: реальные relative paths, source/group IDs, provenance kind и явные rights. Template sources=[] не датасет. Missing/corrupt/unsupported media и decode budgets имеют quarantine reason в audit sidecar. Manifest=null при отсутствии valid videos; K manifest с пустыми videos не подделывается. Decode использует actual PTS, VFR/rotation; scripts/playlists/network inputs не исполняются.

Exact SHA и versioned near-candidate hashes не удаляют originals. Near similarity требует review и может пропускать edits/shifts; все transitive source/canonical/group/scene/SHA/candidate clusters сохраняются в одном partition. Component IDs закреплены в manifest.group_id. Split deterministic по seed+normalized content/config, без выдуманного 30/10.

finalId выбирается явно из initial manifest до использования final. Re-split без flag сохраняет весь existing final; иной seed/dev fraction его не перемещает. Изменение final selection после train/dev/final assignment отвергается до output. Ранее использованный train/dev нельзя назвать независимым новым flag. Новые duplicate edges через partitions дают отказ. Training selector выбирает только train, thresholds только dev_validation; final/jury данные исключены из настройки.

## Полный extract и task bundles

```powershell
$manifestPath = Join-Path $workRoot 'split.json'
$extractRoot = Join-Path $workRoot 'extract'
& $python -m ml.data_cli extract --manifest $manifestPath --source-root $sourceRoot --video-id $videoId --cut-sec 1.3 --rate 2 --crop 2 4 30 22 --output-dir $extractRoot
& $python -m ml.data_cli tasks --manifest $manifestPath --index (Join-Path $extractRoot 'index.json') --scenes (Join-Path $extractRoot 'scenes.json') --frames (Join-Path $extractRoot 'frames') --annotation-version local-labels-v1 --output-dir (Join-Path $workRoot 'tasks')
```

cut/crop выше воспроизведены на synthetic 32×24. Для своих данных выбрать проверенные границы/координаты либо убрать необязательные параметры. Один extract строит PTS index, explicit scenes, PNG и re-encoded FFV1/MKV clips в private staging и публикует общий completion marker только после успеха. Marker проверяет все вложенные bytes; corruption/изменение source/config или превышение bytes/disk/decode limits не возвращает готовый результат.

2fps,32 samples,stride16 = coverage16s/span15.5s/stride8s; padding/image/known masks различаются. Окна не пересекают known scene/split; unknown cuts требуют scene review. Crop/quarter-turn имеют inverse transform к original coordinates. Original source PTS не заменяется output clip PTS; Matroska quantization имеет явный tolerance0.0011s. Подробности в EXTRACTION.md.

Task bundle переносит проверенные PNG и objects.json/actions.json/tasks.json. Baseline context/PNG сохранять неизменными; labels редактировать в новых versioned файлах. Frame ID привязан к source PTS/SHA/geometry через anchors в tasks.json: labels не могут тихо переставить кадр во времени или заменить image hash. Legacy bundles без anchors нужно сформировать заново.

## Разметка, обмен и проверка

Human review, unknown, explicit negatives и disagreement — ANNOTATION_GUIDE.md/ANNOTATION_WORKFLOW.md. Empty/unlabeled не negative; pseudo не gold; actor/party/track IDs nullable. Новые/редактированные COCO labels требуют новой annotation_version и повторного human review. Dataset_revision меняется по manifest/labels/scenes/taxonomy content.

```powershell
$tasksRoot = Join-Path $workRoot 'tasks'
$contextPath = Join-Path $tasksRoot 'tasks.json'
& $python -m ml.data_cli annotation-export --manifest $manifestPath --context $contextPath --objects (Join-Path $tasksRoot 'objects.json') --format coco --output-dir (Join-Path $workRoot 'coco')
& $python -m ml.data_cli annotation-import --manifest $manifestPath --context $contextPath --input (Join-Path $workRoot 'coco/coco.json') --sidecar (Join-Path $workRoot 'coco/sidecar.json') --format coco --output (Join-Path $workRoot 'objects-roundtrip.json')
& $python -m ml.data_cli annotation-export --manifest $manifestPath --context $contextPath --actions (Join-Path $tasksRoot 'actions.json') --format jsonl --output (Join-Path $workRoot 'actions.jsonl')
& $python -m ml.data_cli annotation-import --manifest $manifestPath --context $contextPath --input (Join-Path $workRoot 'actions.jsonl') --format jsonl --output (Join-Path $workRoot 'actions-roundtrip.json')
```

CSV использует те же последние две команды с --format csv и новыми именами output. COCO labels/IDs/xywh/area работают в actual PNG coordinates; canonical source coordinates/PTS/review/unknown остаются в обязательном sidecar. Новые proposals unreviewed. Пример показывает unchanged roundtrip; при реальной правке COCO import добавить новую --annotation-version.

```powershell
& $python -m ml.data_cli validate --manifest $manifestPath --context $contextPath --objects (Join-Path $workRoot 'objects-roundtrip.json') --actions (Join-Path $workRoot 'actions-roundtrip.json') --asset-root $tasksRoot --source-root $sourceRoot
& $python -m ml.data_cli report --manifest $manifestPath --context $contextPath --objects (Join-Path $workRoot 'objects-roundtrip.json') --actions (Join-Path $workRoot 'actions-roundtrip.json') --asset-root $tasksRoot --source-root $sourceRoot --output (Join-Path $workRoot 'DATA_READINESS.json')
```

validate exit0 означает валидные форматы/ссылки/bytes; это не data_ready. --require-data-ready возвращает exit1 при закрытом gate. report успешно создаёт честный blocked report и не заявляет training. Повреждённый input/import отвергается без output; существующий output не перезаписывается.

tools_ready — доступность local data modules/taxonomies/schema, validation_passed — результат проверки данного набора. Отдельны real data presence, files vs reviewed annotations, object_annotations_ready, temporal_annotations_ready, data_ready и training_ready. Формальный K dataset_readiness содержится в contract. Actual source/PNG hash checks, права, reviewed taxonomies/scenes/labels, coverage активных видео и independent/unseen final evidence нужны для real data gate. Для human evidence report принимает --readiness-evidence JSON с manifest_sha256/reviewer/final_viewpoint_independent=true/previously_unseen=true; это явное утверждение проверяющего, не автоматическая проверка независимости.

Objects-only не GRU dataset, фото без PTS-порядка не становятся temporal sequence. QA counts не метрики модели или правовые выводы; R1 отдельно. Runtime preflight/local pretrained weights/release readiness проверяются следующими инструментами. DATA_READINESS текущего smoke сохраняет data_ready=false/training_ready=false; production без trained validated release отвечает model_not_ready/503.
