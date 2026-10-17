# Журнал разработчика №3 — ML / Данные

Рабочий процесс — Git/GitHub, без Aster. Проверка 17 октября 2026 года.
Своя ветка: `codex/fortress-no3-ml`; пакет инструкций и база этой проверки:
`c70a6d366c9b48b090368b92ca1bb60b692f6c26`.

| Task | State | Branch | Commit / PR | Проверки / блокер |
| --- | --- | --- | --- | --- |
| D1 | accepted | codex/fortress-no3-ml | 536fe7af06cadb4ff9513da1bf8dcafb6e6198e6 | Принят главным, merge 8dd2da1; software D1, training gate закрыт |
| D2 | accepted | codex/fortress-no3-ml | b4961272723cefec463d45ccb49d041afd52150b | Принят главным как draft, merge 47787cb; final taxonomy/human review не заявлены |
| D3 | review | codex/fortress-no3-ml | 54493fcd10b1824356f82df3f6bbbfadc1ea5ffc | Исправлен P1 re-split holdout leak; 136 passed + реальный повторный CLI; нужен повторный review №1 |
| D4 | review | codex/fortress-no3-ml | 8b263be898a7f62504cce7a27d82ad8cce89e60b | 14 targeted tests; вместе K/ML 150 passed; четыре настоящих CLI passed; приёмка отдельно |
| D5 | review | codex/fortress-no3-ml | 4ad53e30fe844fba794368e15fa53b91588e007f | 40 targeted tests; K/ML 190 passed; task CLI + JSONL/CSV/COCO/QA smoke passed |
| D | review | codex/fortress-no3-ml | 97bb8cdc6f507990edd5fbd469708a3f4aeb806d | 196 tests passed; 15 data CLI --help и реальный pipeline; data/training false |
| M1 | review | codex/fortress-no3-ml | 145e33e3b80f0001b4eb0eb695ee7b3916c00ce5 | 28 targeted passed; real CPU MobileNet [32,576] cache smoke passed; test-only |
| M2 | working | codex/fortress-no3-ml | База M1 145e33e | Продолжение по поручению человека; frozen encoder/GRU/CPU train-resume |
| M3 | blocked | codex/fortress-no3-ml | — | Зависит от M2 |
| M4 | blocked | codex/fortress-no3-ml | — | Зависит от M3 |
| M | blocked | codex/fortress-no3-ml | — | Зависит от M4 |
| E | blocked | codex/fortress-no3-ml | — | Зависит от I |

## Подготовка до push K

- Прочитаны AGENTS.md, WORKFLOW.md, REQUIREMENTS.md, PLAN.md и полное ТЗ DEV3_ML_DATA.md; сопоставлены все 12 своих задач с plan.json. Исторические MCP-указания не применяются.
- Origin указывает на тот же AlmazCode/Fortress; сохранённый URL использует HTTP, Git наблюдённо перенаправляет его на HTTPS. URL проекта не менялся.
- `git cat-file -t 46b7bc941e64fec5649242b8290607c8f7339819` — exit 0, commit; `git merge-base --is-ancestor 46b7bc941e64fec5649242b8290607c8f7339819 HEAD` — exit 0.
- `git pull --ff-only origin main` — exit 0, Already up to date. После `git fetch origin` найден действующий пакет в codex/github-transition.
- `git pull --ff-only origin codex/github-transition` — exit 0; собственная ветка обновлена fast-forward до указанной базы проверки. Чужие checkout и main не переключались.
- `git ls-remote --heads origin` — exit 0. На момент проверки опубликованы main, codex/github-plan, codex/github-transition и codex/dev2-frontend. Интеграционная ветка и результат K в них не найдены.
- `git ls-tree -r --name-only <ref>` для этих четырёх refs — exit 0. Файлы contracts/, pyproject.toml и uv.lock отсутствуют. Это наблюдение об отсутствующем prerequisite, не проверка работающего API.
- `.venv/Scripts/python.exe -X utf8 docs/github-plan/validate_plan.py` до изменения журнала — exit 0: 36 задач, 48 связей, 12 задач №3, без циклов и пересечений областей независимых исполнителей. Проверен пакет документов, не приложение или ML.
- Рабочая папка — корень своего worktree, rootPath пустой. Абсолютный путь и локальные служебные журналы сохранены в неотслеживаемой контрольной точке. Датасет другого чата и исходные видео не изменялись.

