# Локальный data/ML CLI

Запускать из корня Fortress в Python3.11 с ML extra из общего lock. Все пути конфигурируемы; результаты/веса/видео хранить вне Git. Общая точка входа — `python -m ml.cli`. `--help` каждой команды показывает реализованные аргументы.

| Команда | Результат |
| --- | --- |
| `data` | D CLI: inventory/import/split/index/scenes/frames/clips/tasks/taxonomy/unpack/extract/annotation-import/annotation-export/validate/report |
| `preflight` | Инвентарь/runtime/CPU self-test; отдельно от data readiness |
| `cache` | Raw PTS → shared preprocessing → frozen features576, masks и заново проверенный QA binding |
| `train` | Frozen encoder + AdamW GRU/head, immutable checkpoint/report |
| `resume` | Тот же train, обязательный `--resume`; steps означает общее число шагов |
| `evaluate` | Scores из cache/checkpoint либо метрики supplied evaluation input |
| `thresholds` | Versioned grid только dev_validation; без positives/negatives — null |
| `export` | Полный FP32 model package, hashes/versions/card/metrics и реальные размеры |
| `import` | Проверенная immutable локальная копия package; production требует доверенный manifest SHA |
| `activate` | Проверка candidate → atomic pointer/snapshot, previous остаётся доступен |
| `rollback` | Повторная проверка previous и atomic switch |
| `infer` | Local raw-video PTS → K timeline; default visibility unknown |
| `smoke` | Три generated tiny видео, CPU train1+resume2, dev/final/export/import/inference, все readiness gates false |

Общий source workflow и точные D команды: [DATA.md](DATA.md), [EXTRACTION.md](EXTRACTION.md), [ANNOTATION_WORKFLOW.md](ANNOTATION_WORKFLOW.md). Baseline preprocessing/cache: [PREPROCESSING.md](PREPROCESSING.md). Подготовка другого ПК и будущий запуск: [TRAINING.md](TRAINING.md).

## Воспроизводимый CPU smoke

PowerShell, папка назначения ещё не существует:

```powershell
$mlOutput = 'D:\FortressArtifacts\tiny-v1'
python -m ml.cli smoke --output-dir $mlOutput
```

Parent directory должна существовать. Никаких пользовательских видео не требуется. Создаются только synthetic32×24 FFV1/MKV с nonzero/VFR PTS и искусственные labels. Поля simulated review нужны для проверки формата; это не human gold или доказательство bank events.

`summary.json` содержит steps=2/resumed=true, calibration_partition=dev_validation, evaluation_partition=independent_test, data_ready=false/trained=false/validated=false/production_ready=false. `verdict_metrics=null`, timeline coverage=none без отдельного visibility context. В `DATA_READINESS.json` сохранены конкретные gaps. Все bytes защищены completion marker; точный повтор проверяет старую generation. Порча/другая конфигурация требует нового output-dir.

## Cache

```powershell
python -m ml.cli cache --manifest D:\data\manifest.split.json --source-root D:\data\originals --tasks D:\data\tasks\tasks.json --objects D:\data\objects.reviewed.json --actions D:\data\actions.reviewed.json --asset-root D:\data\tasks --object-taxonomy D:\data\objects.taxonomy.json --action-taxonomy D:\data\actions.taxonomy.json --index D:\data\v1\index.json --scenes D:\data\v1\scenes.json --partition train --encoder-weights D:\weights\mobilenet_v3_small-047dcff4.pth --encoder-sha256 FULL_TRUSTED_SHA256 --readiness-evidence D:\data\independence.json --output-dir D:\cache\train-v1
```

Повторять `--index`/`--scenes` парами для **каждого** видео выбранного partition. Для dev/final использовать их пары, те же manifest/полные canonical actions/taxonomies/tasks/objects/evidence и class order. QA пересчитывается по всем данным, actual original/image hashes; его content revision и исходные SHA входят в cache configuration. Выход `cache.json.readiness_binding.report` — фактический отчёт, а не флаг пользователя.

