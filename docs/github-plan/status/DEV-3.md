# Журнал разработчика №3 — ML / Данные

Рабочий процесс — Git/GitHub, без Aster. Проверка 17 октября 2026 года.
Своя ветка: `codex/fortress-no3-ml`; пакет инструкций и база этой проверки:
`c70a6d366c9b48b090368b92ca1bb60b692f6c26`.

| Task | State | Branch | Commit / PR | Проверки / блокер |
| --- | --- | --- | --- | --- |
| D1 | review | codex/fortress-no3-ml | 536fe7af06cadb4ff9513da1bf8dcafb6e6198e6 | 9 targeted tests + реальный inventory/CPU CLI passed; ожидает проверки главного |
| D2 | ready | codex/fortress-no3-ml | База K 2e44bf555ad1a824d92e73770a1ee85d1bf20d0f | K получен, интегрирован и проверен |
| D3 | ready | codex/fortress-no3-ml | База K 2e44bf555ad1a824d92e73770a1ee85d1bf20d0f | K получен, интегрирован и проверен |
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