## История начальной блокировки

Реализация и проверки критериев D1/D2/D3 ещё не запускались: по WORKFLOW.md перед началом требуется проверенный результат K и точный SHA в согласованной интеграционной ветке. Остальные задачи заблокированы указанной цепочкой. Ни одна карточка не объявляется ready/review/accepted по наличию плана.

Target Python/PyTorch/Torchvision/CUDA, 576 feature shape, preprocessing, annotations, split, train/resume и release loader пока не проверены по действующему K. Полное обучение и реальная ML-оценка не запускались; synthetic данные не выдаются за готовый датасет или качество модели.

Общий manifest пакета фиксирует исходные хэши журналов. Обновление собственного журнала требует штатного обновления manifest/AUDIT главным при интеграции; №3 эти общие файлы не редактирует.

## Снятие блокировки K

После сообщения человека о push получен K `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f` из ветки главного `codex/fortress-backend`. Сам K начат от initial commit и не содержит GitHub-пакета документов. Выполнен обычный merge в свою ветку; инструкции/план сохранены. Результат объединения `04058fd48ce01d31bb4231769b9ceeaa739b6b38`; K — его предок. `pytest tests/contracts/test_schemas.py -q` — exit 0, 55 passed. Общие contracts/locks №3 не изменяет. Последующий backend A1 `a84cce5` не меняет K и для D1 не требуется.

## D1 — готовый кандидат

- Base: `04058fd48ce01d31bb4231769b9ceeaa739b6b38`; candidate: `536fe7af06cadb4ff9513da1bf8dcafb6e6198e6`.
- Файлы: ml/__init__.py, ml/preflight.py, tests/ml/test_preflight.py, docs/model/DATA_INVENTORY.md, docs/model/MISSING_MATERIALS.md. Diff — только add этих пяти файлов; переименований/удалений нет.
- `uv sync --locked --group test --extra ml --no-build` — exit 0; lock №1 не менялся. Python 3.11.14, torch 2.14.1+cpu, torchvision 0.29.1+cpu.
- `.venv/Scripts/python.exe -m pytest tests/ml/test_preflight.py -q` — exit 0, 9 passed. После этой проверки код не менялся; добавлены документы с наблюдёнными фактами.
- `.venv/Scripts/python.exe -m ml.preflight --project-root . --data-root <local-video-root> --annotation-root <local-annotation-root> --case <local-case> --self-test --output <new-local-report>` — exit 0. Полные локальные аргументы/абсолютный checkout и отчёт сохранены вне отслеживаемого кода.
- Финальный локальный отчёт SHA-256: `432959c3b6493d9f7a159db29598059fee068448c5205f9dcbcf96e7202bbcda`. Первый обход служебного окружения остановлен, затем добавлено явное исключение hidden/tooling directories и проведена новая проверка; остановленный запуск не считается passed.
- `git diff --cached --check` перед commit — exit 0. Реальные CLI и тесты проверяют software D1, не качество модели.

Покрытие acceptance D1:
1. Каждый учтённый материал имеет source/path/type/availability/size/SHA/rights/review unknown. Отсутствующие TECHNICAL_SPEC, DATA_AND_TRAINING, CASE_COVERAGE названы; исходный case действительно доступен локально. Проверены bounds, missing paths и сохранность исходных bytes/mtime.
2. Видео/изображения/annotation-or-metadata/weights разнесены. Наблюдены 42 видео и 2621 изображение. Templates/metadata не объявлены reviewed labels, photos не объявлены GRU sequence, raw weights не объявлены production release.
3. CLI наблюдает Python/PyTorch/Torchvision/CUDA/device и RAM/VRAM. Локальная CPU-сборка не подтверждает GPU или другой training PC; hardware_unverified=true.
4. Реальный CPU weights=None self-test даёт [1,3,224,224]→[1,576], без скачивания весов. Потеря runtime даёт failed. Полный train/fine-tune/GPU search/dataset evaluation не запускались.
5. tools_ready отделён от наличия/валидности данных; annotation_missing=null при наличии непроверенных файлов, review=unverified; license_unknown=true; training_ready=false. Отдельный regression check не смешивает restricted с unknown.

