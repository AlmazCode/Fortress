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

На Windows fixture адаптирует POSIX directory fsync и pipe polling, сохраняя настоящий ffprobe/validation/atomic rename; Linux выполняет backend без адаптаций. Linux durability/полная HTTP/queue/runtime интеграция этим Windows запуском не подтверждены. Точный новый SHA, команды и результаты — в [журнале №3](../github-plan/status/DEV-3.md). M4/M приняты №1: merge **894e869b7b02deceb0a3978e086750d828c380e0**, review **479aa05e7154b5b50bc9a70b0a8ea7ed8cca64b2**. На Linux273 tests/no skips/87.46s и отдельный штатный .video сценарий прошли без Windows IO adapters. Это software acceptance M, не полный I.

## Что передать другому ПК

- Точный принятый code commit/общий lock/контракты, [CLI.md](CLI.md) и [TRAINING.md](TRAINING.md).
- Originals/полный manifest+audit+split, raw PTS index/scenes, task assets и versioned canonical annotations/taxonomies с hashes.
- После реальной подготовки — локальный IMAGENET1K_V1/full trusted SHA, actual preflight и freshly bound reviewed QA; никаких runtime downloads.
- После будущего обучения — immutable checkpoint/config/RNG lineage, dev thresholds/fixed [evaluation protocol](EVALUATION.md), independent real metrics и честную [model card](MODEL_CARD.template.md).
- После review — полный package/K manifest+каждый SHA, измерение encoder+GRU+head/all-model budget, совместимые taxonomy/rules/runtime, previous release для atomic rollback.

Другой ПК сейчас не доступен и не объявляется проверенным. Текущий lock CPU-only; CUDA/перенос между torch builds ещё требуют проверки. Full training/real data ML evaluation/цели≥0.80/production taxonomy budget/performance не выполнены.

## Остаток E

**E blocked: требуется принятый I.** Текущий принятый software состав **479aa05e7154b5b50bc9a70b0a8ea7ed8cca64b2**, D/M приняты №1. Подготовка E **a06e6382638af7d52b0dda2b4cbc016e97cc362a** проверена дополнительно:22 parser/config tests и реальный перенос готового tiny package с hash/loader/production-refusal checks. O сохраняет runtime/HTTPS blockers; принятого I SHA пока нет.

После I получить его точный SHA, проверить ports/ready503/failed-vs-unknown путь в сочетании с backend/rules и воспроизвести handoff-команды на принятом составе. Не объявлять HTTP/Docker/external HTTPS/реальное training quality выполненными по одному local CPU smoke. Материалы E подготовлены заранее; окончательная integration verification не выполнена.

Машиночитаемая запись текущей подготовки — [ACCEPTANCE.json](ACCEPTANCE.json). Её state=blocked относится к E, software checks pass относятся к кандидату №3. Main/shared lock/backend/данные другого чата этим исполнителем не изменялись.

## Проверенная подготовка E

Эта таблица сопоставляет критерии E с конкретным software evidence. Она не заменяет зависимость от I, human review или ML validation.

