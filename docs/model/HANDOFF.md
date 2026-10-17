# Передача №3: программные инструменты готовы к review

Первоначальный M candidate **85e5b2162d86e95d831ce9fb7ef2c7578b9ee92d**; текущий M4/M follow-up **c68ae819d38cd14b97921c9c76ed1a4b92d89cc8**, ветка `codex/fortress-no3-ml`, репозиторий AlmazCode/Fortress. Позднейшие documentation commits записаны в [журнале №3](../github-plan/status/DEV-3.md). Публикация ветки не означает acceptance главным или production readiness.

## Проверено

`python -m pytest tests/contracts/test_schemas.py tests/ml -q` на M4/M follow-up → exit0, **273 passed in137.47s**, no skips. Предыдущий run на85e5b21:269 passed in137.76s. Общие CLI cache/train/resume/dev scoring/thresholds/final diagnostics/export/import/activation/rollback/infer и13 --help проверены в subprocess/in-process тестах. Actual native PyAV/Pillow/NumPy/PyTorch операции выполнены на synthetic CPU.

Ранее на85e5b21 standalone `python -m ml.cli smoke --output-dir <new-directory>` → exit0: три generated видео, grouped train/dev/final, actual PTS/PNG/tasks/canonical labels, три feature caches, CPU optimizer1+resume2, dev-only thresholds, final diagnostics, full FP32 measured export/import и unknown timeline. Summary/model/package SHA сохранены в журнале. Readiness data/trained/validated/production=false, verdict_metrics=null, timeline coverage=none.

Общий набор также покрывает extraction/COCO roundtrip/annotation QA и regression D3 re-split: прежний independent_test не возвращается в train/dev, поздний выбор final отвергается, transitive source/near groups сохраняются. Исправленный D3 — **54493fcd10b1824356f82df3f6bbbfadc1ea5ffc**, вместо отклонённого d0b9704.

## Текущее review №1 и исправление M4/M

Review №1 **69f2a3835a3b9964f8fc03922ea7da5ff03e9aa5** принимает D3–D и M1–M3. Исправленный D3 **54493fcd10b1824356f82df3f6bbbfadc1ea5ffc** интегрирован merge **d74e06ad80a6751d0bf50a0a66a7ae88192b10cc**; отказ к старому d0b9704 закрыт. Финальный holdout сохраняется при повторном split, другом seed и транзитивных source/duplicate/near groups, не попадает в training и threshold calibration. Split-код и его тесты в новом исправлении не менялись.

M4/M возвращены на исправление: принятый backend сохраняет оригинал как `<uuid>.video`, а прежний ML reader выбирал demuxer по суффиксу. Новый reader определяет контейнер по содержимому через native demuxer whitelist MOV/MP4, Matroska/WebM, AVI до чтения заголовков, сохраняет file-only protocols, hash/PTS/geometry/decode limits. Общий helper используется на всех трёх проходах: probe, build_index и iter_indexed_frames. Original не переименовывается и не перекодируется. Это исправление ML dependency reader, не изменение backend или holdout.

Регрессия [test_inference_timeline.py](../../tests/ml/test_inference_timeline.py) создаёт H.264 MP4 и MOV с rotation90/VFR/nonzeroPTS; реально выполняет LocalStorage.spool → VideoValidator → promote → повторный VideoValidator → adapter и CLI infer. До исправления MP4 проходил исходный путь и отказывал на .video; после исправления оба контейнера проходят. Неизменность bytes/mtime проверена; output остаётся unknown/coverage=none, test package остаётся not_ready. [test_manifest.py](../../tests/ml/test_manifest.py) отвергает реально декодируемый ffconcat playlist, [test_pts_index.py](../../tests/ml/test_pts_index.py) сохраняет hash/decode-budget failures для .video.

На Windows fixture адаптирует POSIX directory fsync и pipe polling, сохраняя настоящий ffprobe/validation/atomic rename; Linux выполняет backend без адаптаций. Linux durability/полная HTTP/queue/runtime интеграция этим Windows запуском не подтверждены. Точный новый SHA, команды и результаты — в [журнале №3](../github-plan/status/DEV-3.md). M4/M остаются review до проверки и интеграции №1.

## Что передать другому ПК

- Точный принятый code commit/общий lock/контракты, [CLI.md](CLI.md) и [TRAINING.md](TRAINING.md).
- Originals/полный manifest+audit+split, raw PTS index/scenes, task assets и versioned canonical annotations/taxonomies с hashes.
- После реальной подготовки — локальный IMAGENET1K_V1/full trusted SHA, actual preflight и freshly bound reviewed QA; никаких runtime downloads.
- После будущего обучения — immutable checkpoint/config/RNG lineage, dev thresholds/fixed [evaluation protocol](EVALUATION.md), independent real metrics и честную [model card](MODEL_CARD.template.md).
- После review — полный package/K manifest+каждый SHA, измерение encoder+GRU+head/all-model budget, совместимые taxonomy/rules/runtime, previous release для atomic rollback.

Другой ПК сейчас не доступен и не объявляется проверенным. Текущий lock CPU-only; CUDA/перенос между torch builds ещё требуют проверки. Full training/real data ML evaluation/цели≥0.80/production taxonomy budget/performance не выполнены.

## Остаток E

**E blocked: требуется принятый I.** Последняя наблюдённая integration — ecce7c2126e8e99e7dea3baff3af7b15b4391891; её последние изменения только документационные, принятый исполняемый состав совпадает с69f2a38. D1–D/M1–M3 приняты №1; M4/M требуют повторного review исправления .video, O сохраняет runtime/HTTPS blockers. Принятого I SHA пока нет.

После I получить его точный SHA, проверить ports/ready503/failed-vs-unknown путь в сочетании с backend/rules и воспроизвести handoff-команды на принятом составе. Не объявлять HTTP/Docker/external HTTPS/реальное training quality выполненными по одному local CPU smoke. Материалы E подготовлены заранее; окончательная integration verification не выполнена.

Машиночитаемая запись текущей подготовки — [ACCEPTANCE.json](ACCEPTANCE.json). Её state=blocked относится к E, software checks pass относятся к кандидату №3. Main/shared lock/backend/данные другого чата этим исполнителем не изменялись.