Ограничения: decode/dedup/group split/annotation QA — следующие этапы; labels, rights и target GPU не подтверждены. Ни software D1, ни синтетические веса не активируют production readiness.

Следующий шаг: D2 и D3 по проверенному K. D1 остаётся review до проверки и интеграции главным; №3 не выставляет себе accepted. Публикация своей ветки следует фактическому разрешению человека.

## D2 — готовый кандидат

- Base: `9aa9dda`; candidate: `b4961272723cefec463d45ccb49d041afd52150b`. Только шесть разрешённых файлов D2, все добавлены; удалений/переименований нет. Абсолютный собственный checkout сохранён в локальном checkpoint, частные пути не публикуются.
- `.venv/Scripts/python.exe -m pytest tests/ml/test_taxonomy.py -q` — exit 0, 17 passed. Реальные draft-файлы и состояния/known_mask дополнительно проверяются действующим contracts.python_ports.validate_contract("events", ...).
- `.venv/Scripts/python.exe -m ml.data.taxonomy ml/config/object_taxonomy.draft.json` — exit 0: objects-draft-v1, 9 classes, 0 states, official IDs not supplied.
- Такая же CLI для action_taxonomy.draft.json — exit 0: actions-draft-v1, 14 classes, 6 states, official IDs not supplied. Код после этих проверок не менялся.
- `git diff --cached --check` — финальный exit 0. Первый check обнаружил только лишние пустые строки в конце двух документов; исправлены до commit.
- Покрытие acceptance: девять candidate objects; versioned action/state definitions; includes/excludes/hard negatives/visibility/truncation/unknown и честный unmeasured pixel limit для каждого; append-only IDs с проверкой против previous; nullable identity/party/role links; карта всех C01–C15 с пределами наблюдения и R1; human review, disagreement, explicit negatives, pseudo-labels не gold, отдельный final holdout.
- Формат K bbox=xywh сохранён; будущая внутренняя xyxy-разметка преобразуется обратимо, отсутствующие в K поля хранятся в sidecar. Общий контракт не менялся.

После fetch подтверждена интеграционная ветка `codex/integration` на `c22a4a6`: STATUS.md принимает K `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`, но D1 ещё review. `git diff --stat origin/codex/integration -- contracts pyproject.toml uv.lock` пуст: используемый K/lock не изменён.

Человек явно разрешил обычный push проверенных commits №3 в codex/fortress-no3-ml; разрешение распространяется на следующие проверенные результаты №3. D1 и журнал уже опубликованы. D2 остаётся review до проверки главным. Официальная taxonomy, человеческая разметка, права и training readiness не подтверждены; обучение и реальная ML-оценка не выполнялись. Следующая независимая задача — D3; D4 ждёт принятого D3.

## D3 — исходный кандидат (возвращён на исправление)

- Base: `c4857881d6a7e44af9f643b2ea2dc4713241abbc`; candidate: `d0b9704b005e85675191baf0c0737b5d6da8cc49`. Diff — add только десяти разрешённых файлов D3, 1068 строк; contracts/locks и исходный датасет не изменялись.
- `.venv/Scripts/python.exe -m pytest tests/contracts/test_schemas.py tests/ml -q` — exit 0, **129 passed**, no skips (K 55, D1 9, D2 17, D3 48). Проверялся неизменённый код кандидата до commit.
- Первый targeted D3 run: 43 passed / 2 failed — выявлены implicit directory case collision и необработанный zlib error. Исправлены до итоговой проверки: collision отвергается до extraction, повреждённый поток откатывает private staging. Повторный промежуточный run 45 passed; затем добавлены реальные rotation/reflection и pre-allocation entry-limit проверки, вошедшие в финальные 129.
- `python -m ml.data.manifest --help` и `python -m ml.data.splits --help` через собственный Python3.11 — оба exit 0.
- Настоящий отдельный CLI smoke вне Git: сгенерированы четыре tiny synthetic FFV1/matroska видео 32×24 с исходными PTS; `python -m ml.data.manifest --config <local-config> --output <new-import.json>` — exit 0, videos=4, imported_unassigned, training_ready=false. `python -m ml.data.splits --input <import.json> --output <new-split.json> --seed 17 --final-video-id <explicit-synthetic-id>` — exit 0, train=2/dev=1/final=1/excluded=0, training_ready=false. Полные аргументы и отчёты сохранены в локальном checkpoint, не в Git.
- SHA-256 import report: `753d007e902a0564aa8722a9e5b27c4e187516dbdc06e8496a05a7192322a5a7`; split report: `6110fe44e1c5af6e13a8fa5f57efc3303fdaf1211884cb85cc9aec6a7f106a88`. Это проверка кода, не фактический split исходных видео и не ML-оценка.
- `git diff --cached --name-status` — ровно область D3; `git diff --cached --check` — exit 0.