| E критерий | Подготовка и наблюдённые проверки |
| --- | --- |
| 1. Команды и tiny data→ML путь | Принятые273 tests на c68ae81 включают фактический tiny CPU CLI pipeline. Новые22 checks на a06e638 проверяют21 документированную команду настоящим parser + CPU TrainConfig, без IO/train. |
| 2. Форматы, версии, hashes и отказ плохому release | Strict load переданной локальной smoke generation:10 artifacts, hash/size/lineage/576 проверены. Production untrained и неверный manifest SHA отвергнуты; K release schema/negative compatibility cases покрыты принятым273 run. Положительный trained release отсутствует. |
| 3. Передача другому ПК | TRAINING описывает Python3.11/FFmpeg/preflight, paths/seed/split/cache/OOM/resume/rollback/SHA и CPU-vs-CUDA границу. Другой ПК не проверен; доступа к нему сейчас не требуется. |
| 4. Независимая оценка | EVALUATION заранее фиксирует event-boundary-v1/0.5с, независимый video/scene final, цели≥0.80 и обязательные support/FP/FN/errors/coverage/unknown/event P/R/F1. Реальная оценка не запускалась. |
| 5. Честная card | MODEL_CARD.template сохраняет not trained/not validated, null metrics и конкретные data/taxonomy/rights/source/hardware gaps. |
| 6. Полный FP32 budget | Фактически загруженный model.pt6385243 bytes; encoder3756752, GRU/head2564104, whole tensors6320856, optimizer checkpoint11543771. Это C2 synthetic; production taxonomy/≤12MB/≤35MB требуют будущей проверки. |
| 7. Только разрешённый CPU smoke | Готовый synthetic package перенесён и проверен повторно без optimizer steps; full train/fine-tune/GPU search/реальная dataset evaluation не выполнялись. |
| 8. Data/annotation workflow | Extraction/COCO roundtrip/annotation QA/grouped split/holdout protections уже входят в принятые273 checks. Existing artifacts сохраняют source/PTS provenance; новые данные другого чата не читались и не изменялись. |

Package/source-copy manifest SHA **b81ffe159a0516fbdebea0c0ff80245ffd115bff97bc7ab4d7fb22e4f2dc4351** и model SHA **6b89924cc8a3622d4d47d4f06763a5de3eeb2f200b737371f45cfcca60096c5f** проверены новой E transfer verification; локальный полный отчёт вне Git, агрегат — ACCEPTANCE.json. Все readiness gates остаются false/not_ready.

## Пакет дальнейшей интеграции I

Предварительная сверка выполнена после подготовки E на479aa05. Полный I остаётся blocked до фактически принятого O и доступного Linux runtime. Текущий Windows host не имеет fcntl/Docker CLI в PATH/стандартной установке. Production `_components` в backend/app/main.py пока выбирает MissingRelease/MissingRunner; release_root ещё не связан с M/R. Это открытый объём I, а не проверенная интеграция.

После закрытия prerequisites:

1. Зафиксировать точные accepted A/F/M/R/O + K/D SHA и итоговый состав; общий lock/contracts/граф не подменять.
2. Подключить production ReleaseManager/TimelineAdapter с отдельно доверенными manifest SHA/taxonomy/rules versions; путь или значения из самого непроверенного package не открывают readiness. Без usable release сохранить503 model_not_ready до создания job/outbox. Test/demo компоненты доступны только явному synthetic profile.
3. Соединить job runner с новым RuleEngine на каждое задание, source evidence и K diagnostics. Сохранить reset по сценам, unknown actor/relations, неподтверждённые нормы; coverage=none даёт durable failed insufficient_evidence. Partial coverage не становится полным clean verdict.
4. На Linux выполнить настоящий FastAPI/PostgreSQL/Redis/Celery/UI путь upload→outbox→worker→timeline/rules→result→protected Blob seek. Проверить1–3 JPEG из того же original/PTS, hashes/preview mapping, exact public/UI schemas, media auth, retry/duplicate/fencing/deadline failures. Fixture не подтверждает реальный ML/legal результат.
5. Привязать фактические O evidence: Compose build/start, worker DB/Redis при запрещённом egress, persistence media/models/DB после restart, hardware/CUDA статус и независимый внешний HTTPS observer. YAML/loopback/Windows adapters их не заменяют.
6. После проверки и принятия точного I commit завершить E на этом составе: сверить изменённые ports/CLI/форматы, воспроизвести только затронутые handoff checks, приложить реальные команды/exit codes и сохранить data/rights/review/hardware gaps. До этого E final/I success не заявлены.

Последний fetch перед публикацией: integration **469b2eb841de187d8e3429dc17514254777d3bdc**, TLS diagnostic fix №4 принят как tooling; backend/ML/contracts/locks относительно проверяемого E состава479aa05 неизменны. Published STATUS по-прежнему сохраняет O/I blocked.