`--class action.id` можно повторять: только упорядоченное подмножество существующей taxonomy. Полная разметка проверяется и хэшируется до фильтрации output classes. `--test-only` разрешает random encoder только на полностью synthetic active sources; такой cache не пройдёт real-training gate. Веса никогда не скачиваются автоматически. Dataset/split SHA означают manifest content/split-version; QA dataset_revision отдельно включает objects/actions/scenes/обе taxonomies.

## Train / resume

```powershell
python -m ml.cli train --cache D:\cache\tiny-train --config ml/config/train.example.yaml --smoke --steps 1 --output-dir D:\runs\tiny-first
python -m ml.cli resume --cache D:\cache\tiny-train --config ml/config/train.example.yaml --smoke --steps 2 --resume D:\runs\tiny-first\checkpoint.pt --output-dir D:\runs\tiny-resumed
```

`--smoke`: только test-only CPU, ≤4 windows/steps, T≤32, C≤8. Реальное обучение отложено; условия будущей команды — в TRAINING.md. Пример `.yaml` использует JSON syntax (валидное подмножество YAML), которое читает `--config`; произвольный YAML trainer не принимает.

Resume требует тот же cache/config/architecture/class order/runtime; меняется только общий step budget. Сохраняются actual model/optimizer/RNG/sampler states. Новая generation не затирает предыдущую. Checkpoint создаётся в конце ограниченного run; periodic checkpoint/epochs/early stopping не реализованы. При OOM остаётся последняя завершённая generation. All-unknown → ноль optimizer steps; такой checkpoint не экспортируется как обученный.

## Scores, thresholds, metrics

```powershell
python -m ml.cli evaluate --cache D:\cache\dev-v1 --checkpoint D:\runs\run-v1\checkpoint.pt --manifest D:\data\manifest.split.json --output D:\eval\dev.scores.json
python -m ml.cli thresholds --input D:\eval\dev.scores.json --output D:\eval\thresholds.json
python -m ml.cli evaluate --cache D:\cache\final-v1 --checkpoint D:\runs\run-v1\checkpoint.pt --manifest D:\data\manifest.split.json --output D:\eval\final.scores.json
python -m ml.cli evaluate --input D:\eval\final.scores.json --thresholds D:\eval\thresholds.json --output D:\eval\metrics.json
```

Для real pretrained scoring дополнительно передать `--encoder-weights` и `--encoder-sha256` с тем же локальным encoder. Scores объединяются по actual source PTS с masks. Training cache должен покрывать declared train source set; dev/final имеют другие windows/source hashes, но ту же общую lineage. Train/final calibration и пересечение source groups запрещены.

Evaluation input `ml-evaluation-input-v1` включает manifest/hash, split/test_only, class_ids, dataset/taxonomy/checkpoint hashes, `samples[{id,video_id,scene_id,time_sec,targets,scores}]`, `event_protocol:{version:"event-boundary-v1",tolerance_sec:0.5}`, а также отдельные `verdicts`, `truth_events`, `predicted_events`. Bool target — известная метка, null — unknown. Scores — probability/null; duplicate source time отвергается.

`verdicts[{id,video_id,truth,prediction}]` заполняются только отдельными reviewed verdicts; action classifier их не выдумывает. `events[{id,video_id,scene_id,class_id,start_sec,end_sec,known}]`: known=true означает reviewed сравнимый интервал, unknown не даёт negative. Events arrays заполняются из соответствующего evaluation workflow, не считаются известными по отсутствию labels. Порог и tolerance фиксируются на dev до final; изменение protocol отвергается. Сопоставление events — maximum one-to-one, оба endpoints в пределах tolerance, строго внутри video/scene/class.