Покрытие acceptance D3:
1. ZIP rejects traversal/absolute/Windows drives/UNC/mixed separators, links/special files, reserved names, explicit и implicit case/Unicode collisions, file-directory collisions, entry/compressed/uncompressed/ratio limits. Central-directory count проверяется до allocation ZipFile; ZIP64/split ZIP не поддерживаются и отвергаются. Реальный bad deflate и скрипт проверены: originals не меняются, script не выполняется, частичный staging удаляется только внутри проверенного output parent, destination не перезаписывается.
2. Read-only full decode и SHA-256, original/synthetic provenance и source/video/group/scene IDs; относительные local-only paths. Карантин с причиной/доступностью/правами в audit sidecar, поскольку K запрещает дополнительные поля manifest. Missing identities явно unverified/excluded. Corrupt/budget/unsupported sources не попадают в manifest; пустой набор даёт manifest=null/data_not_ready.
3. Exact SHA clusters; near candidates через versioned early dHash sequence с config/hash/threshold/distances и ограничением пар. Кандидаты требуют source-pixel review и могут пропускать edits/shifts; это ограничение записано, originals не удаляются. Static scene similarity не объявляется доказанной идентичностью.
4. Transitive source/group/canonical/scene/SHA/near-candidate components делятся целиком. Даже excluded member исключает всю связанную группу. Seed+normalized manifest/config дают воспроизводимую split_version; explicit final защищён от training и threshold_calibration selectors. Не заявлена проверенная независимость ракурса.
5. Только tiny synthetic; нет 30/10, выдуманного минимального объёма или готового real dataset. Нет прав/групп — неeligible/excluded; нет источников — data_not_ready. Training_ready всегда false до следующих annotation/readiness gates.

Ограничения: поддержаны локальные MP4/MOV/M4V/MKV/WebM/AVI; неподдержанные контейнеры, changing geometry и отражение/scale/perspective display transform карантинируются. Loop budgets native decoder не равны OS process isolation; это явно указано в audit/API. Сцены пока unsegmented, D4 должен проверить реальные границы. Настоящий dataset другого чата не извлекался/не делился/не размечался.

## Проверка интеграции и следующий gate

После нового fetch `origin/codex/integration` = `2ba4272e9504e7b15c76cecc04f7ed6fa5d98788`. Главный принял software D1 и включил точный `536fe7a` merge `8dd2da1`; ancestry check exit 0, STATUS.md и журнал №1 это фиксируют. Собственная строка D1 обновлена по фактической приёмке, не по авторской самооценке. K/pyproject/uv.lock всё ещё без изменений относительно этой integration. D2 и D3 — опубликованные кандидаты review; D4 не начинается до проверки и интеграции D3 по AGENTS.md/WORKFLOW.md. Следующее действие главного — review/integrate D2/D3, затем №3 получает точный принятый D3 SHA и выполняет D4.

Последующий fetch: integration `c00516e` принимает D2 `b4961272723cefec463d45ccb49d041afd52150b` как draft (merge `47787cb`); ancestry check exit 0. Строка D2 синхронизирована с приёмкой главным. D3 и журнал опубликованы до `ad39b03f0ba751137f441a19e6644ca0da0c2e50`, remote head подтверждён через ls-remote, рабочее дерево чистое. Старое упоминание c485788 в чужой сводке отражает её время проверки, а не отсутствие опубликованного D3.

## D3 — исправление P1 после review №1

Получен `origin/codex/integration=bfff45447f74a5263b1d728e05ebb41490d91b58`. Главный фактически воспроизвёл утечку: повторный split уже разделённого bundle без final flag терял independent_test и выдавал прежний final в training. Авторский 129-test suite пропустил повторный сценарий. Замечание принято; прежний `d0b9704` не считается принятым или достаточным.

