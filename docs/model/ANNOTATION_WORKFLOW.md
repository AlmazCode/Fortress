# Локальная разметка и QA — D5

Этап подготавливает переносимые task bundles, canonical object JSON, action JSONL/interval CSV, COCO bbox exchange и проверки. Он не устанавливает CVAT/Label Studio и не подтверждает наличие локального annotation UI. Кадры и metadata остаются локальными; cloud annotation, face ID и звук не используются. Pseudo labels и пустые templates не gold.

## Подготовка bundle

Из корня checkout после D3/D4, с настраиваемыми sourceRoot/workRoot/manifestPath:

```powershell
.venv/Scripts/python.exe -m ml.data.annotation_tasks --manifest $manifestPath --index (Join-Path $workRoot 'index.json') --scenes (Join-Path $workRoot 'scenes.json') --frames (Join-Path $workRoot 'frames') --annotation-version local-labels-v1 --output-dir (Join-Path $workRoot 'annotation-tasks')
```

Команда проверяет manifest/split, PTS/scene context, hashes PNG и копирует только проверенные кадры в новый локальный bundle. В нём objects.json, actions.json, tasks.json, PNG и completion marker artifacts.json. Пустые objects/records и frame_review=unreviewed обозначают очередь ручной работы. Отсутствие записи не становится отрицанием. Повтор использует только проверенные завершённые bytes того же ключа; иной output не перезаписывается.

Objects.json хранит исходные decoded dimensions, source SHA/PTS, video/scene/split, taxonomy version и bbox_xyxy в original coordinates. artifact содержит фактический PNG path/hash/dimensions и crop/rotation transform. У каждого объекта есть visibility, occluded/truncated, nullable local track_id/actor_id, annotator/reviewer/review_status, human_approved и label_origin. Score модели не создаёт identity link.

## Обмен и координаты

API экспортирует export_coco(objects, taxonomy) → (coco, sidecar), импортирует import_coco(coco, sidecar, taxonomy, annotation_version=...). COCO использует image/category/annotation IDs, artifact-coordinate bbox=[x,y,width,height], area и iscrowd=0. Canonical original bbox преобразуется через D4 affine; за пределами видимого crop рамка отвергается, не обрезается молча. Roundtrip на 0/90/180/270 сохраняет source PTS, неизвестное, identities и review metadata в обязательном sidecar.

K objects view также использует фактические artifact dimensions/xywh; canonical original coordinates и inverse transform остаются в bundle/sidecar. K schema не расширяется неподдерживаемыми полями. Это позволяет правильно сопоставлять hash и dimensions реального PNG, сохраняя оригинальную геометрию для downstream.

Сверены bbox/area и IDs в [официальном COCO API](https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/coco.py). Поддержан bbox exchange; crowd labels не поддерживаются. Отсутствующий/повреждённый sidecar, дубли ID, иной source image/category, неверная площадь/границы дают отказ. Неизвестные annotation extras сохраняются в coco_extra, не используются как gold.

Новая/изменённая/удалённая COCO-разметка требует новой annotation_version. Новые/изменённые записи переводятся в imported/unreviewed с human_approved=false; удаление сбрасывает complete frame review. История содержит прежнюю версию/hash. Неизменённый roundtrip сохраняет review. QA вычисляет dataset_revision по manifest+object+action content: любое изменение labels создаёт новую версию составного dataset bundle, даже если исходные видео не менялись. Raw dataset_version отдельно идентифицирует source manifest.

Для действий write_actions/read_actions поддерживают canonical JSONL и interval CSV. JSONL начинается metadata header и содержит annotation records; CSV — metadata row, core columns annotation_id/video_id/scene_id/start_sec/end_sec/event_type и extra_json с прочими полями. Extra JSON не может переопределить core columns. Форматы сохраняют nullable identities, relations, unknown/review/visibility и версии без потерь; bounded read/count и exclusive write защищают импорт/выход.

## Интервалы и review

Action record содержит source SHA/split, scene interval [start_sec,end_sec), candidate event_type, state/known_mask, visibility/interval_complete и review evidence. Интервал положительной длины лежит внутри своей сцены. Разные действия могут пересекаться. Reviewed present и absent_verified одного класса/actor с пересечением отвергаются. Known actor/relation endpoints требуют явно проверенных local entity links; без них null/known=false.

present: различимая visible/partial положительная метка, human reviewer и approval. absent_verified дополнительно требует полного видимого интервала. unknown и unreviewed имеют known_mask=false. needs_review остаётся unknown с mask=false. Label_origin=pseudo не принимается как reviewed gold; после реального human review создаётся manual/imported запись с историей предложения. Никакого автоматического approval по confidence.

Frame review отдельно фиксирует полноту, reviewer и classes_reviewed. Пустой кадр не negative без complete human review. Затруднения разрешаются по исходным pixels/PTS и ANNOTATION_GUIDE.md; спор сохраняется needs_review. Изменение source/hash/split/taxonomy требует повторной проверки.

## QA и пределы готовности

quality_report валидирует split, классы, coordinates/PTS, review/masks, конфликтующие intervals, original hashes и PNG pixels/hashes при предоставленных source_root/asset_root. Отчёт включает per-class/per-case/per-video counts, small-box/occlusion/truncation, unknown rate, disagreements, duplicates, rights, source/artifact verification и dataset_revision. Small-side=16px — настраиваемая диагностическая группировка, не измеренный предел распознавания. Per-case counts не юридические вердикты: normative_status=unknown, применимость принадлежит R1.

Отдельны object_annotations_ready, temporal_annotations_ready, data_ready и training_ready. Реальная готовность требует original sources, подтверждённых прав/хэшей, reviewed taxonomy/scene/labels, покрытия активных видео и трёх partitions, human evidence независимого ранее не использованного final. Objects-only не открывает temporal gate. Данные synthetic всегда подтверждают только код. Отсутствующий review/independence/права остаётся явным ограничением; объёмы и точность не выдумываются. Training_ready здесь false: data QA не проверяет runtime/local encoder weights и не даёт поручения запускать обучение.

Проверенные API пригодны для unified data CLI следующего этапа D. До него реальные API/import/QA проверки выполнены pytest на tiny synthetic; отдельная bundle CLI воспроизведена. Production detector и temporal model не обучались.
