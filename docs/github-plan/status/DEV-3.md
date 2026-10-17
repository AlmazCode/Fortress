# Журнал разработчика №3 — ML / Данные

Рабочий процесс — Git/GitHub, без Aster. Проверка 17 октября 2026 года.
Своя ветка: `codex/fortress-no3-ml`; пакет инструкций и база этой проверки:
`c70a6d366c9b48b090368b92ca1bb60b692f6c26`.

| Task | State | Branch | Commit / PR | Проверки / блокер |
| --- | --- | --- | --- | --- |
| D1 | accepted | codex/fortress-no3-ml | 536fe7af06cadb4ff9513da1bf8dcafb6e6198e6 | Принят главным, merge 8dd2da1; software D1, training gate закрыт |
| D2 | accepted | codex/fortress-no3-ml | b4961272723cefec463d45ccb49d041afd52150b | Принят главным как draft, merge 47787cb; final taxonomy/human review не заявлены |
| D3 | review | codex/fortress-no3-ml | d0b9704b005e85675191baf0c0737b5d6da8cc49 | 48 targeted D3 tests; вместе K+D1+D2+D3 129 passed; manifest/split CLI passed |
| D4 | blocked | codex/fortress-no3-ml | — | Зависит от D3 |
| D5 | blocked | codex/fortress-no3-ml | — | Зависит от D2/D4 |
| D | blocked | codex/fortress-no3-ml | — | Зависит от D1/D5 |
| M1 | blocked | codex/fortress-no3-ml | — | Зависит от D |
| M2 | blocked | codex/fortress-no3-ml | — | Зависит от M1 |
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

## D3 — готовый кандидат

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