Base исправления: `0e9bebc8417dbf63364b735624f7fbd8ac4e309f`; candidate: **`54493fcd10b1824356f82df3f6bbbfadc1ea5ffc`**. Только три файла D3: ml/data/splits.py, ml/config/data.example.yaml, tests/ml/test_splits.py. Контракты/locks/original data не изменены.

- До изменения product code добавлены регрессии: targeted run → exit 1, **5 failed**. Два seed теряли final; новый final не отклонялся; связанные source/SHA/near groups теряли holdout; реальный CLI подтвердил дефект.
- Отдельный CLI на прежнем изолированном synthetic bundle, seed17 без final flag → exit 0, train3/dev1/final0; прежний final перешёл в dev_validation. Это утечка в threshold calibration, даже при training_ready=false. Отчёт сохранён вне Git, SHA-256 `9bd8c90d193778343d82974bf96a1a9d154d6aacdc14b19a63d22de4794747f2`.
- Исправление grouped-v2: сохраняется полный existing independent_test; смена seed/dev ratio его не перемещает; изменение final selection после любого train/dev/final assignment отклоняется до output. Ранее использованные train/dev нельзя «сделать независимыми» новым flag. Повторное указание текущего final допустимо и idempotent. Ineligible existing final и пересекающие partitions новые duplicate edges отвергаются.
- Transitive source/duplicate/near components сохраняются в manifest.group_id как component hash; исходные group IDs остаются в import audit. Поэтому забытый optional near sidecar при следующем API call не разрывает прежние группы. Canonical identity не подменяется near similarity. Новый алгоритм имеет новую split_version, инвалидирующую downstream inputs.
- Реальные CLI regression tests создают новые FFV1/MKV и вызывают отдельные Python-процессы import → first split → re-split seed17/99 без flag → запрет другого final. Проверены distinct sources и transitive source+exact-copy groups, оба selectors training/threshold_calibration, отсутствие output при отказе, hash/mtime originals.
- Финальный `.venv/Scripts/python.exe -m pytest tests/contracts/test_schemas.py tests/ml -q` → exit 0, **136 passed in 12.50s, no skips** (55 K + 9 D1 + 17 D2 + 55 D3). Код после проверки не менялся.
- Отдельные CLI re-split прежнего bundle после fix с seed17 и seed99 → оба exit 0, train2/dev1/final1; тот же ID остаётся independent_test. SHA-256 отчётов: seed17 `1af8954ab5711192b39291724f4ad13db337e338dbabca185c3fb5d65282b1f4`; seed99 `7fc8431365d7bc79c24029b840accc0274ef634cbfc9f765be649206aa5a42c6`. Полные локальные пути/argv сохранены вне Git.
- `git diff --cached --check` → exit 0; staged paths — ровно три разрешённых файла D3. Full train/fine-tune/реальная ML evaluation не выполнялись; все regression data synthetic.

Человек после ожидания поручил «делай»; начат локальный черновик D4 поверх проверенного автором D3. После сообщения об утечке работа D4 остановлена, четыре собственных непроверенных файла сохранены вне Git в локальной контрольной папке. Они не входят в исправление D3 и не объявлены готовыми. Следующее действие №1 — повторная проверка точного `54493fc` и интеграция D3; D4 по графу ещё не принята/не открыта. Журнал обновлён до review нового кандидата, а не accepted.

## D4 — кандидат после прямого поручения продолжать

Человек затем явно поручил: «проверь, принял ли N1 исправленный D3, и продолжай D4 и остальные свои задачи». Fetch и STATUS.md проверены: integration пока на `bfff454`, в нём старое замечание к `d0b9704`, новый `54493fc` ещё не принят. Согласно новому прямому поручению человека продолжена реализация кандидатов в своей ветке поверх проверенного исправления; это исключение из административного ожидания, не самостоятельное принятие задач. Общие main/STATUS/contracts не менялись.