Binary metrics отдельно показывают covered accuracy, balanced accuracy, macro-F1, support/TP/TN/FP/FN/absolute_errors, coverage, unknown и accuracy_over_all_known. Balanced accuracy усредняет supported recalls; macro-F1 — обе binary classes, undefined F1=0. Отсутствующие verdicts → null; пустые events → undefined precision/recall/F1, а не 1. Даже synthetic accuracy1 не является качеством настоящей модели. Evaluator оставляет validation_status=not_validated; release review — отдельный будущий шаг.

## Export / transfer / activation

```powershell
python -m ml.cli export --checkpoint D:\runs\tiny-resumed\checkpoint.pt --taxonomy D:\data\actions.taxonomy.json --thresholds D:\eval\thresholds.json --metrics D:\eval\metrics.json --metadata ml/config/release.example.json --output-dir D:\releases\tiny-v1
Get-FileHash -Algorithm SHA256 D:\releases\tiny-v1\package.json
python -m ml.cli import --package D:\releases\tiny-v1 --output-dir D:\installed\tiny-v1 --allow-test
python -m ml.cli activate --package D:\installed\tiny-v1 --pointer D:\installed\active-test.json --allow-test
python -m ml.cli rollback --pointer D:\installed\active-test.json --allow-test
```

Rollback требует предыдущую activation. `--allow-test` нужен для каждой test operation и сохраняет readiness=not_ready. Без него random/untrained пакет возвращает ModelNotReady; backend должен отобразить503. `package.json` — честный внутренний smoke format с actual_weights=None. K `release.json` требует IMAGENET1K_V1 и не создаётся для random encoder.

Полный state_dict включает encoder+GRU+head, без optimizer. Tensor/file bytes и training checkpoint bytes измерены отдельно, MB=1000000/MiB=1048576. Лимит всего model≤12MB, всех моделей≤35MB; превышение — отказ. Ни head-only размер, ни synthetic class count не подтверждают production budget.

Будущий production export требует `--production --approval <review.json>`, реальные trained weights/independent metrics/человеческую reviewed taxonomy и соответствующие hashes. Production import требует `--manifest-sha256`, `--expected-taxonomy`, `--expected-rules`; перед переносом сверить полный SHA по доверенному каналу. Loader также проверяет preprocessing, runtime, architecture, strict shapes и каждый artifact. Unknown/несовместимый runtime отвергается; CPU/GPU portability не заявлена без отдельной проверки.

```powershell
python -m ml.cli infer --package D:\installed\tiny-v1 --video D:\samples\tiny.mkv --output D:\eval\timeline.json --allow-test
```

Контейнер определяется по содержимому, включая штатные backend originals `<uuid>.video` и upload `.part`. Во всех проходах probe/index/decode разрешены только MOV/MP4, Matroska/WebM и AVI, с `protocol_whitelist=file`; playlists не допускаются. Файлы не переименовываются и не перекодируются для inference. Проверки SHA-256, PTS, rotation, geometry и decode budgets сохраняются.

Регрессия `python -m pytest tests/ml/test_inference_timeline.py -k backend_promoted -q` требует принятого backend A и настоящий `ffprobe` в PATH либо `FORTRESS_TEST_FFPROBE=<absolute executable>`. Она использует LocalStorage.spool/promote, VideoValidator, H.264 MP4/MOV и CLI inference. На Linux backend выполняется без адаптаций; на Windows fixture заменяет только POSIX directory fsync/pipe polling и сохраняет реальный ffprobe/валидацию/atomic rename. Это не проверка Linux durability, HTTP/очереди или production ML quality.

Без отдельного подтверждённого visibility context CLI inference выдаёт unknown, включая высокие scores; actors/relations остаются unknown. Python TimelineAdapter принимает независимый visibility provider и reviewed scenes через infer_indexed. Raw port использует одну unreviewed scene; автоматическое обнаружение монтажных склеек не реализовано. Нет надежной наблюдаемости — coverage=none, не clean verdict. Decode/OOM/hash/deadline/inference ошибки — failed; K findings принадлежат R.