- Base: `becebd45969001380ba05b086ead0cda3b66bdd2`; D4 candidate: `8b263be898a7f62504cce7a27d82ad8cce89e60b`. Diff — 7 добавленных разрешённых файлов D4, 960 строк. Старый собственный черновик восстановлен из сохранённой копии, проверен/дополнен tests/docs.
- `.venv/Scripts/python.exe -m pytest tests/ml/test_pts_index.py tests/ml/test_extraction.py -q` → exit 0, 14 passed; после уточнения byte limit повторная общая проверка `tests/contracts/test_schemas.py tests/ml -q` → exit 0, **150 passed in 13.20s**, no skips (D4 14).
- Реально воспроизведены все четыре CLI в EXTRACTION.md на отдельном synthetic work root: pts_index → exit 0, 4 source frames; scenes cut1.3 → exit 0, 2 unreviewed scenes с actual boundary2.0; extract_frames rate2/crop[2,4,30,22] → exit 0, 4 PNG / 6392 file bytes; extract_clips rate2,size32,stride16 → exit 0, 2 FFV1/MKV / 9030 file bytes. Counts/bytes исключают marker JSON; общий byte limit marker учитывает. Все четыре --help → exit 0.
- Настоящий повторный decode клипов подтвердил source bounds [0,2) и [2,3.1), encoded pts 0/1000, последние duration 1000/100 ticks при time_base1/1000. Это не keyframe stream-copy. Original PTS сохраняются отдельно от квантованных encoded PTS.
- Acceptance: PTS/origin/time_base/source hash и partition сохраняются; actual K TimeMapping проверен; sample cadence configurable, missing image/known/padding раздельны; окно32/2fps имеет coverage16s/span15.5s/stride8s и tail masks; windows/клипы внутри scene/split; affine crop/CCW rotation inverse проверен для четырёх поворотов; byte-reproducible artifacts, rerun/hash/metadata/source/config corruption, disk/byte/decode-work limits и rollback проверены.
- Unreviewed cuts не заявляют отсутствия других склеек; rate2 не гарантирует быстрые события. Никакие object/action labels не выдуманы, training_ready=false. Native decode loop не OS sandbox; output timing tolerance0.0011s, exact source mapping не теряется. Реальные пользовательские видео/labels не использовались.
- `git diff --cached --name-status` — ровно 7 D4 paths; `git diff --cached --check` → exit 0. Source code после общей проверки не менялся. Полные local argv, output paths и frozen checkpoint остаются вне Git.

Следующая работа по прямому поручению — D5 поверх этого проверенного кандидата; D3/D4 остаются review для N1. Публикация проверенных собственных commits разрешена человеком ранее.

## D5 — проверенный кандидат разметки и QA

- Base `763f2b91dd9df7262d38d1ff866cc2dcbea7fff7`; candidate `4ad53e30fe844fba794368e15fa53b91588e007f`. Ровно 9 разрешённых добавленных файлов D5, 982 строки, без shared changes.
- Финальный `.venv/Scripts/python.exe -m pytest tests/contracts/test_schemas.py tests/ml -q` → exit 0, **190 passed in 18.20s, no skips** (D5 40). Source code после этой проверки не менялся.
- `python -m ml.data.annotation_tasks --manifest <synthetic-split> --index <index> --scenes <scenes> --frames <PNG-output> --annotation-version synthetic-cli-labels-v1 --output-dir <new-local-bundle>` → exit 0: 4 frames, 6 tasks, training_ready=false, annotation_ui=not_verified. --help → exit 0.
- Отдельный local API smoke: COCO+sidecar roundtrip, action JSONL/CSV roundtrip и настоящий pixel/source-hash QA → exit 0; valid=true, annotation_records=0, unknown_rate=null, assets/sources_verified=true, data_ready=false/training_ready=false. Первый запуск внешнего helper как script не видел cwd package; запуск через `python -c "import runpy; runpy.run_path(...)"` из checkout прошёл. Это ошибка вызова helper, не успешная проверка первого запуска.
- Final QA report SHA-256 `ccc7d98e85b49b5d7d3b9c075c749a5a408fa79a560bec5e2155cd5cdfbfd629`; COCO `d7aaaf29c0c687c44387831f13d34974519d0efb2e569f0dea8d8f805c57678d`; sidecar `93a0bedddc881c0179684b6743fedaf3bbdb283563126810532fde274528d205`; action JSONL `728c51601efc2508302e5a710010bec8e0198aa632909c6b8677bb1a2c6579cb`; CSV `e85553d9593ca0f5b91c2a1798d79f5c020709dc6ca5fdbc16f70b90cc7720e9`. Эти артефакты synthetic, полные paths/argv вне Git.
- Acceptance: canonical original bbox/PTS/visibility/occlusion/truncation/nullable identities/review versions; проверенный COCO xyxy↔xywh с четырьмя rotations/crop и metadata sidecar; ID/area/bounds/path/provenance validation; независимые actions могут пересекаться, противоречащие reviewed labels не могут; explicit negatives требуют reviewed complete visible interval; pseudo/unreviewed/needs_review не становятся gold/known. Новые/редактированные/удалённые COCO labels требуют новой annotation version и сбрасывают затронутый review; dataset_revision меняется по content.
- QA показывает per-class/case/video counts, small-side diagnostic16px (не recognition threshold), occlusion/truncation, unknown/disagreement/duplicate/leakage/review/rights/source+PNG checks. Objects-only, synthetic и пустые templates не открывают temporal/training gate. Human-reviewed taxonomy/scenes/labels, original sources, rights и independent final evidence требуются отдельно.
- K views структурно проверены настоящим validator. Objects K/COCO geometry соответствует фактическому PNG; original coordinates/transform/дополнительные review fields сохранены canonical sidecar. Нормативные выводы R1 не присваиваются; annotation UI не объявлен установленным. COCO primary API сверено по официальному cocoapi source, ссылка в ANNOTATION_WORKFLOW.md.
- `git diff --cached --name-status` — ровно 9 D5 paths; `git diff --cached --check` → exit 0. Реальный датасет не размечался/не оценивался, training не запускался.

После очередного fetch N1 всё ещё не зафиксировал приёмку исправленного D3. Продолжение D выполняется по прямому поручению человека; все собственные D3/D4/D5 остаются review и не объявляются accepted.

## D — собранный data CLI и readiness

- Base `46719d2a3f2164b4569b5d931e3096fb0d6baeb2`; candidate `97bb8cdc6f507990edd5fbd469708a3f4aeb806d`. 10 разрешённых путей D: unified CLI/tests, DATA.md/наблюдённый DATA_READINESS.json, MISSING_MATERIALS и интеграционные уточнения собственных D4/D5 modules/tests. Данные/locks/contracts/shared code не менялись.
- Unified import/split/extract/tasks/annotation-import/export/validate/report реально запускались отдельными Python-процессами на новых synthetic FFV1/MKV. JSONL/CSV/COCO roundtrip, re-split protection, actual PTS и hashes/mtime originals проверены. Targeted pipeline → exit 0, 4 passed in45.66s; full `python -m pytest tests/contracts/test_schemas.py tests/ml -q` → exit 0, **196 passed in65.54s, no skips**. Код после этого не менялся.
- Длинные проверки теперь сохраняют local log и exit file вне Git. Предыдущая сессия после обновления environment потеряла final output и не была засчитана; повтор с явным собственным cwd и durable log завершён. Shared checkout не редактировался.
- Unified inventory реально выполнил CPU weights=None self-test [1,576]. Объём/архив, parent extraction transaction, вложенный PNG corruption, snapshot dataset_readiness schema и invalid labels present-but-unverified покрыты. Top help и все 15 data subcommands --help → exit 0.
- Интеграционное уточнение: task context содержит immutable frame anchors (PTS/source SHA/artifact hash+geometry). Изменённый на другой существующий PTS кадр отвергается; legacy tasks без anchors требуют regeneration. Parent extract marker теперь хэширует все вложенные frame/clip bytes и учитывает их в общем byte budget. Пустой invalid labels object не заменяется тихо template; annotation_missing=null при имеющемся невалидном input.
- Отдельный настоящий CLI smoke вне Git создал 4 PNG/2 clips, 6 tasks и COCO roundtrip; report → exit 0, tools_ready=true/validation_passed=true/data_missing=true/annotation_missing=true/data_ready=false/training_ready=false. Это synthetic manifest: не опровержение D1 snapshot с42 пользовательскими видео. Source/asset hashes реально проверены, labels пустые, unknown_rate=null.
- Local DATA_READINESS report SHA-256 `dc5e5be077fd12a7579fb811ddcf590eafcb77e39b32c8f95e2969c4c4d96168`; содержимое сохранено как docs/model/DATA_READINESS.json. В нём actual K dataset_readiness contract=blocked, provenance synthetic. Никаких метрик качества модели/человеческого gold не создано.
- Acceptance D: материалы/отсутствующие приложения и фактический case отмечены по D1; safe archive/quarantine/dedup/transitive split/final protection/PTS/masks/COCO/review QA собраны; Python3.11 CPU preflight проверен, target RTX5060/RAM16/Ryzen5 и CUDA явно unverified; DATA.md содержит реализованные команды и отдельные gates/reasons. Оригинальный набор другого чата не оценивался/не менялся, full training не запускался.
- `git diff --cached --name-status` — ровно 10 разрешённых путей; `git diff --cached --check` → exit 0. Candidate D остаётся review; последняя наблюдённая integration всё ещё содержит старую блокировку D3, новый D3 fix не объявляется принятым автором. Следующий собственный этап по прямому поручению — M1.

## M1 — preprocessing/windows/cache

- Base `0ec4d69b7d0babd7293d5a7764032375709befe4`; candidate `145e33e3b80f0001b4eb0eb695ee7b3916c00ce5`. Add ровно шести разрешённых M1 файлов, 762 строки; D/общие файлы не менялись.
- `python -m pytest tests/ml/test_pts_preprocessing.py tests/ml/test_cache_resume.py -q` → exit 0, **28 passed in5.89s**. Ранее tests нашли tuple/list inconsistency на повторном JSON load (1 failed/26 passed); metadata нормализована. Дополнительная регрессия source bytes mutation сначала дала expected failing test: complete cache тихо возвращался при старом manifest. До публикации build_cache получил обязательный source_root и actual SHA check до reuse/после построения; test теперь passed.
- Отдельный API CPU smoke с настоящим torchvision MobileNetV3-Small features(weights=None), spatial mean, замороженными параметрами и общим preprocessing → exit 0. Четыре synthetic source frames дали 2 windows [32,576], 4 искусственных known labels; cache load прошёл, production_cache_ready=false, training_ran=false. Labels smoke.action_a/b — искусственные, не bank-event gold. Веса не скачивались.
- Local summary SHA `07c6bb028dd97debf85e7789abc2869d4def207d2b7b236a5a14456735b79dee`; completion marker `b27749dc454241c8d445ab9341d4af7cf39fc1344c6684a02410df9b73f1851d`; cache.json `af740043bc1486e020f809eda67f757f990626cbb4fd48e4b109946999400a9c`. Paths/полный helper/argv/логи сохранены вне Git.
- Acceptance: shared RGB/letterbox224/ImageNet FP32 path, pixel padding mask и точный inverse с actual resize ratios; four rotation/odd sizes/channel/double-normalization checks; source PTS labels/nullable actor policy, unknown/image/padding masks; overlap mean/counts/null для unknown и запрет crossing scene/split/source.
- CacheSpec включает все девять input/window hashes, class order, partition и test provenance. Каждое поле invalidates старый cache. Encoder fingerprint берётся с actual frozen tensor bytes и проверяется до/после; cropped annotation image не принимается как raw global frame. Numeric NPZ без pickle, bounded header/shape/dtype/bytes, finite targets/features и mask checks; actual partial filesystem write откатывается, source originals неизменны; corrupt/foreign cache сохранён и отвергнут, новая generation реконструируется.
- Real/pretrained feature cache и hardware budgets не заявлены: только synthetic CPU, descriptor weights=None/test_only=true. Cache completeness не dataset/model readiness. Load переносимого immutable cache сверяет spec/bytes, raw-source reuse дополнительно проверяет files. Документация PREPROCESSING.md фиксирует эти границы и ссылки на первичный NumPy API.
- Scope/name-status и `git diff --cached --check` → exit 0. Код после последнего targeted run и real smoke не менялся; добавлена документация. Предыдущие 196 D/K checks относятся к неизменённым D sources; не выдаются за новый общий запуск с M1.

Далее M2: только короткие synthetic CPU optimization/resume checks; full training, fine-tune и настоящая ML evaluation остаются отложенными. Продолжение выполняется по прямому поручению человека; accepted по D3 и последующим этапам самостоятельно не выставляется.
