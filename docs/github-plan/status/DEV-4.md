# Журнал разработчика №4 — Правила / Инфраструктура

Git/GitHub, без Aster. Своя ветка: `codex/dev4-rules-infra`. База инструкций: `c70a6d366c9b48b090368b92ca1bb60b692f6c26`, исходная база проекта: `46b7bc941e64fec5649242b8290607c8f7339819`.

| Task | State | Branch | Commit / PR | Проверки / блокер |
| --- | --- | --- | --- | --- |
| O1 | accepted | codex/dev4-rules-infra | 12acfed / 9569729, merge df1f398 | Принят главным в STATUS 2ba4272; это инвентарь, не готовность среды |
| R1 | accepted | codex/dev4-rules-infra | 95697291a879130a6b3babdedfcd959797ad68f0 | Главный принял software/missingSource; legal gate unknown |
| R2 | accepted | codex/dev4-rules-infra | 95697291a879130a6b3babdedfcd959797ad68f0 | Принят главным, merge df1f398; synthetic observations не ML validation |
| R3 | accepted | codex/dev4-rules-infra | 95697291a879130a6b3babdedfcd959797ad68f0 | Главный принял software; production cases unsupported |
| R | accepted | codex/dev4-rules-infra | 95697291a879130a6b3babdedfcd959797ad68f0 | Принят главным в программном объёме; legal/ML gate не пройден |
| O2 | blocked | codex/dev4-rules-infra | 1137423fc1de54b3d6cc5b77c2c14010e72d2ecf | CLI/env/health/scope/COPY исправлены; config и frontend native build passed; runtime не проверен, VM отложена пользователем |
| O3 | blocked | codex/dev4-rules-infra | 1137423fc1de54b3d6cc5b77c2c14010e72d2ecf | Harness и actual-API clients проверены local HTTP/TLS; нет trusted внешнего hostname/маршрута |
| O | blocked | codex/dev4-rules-infra | — | Требует O3 |
| B | blocked | codex/dev4-rules-infra | 1137423fc1de54b3d6cc5b77c2c14010e72d2ecf | По запросу подготовлены native probe/benchmark/resource tools и runbooks; actual acceptance только после I |

## O1: реально выполнено

17.10.2026: origin/rootPath/base/origin-main/HEAD ancestry проверены до исходников. Реализованы POSIX и PowerShell точки входа с одним recorder, структурированными missing/failed/timeout и Git guard до runtime/network действий. Без Python обе обёртки возвращают blocker JSON и exit 2.

- `python -m unittest discover -s tests/performance -p test_preflight_report.py -v` — exit 0, 15 тестов. Synthetic probes проверяют логику отчёта, не оборудование/ML.
- `pwsh -NoProfile -File infra/scripts/preflight.ps1 -OutputPath ../dev4-preflight-local.json -TimeoutSeconds 5` — exit 0, JSON collected, все readiness false.
- Та же команда с `-Strict` — ожидаемый exit 2.
- Git Bash `-n` для обоих shell scripts — exit 0; реальный shell preflight и network inventory — exit 0. Нерабочий MSYS Python3 не принимается за recorder; выбирается работающий Python.
- Факты хоста: Windows 11 Pro 10.0.26300; Ryzen 7 7435HS; RAM 16989736960 байт; RTX 4060 Laptop, driver 595.79, VRAM 8188 MiB. Python recorder 3.13.0. Это не целевой RTX 5060/Ryzen 5 и не другой training ПК.
- WSL не установлен, Python 3.11/Docker/Compose/FFmpeg/ffprobe/nvcc/nvidia-ctk не подтверждены. GPU container, compatibility, приложение, внешний HTTPS upload/status — not_run. Host nvidia-smi не считается CUDA/PyTorch/container readiness.
- Нет предоставленного hostname, сертификата, WAN/public данных и разрешённого incoming transport: CGNAT unknown, внешний обязательный критерий blocked. Не подключались туннели/облачная обработка и не использовались настоящие видео.

Критерии O1 1–5 покрыты Git guard, реальными command results, честным network inventory, missing-dependency tests и отсутствием train/deploy. Известные программные инструменты готовы к проверке, среда не объявлена готовой. Полные JSON с локальными путями сохранены вне Git. Подробности и первоисточники — docs/operations/PREFLIGHT.md и NETWORK_INVENTORY.md.

## K / R1–R3: собственные проверки

K `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f` интегрирован локальным merge `e35778400985f6c9fee9c5f98a3ac6d11b00e6e2`. `uv sync --locked --group test --python 3.11` выполнен в собственном окружении; CPython 3.11.17. Первая попытка managed install в стандартном uv каталоге не завершилась; повтор в отдельном dev4-python каталоге успешен. Общие pyproject/uv.lock не изменены.

`python -m pytest tests/contracts/test_schemas.py tests/rules tests/performance/test_preflight_report.py -q` в этом venv — exit 0, **88 passed, 29 subtests passed**, из них 55 tests контракта K. Pure template tests используют explicit synthetic RuleInputs, остальные — synthetic K observations. Это не валидация ML/реальной видимости.

Все C01–C15 имеют prerequisites/data/exceptions/limitations/tests. Источник только unverified нормализованная сводка предоставленного ТЗ с проверяемым hash, не оригинальный кейс и не норма. Все production findings unknown/unsupported, никакие нормативные названия, суммы/подделки/OS lock/полномочия не выдумываются. Полная неинформативность не даёт clean verdict; это должно сохраняться в pipeline I.

Session memory хранит историю ролика, дедуплицирует overlapping observations, сортирует поздние события той же сцены, разделяет scenes/jobs и не превращает score в actor ID. Absence требует явных достаточных metadata; источник и exceptions проверяются отдельно. Source frames создаёт pipeline, не rule pack.

Далее: O2 config + synthetic harness и O3 scripts. Docker/GPU runtime, volumes restart, worker egress и trusted внешний HTTPS остаются not_run/blocked до реальной среды и маршрута. Главный подтверждает интеграцию; запись не является independent/human approval.

## O2 / O3: подготовлено и проверено

Созданы Compose nginx/api/worker/redis/postgres, persistent named volumes, отдельная internal backend network, GPU reservation только worker, limits/concurrency/prefetch/threads. DB/Redis не имеют published ports; Nginx по умолчанию только 127.0.0.1:8443. Это static topology, реальная изоляция не доказана без запуска.

Образы закреплены реальными index digests из официального Docker Hub tag API; uv bootstrap — версия/hash Linux x86_64 wheel из PyPI. Python graph — исходный K lock, frontend — отдельный npm lock №2. K содержит CPU Torch wheels, поэтому production CUDA compatibility остаётся отдельным blocker до согласованного исправления №1/№3. Runtime не устанавливает пакеты/веса.

Для O3 подготовлены Nginx TLS proxy, bounded upload/timeouts, защищённые API/media proxy без direct media alias/access log; TLS/смoke scripts и отдельный explicit infra-only harness. Harness не импортирует модель/приложение, принимает только tiny synthetic marker и не выдаёт ML verdict. Local loopback HTTP tests реально проверяют 401 → upload 202 → synthetic status, wrong key, over-limit/неподдержанное тело, bound 128 records и явный запуск. Это не внешний HTTPS, Nginx/container или реальный API.

После последних изменений: `python -m pytest tests/performance tests/rules -q` в Python 3.11.17 — exit 0, **47 passed, 32 subtests passed**. Отдельно ранее 55 tests неизменённого K — exit 0. `bash -n` для shell scripts — exit 0; реальный tls-check без hostname — ожидаемый exit 2. Статические Compose тесты не объявляются `docker compose config`.

Оставшиеся обязательные проверки: Docker Compose config/build/start; настоящие GPU/CUDA/PyTorch checks; worker DB/Redis connectivity + egress; persistent volumes restart; доверенный внешний TLS upload/status; настоящий API/media путь после I; B fault/offline/capacity/deadline/benchmark после I. Сейчас они **not_run/blocked**, итог всего направления не объявлен готовым. Команды/ограничения/первичные источники — SETUP.md, NETWORK.md, PREFLIGHT.md; нормативные пробелы — SOURCES.md/CASE_SUPPORT.md.

Начатый по ошибочно указанному номеру frontend сохранён в отдельном dev2 worktree без дальнейших правок и не включён в результаты №4.

## Продолжение: совместимость с A1–A5, Compose CLI и TLS

17.10.2026: `git fetch origin` и `git pull --ff-only` — exit 0. Проверены опубликованные A1–A5 и журнал №1 на integration `cc6f29a8f6566ede9d648e4324ef91c55cd8cb94`; собственная ветка объединила их обычным merge `aa1c7a6098c4ed6c642644fe0d39b7bc5f037dc4` без конфликтов. Чужие рабочие копии не изменены. A ещё working, I blocked: финальные B проверки не начинались.

Проверенный код O2/O3: base `aa1c7a6098c4ed6c642644fe0d39b7bc5f037dc4`, head `1a1b091f091611ff56ff523daf1aebf137e343ee`. Изменены только `infra/{compose.yaml,compose.test.yaml,api.Dockerfile,worker.Dockerfile,env.example,smoke_server.py}`, `tests/performance/{test_compose_isolation.py,test_network_smoke.py}`, `docs/operations/{SETUP.md,NETWORK.md}`. Отчёт — отдельное изменение этого DEV-4 журнала; общий STATUS/manifest/audit самостоятельно не редактируются.

Исправлены три несовместимости с реальным backend: prefork вместо solo для hard deadline; local PID health вместо неработающего inspect ping при disabled remote control; обязательные явные FORTRESS_API_APP/FORTRESS_WORKER_APP вместо выдуманного Celery export. A1–A5 экспортируют factories, production assembly A/I ещё нужна. Overlay явно заменяет обе команды, поэтому test harness не запускает реальное приложение. TLS loopback больше не помечается как non-local.

Реальные проверки на неизменённом коде указанного head:

- Standalone Compose v5.6.0 `version` — exit 0. Официальный executable/hash и границы установки зафиксированы в SETUP. Только собственный локальный tooling-каталог, без установки engine/служб.
- Production и test overlay `config --quiet` с dummy env — exit 0 до изменения; после изменения итоговый JSON и ошибки отсутствующих exports проверены CLI tests. Контейнеры не запускаются, private env не читается, конфигурация с реальными secrets не печатается.
- `FORTRESS_COMPOSE_CLI=<local-compose> FORTRESS_TEST_OPENSSL=<local-openssl> .venv/Scripts/python.exe -m pytest tests/performance/test_compose_isolation.py tests/performance/test_network_smoke.py -q` — exit 0, **20 passed, 2 subtests passed**, без skipped. Python 3.11.17. Включены 3 настоящих config tests и 3 настоящих loopback TLS tests с временным self-signed сертификатом/явным private CA. TLS upload/auth/status проходят, недоверенная цепочка и неверный hostname отвергнуты до upload. Certificate/private key создаются и удаляются во временной папке, в Git их нет.
- `git diff --check` и staged diff check — exit 0. Проверено, что кандидат не меняет shared locks/contracts/backend/frontend.
- `python docs/github-plan/validate_plan.py` — **exit 1**: manifest ожидает старый hash `status/DEV-4.md`, saved AUDIT отличается после изменения журнала. Граф 36 задач/48 рёбер ацикличен, ownership overlap отсутствует. Это не application test failure и не pass документационного audit. Следующее действие №1 при приёмке: проверить/обновить общий manifest и audit штатным workflow; №4 не присваивает эти общие файлы.

Ограничения прежние: Docker engine/WSL отсутствуют, runtime/GPU/offline/volumes и публичный HTTPS не проверены; local private-CA TLS не доказывает внешний маршрут. B ожидает принятый I. Нормативные sources и original case/jurisdiction не появились: R остаётся unknown/unsupported. Подготовка и push своей ветки не означают accepted или финальную сдачу.

## Принятый A и исправления по возврату O2/O3

После нового `git fetch origin` проверен STATUS `2ba4272`: главный принял O1 и программный объём R1–R3/R, merge `df1f398d14367fddc5621f613280115f8df19ff3`. Таблица выше отражает эту опубликованную приёмку, не новую собственную. A принят в `043eeb6d125f3b77d71b74de3b56c6a1cee91e70`. Все эти изменения объединены в своей ветке merge `5754d22292a80fb1006c78f59ce8dba237b1075d` без конфликтов и правок чужих checkout.

Base исправлений `5754d22292a80fb1006c78f59ce8dba237b1075d`; проверенный code head `3cee7531746927cd035b4c4e51e522f150990dbd`. Изменены `infra/{compose.yaml,api.Dockerfile,worker.Dockerfile,env.example}`, `tests/performance/test_compose_isolation.py`, `docs/operations/{SETUP.md,NETWORK.md}`. Внеплановый собственный `infra/.gitattributes` удалён по review; shared settings/locks/contracts не менялись.

Замечания review 1–5 исправлены в собственном scope: поддерживаемый `python -m backend.app.main api/worker` вместо guessed exports; prefork/concurrency/limits берутся из принятого backend CLI; local process health вместо disabled remote control; полный Settings env, включая API key у worker; явный порядок DB/Redis → migrate → остальные services. Общий key остаётся private environment, не build argument. Health проверяет PID 1/argv при NOSETPS=1; это только liveness, не модель/queue readiness. Замечание 6 о настоящем runtime/external HTTPS остаётся blocker.

Фактические проверки:

- `FORTRESS_COMPOSE_CLI=<local-compose> .venv/Scripts/python.exe -m pytest tests/performance/test_compose_isolation.py -q` — exit 0, **10 passed, 2 subtests passed** на неизменённом коде указанного head. Настоящий Compose v5.6.0 config, production/test resolved commands/networks/GPU reset, обязательный Settings env, принятые Celery defaults. Контейнерного запуска нет.
- `preflight.ps1 -OutputPath <local-report> -TimeoutSeconds 5` с собственным Python 3.11 venv первым в process PATH — exit 0, collected, recorder 3.11.17, python311_ready=true; os/docker/compose/ffmpeg/toolchain/service/gpu/external readiness=false. Standalone Compose хранится отдельно и не выдаётся за работающий Docker plugin/engine. Сырые отчёты остаются вне Git.
- С разрешения пользователя скачан официальный Docker Desktop 4.95.0 build 242831. SHA-256 и Authenticode Valid/Docker Inc проверены до запуска; полные значения/официальные ссылки в SETUP.
- Реальный per-user installer `install --user --quiet --accept-license --backend=wsl-2 --no-windows-containers` — **exit 1** на prerequisite check: выключен VirtualMachinePlatform, для включения нужны administrator privileges. Текущий процесс не elevated; Docker не установлен. Не пытались обходить Windows permission gate. Пользователю сообщён требуемый шаг admin PowerShell `wsl --install --no-distribution` и последующая перезагрузка. После вопроса «зачем» объяснено, что компонент нужен для Linux containers только на ПК развёртывания; решение о ПК/системном шаге ещё не получено.
- `git diff --check` / staged check — exit 0. Новые code changes прошли targeted checks; прежние успешные loopback TLS и rules tests не повторялись без изменения их кода.

Оставшиеся O2/O3/O/B не закрыты. Следующее действие: выбранный runtime PC с engine/WSL2 → build/start, worker connectivity/egress и volumes; подтверждённый внешний HTTPS; B только после принятого I. Правила остаются юридически unknown до original case/jurisdiction/normative sources. Локальный поиск предоставленного case в текущем workspace файла не нашёл; чужие материалы/разметка не изменялись. Общий manifest/audit после изменения DEV-4 журнала по-прежнему обновляет №1 при review, не №4.

## Продолжение по указанию «пока без виртуалки, доделывай оставшиеся задачи»

Актуальный user constraint: WSL/VirtualMachinePlatform/виртуализация отложены; системные компоненты и Docker повторно не устанавливались, перезагрузка не выполнялась. По прямому поручению подготовлены оставшиеся переносимые инструменты до приёмки I, без изменения графа/присвоения B accepted. Native Windows выполняет frontend build, client HTTP/TLS и RSS sampler. Полный текущий worker требует native Linux/POSIX; Windows portability не подменяется solo или новым in-memory backend в чужой области.

Получен и просмотрен integration `6b16272fded945668b8997498faa0b2d83a541a0` с принятыми F/D2; объединён в собственной ветке merge `56da971759ddccc8a809a77510b8174723628f18`. I ещё blocked по M/O. Base кандидата — этот merge, проверенный code head `1137423fc1de54b3d6cc5b77c2c14010e72d2ecf`. Изменены только 10 собственных файлов O/B: frontend.Dockerfile, smoke.sh, benchmark.py, test_https.py, test_capacity_deadline.py, test_service_resources.py, SETUP/NETWORK/BENCHMARK/RECOVERY. ACCEPTANCE.json и этот журнал — отдельный итоговый отчёт.

Закрыто ещё одно реальное замечание O2: frontend build stage теперь копирует `/contracts` рядом с `/frontend`. Reproduced COPY layout в отдельной новой tooling-папке, `npm ci --ignore-scripts --no-audit --no-fund` + `npm run build` — exit 0, typecheck и production build успешны, Node 22.22.2, 173 modules. Это не Docker build; frontend source/lock №2 не изменялись.

Добавлен настоящий portable API client: production auth/model gate либо explicit synthetic upload → public/UI status → original SHA/preview/JPEG. Строгий K, тот же job ID/пути, wrong/missing key, отказ redirect, TLS verification, multipart streaming, bounded input/response, absolute deadline и slow-drip защита. Reports create-only до запросов, без keys/private paths/media. Warmup исключается из nearest-rank p95; failed/unknown не clean verdict. Внутренние server-stage timings и model memory остаются null — K не отдаёт такую telemetry.

Отдельный native resource sampler читает только operator-specified PID/children: Windows WorkingSet64 или Linux statm RSS в bytes, worker VRAM из nvidia-smi в MiB. Частичный scope не даёт общей service RAM; N/A/отсутствие PID/query не становятся нулевой VRAM. Observed max не называется гарантированным peak, scope/job correlation не присваиваются автоматически. Тесты действительно измеряют память собственного pytest процесса; это не RAM сервиса.

Итоговая проверка неизменённого кода head `1137423`: `FORTRESS_COMPOSE_CLI=<local-compose> FORTRESS_TEST_OPENSSL=<local-openssl> .venv/Scripts/python.exe -m pytest tests/performance tests/rules -q --tb=short` — **exit 0, 78 passed, 50 subtests passed, 0 skipped**, 45.13s, CPython 3.11.17. Bash syntax и реальный smoke.sh --help — exit 0. `git diff --check` / staged check — exit 0. Дополнительные unchanged checks не повторялись после этого результата.

При разработке HTTP tests сначала воспроизведён дефект нового клиента с Connection: close на Windows (закрытый socket handle), исправлен bounded response-reader socket + read1; затем все проверки прошли. Fixture сначала использовал неверный `not_found`: строгий K выявил это. Сравнение с A показало тот же literal в backend/app/api.py, media.py и main.py. **Передача №1:** заменить на contract job_not_found/media_not_found с проверкой HTTP/body; №4 не меняет backend/contracts и не ослабляет client. Это статически подтверждённое несоответствие и HTTP protocol regression, не live API проверка A на Windows.

Полный machine-readable итог — docs/operations/ACCEPTANCE.json. O2/O3/O/B остаются blocked по настоящему runtime/offline/volumes, внешнему HTTPS, I и server timing trace. Recovery/fault/capacity actual full-stack не выполнялись; новые parser/protocol/sampler tests ими не считаются. Training/independent ML evaluation не запускались, реальные latency/VRAM/RAM модели not measured. Общий manifest/audit изменяет №1 при проверке этого журнала.

## Повторная передача на review — 18 октября 2026

`git remote -v`, status/root/base guard, `fetch origin`, `pull --ff-only` — exit 0. Получен свежий integration `bfff45447f74a5263b1d728e05ebb41490d91b58`. Проверены текущие AGENTS/WORKFLOW/PLAN/REQUIREMENTS, своё ТЗ и review №1 `c00516e3e5e8bc08c0ba96a4cb24b0048178068f`: инструкции/граф относительно своей ветки не изменились. Review главного относится к code `3cee753` / report `b679dc7`, а не к уже опубликованным `1137423` / `8aee9d1`.

Принятые зависимости подтверждены через `git cat-file -t` и `git merge-base --is-ancestor` отдельно для integration и собственного HEAD; каждый exit 0:

| Результат | Точный SHA |
| --- | --- |
| K | 2e44bf555ad1a824d92e73770a1ee85d1bf20d0f |
| A | 043eeb6d125f3b77d71b74de3b56c6a1cee91e70 |
| F | c9317918fad3e3cb8bfccf0d76b6dc4de695ccfc |
| F merge | c6d15d5feade48abfcde81207c818510344445a9 |

Fresh integration объединена обычным merge `8a4cf759095adfa59090536ca7cf83a2932c4726` — exit 0; пришли только 4 документа №1/№2, исполняемый код не изменился. Код backend в integration побайтно соответствует принятому A; frontend в своей ветке — принятому F. Девять наборов Git objects (`infra`, `rules`, `tests/performance`, `tests/rules`, `backend`, `frontend`, `contracts`, pyproject и uv.lock) сравнивались с `1137423fc1de54b3d6cc5b77c2c14010e72d2ecf`: все OID идентичны, exit 0. Дельта относительно integration — 27 разрешённых файлов №4, вне scope нет, exit 0. Полные object IDs и перечень путей сохранены в ACCEPTANCE.json.

Поэтому 78 passed / 50 subtests / 0 skipped, настоящий Compose config, private-CA loopback TLS, native RSS tests и frontend COPY-layout build сохраняются как доказательства **выполнения 17 октября на коде 1137423**. Они не повторялись без изменения кода и не переименованы в новый runtime прогон. Текущая дата оценки и дата исполнения checks в JSON явно разделены. COPY contracts остаётся исправленным в 1137423, старые :app/:celery_app exports/solo/remote-control ping не возвращались.

Замечание 404 воспроизведено заново без изменения backend. Из настоящего AST `backend/app/api.py:18` взяты literal arguments для IntakeError(404, not_found, ...), вызван настоящий `backend.app.storage.IntakeError.payload()`, затем настоящий K validator. Получен **ожидаемый exit 1**, diagnostics schema отвергает error.code=not_found. Это actual serializer/schema reproduction, а не live API/DB/Windows worker. Для №1 минимальное воспроизведение в locked Python environment:

```sh
python -c 'from backend.app.storage import IntakeError; from contracts.python_ports import validate_contract; validate_contract("diagnostics", IntakeError(404, "not_found", "Job is unavailable.").payload())'
```

Ожидается ContractError / exit 1. Исправление job_not_found/media_not_found и HTTP/body regression остаётся владельцу backend; клиент и K не ослаблены.

Пользователь сообщил, что технический выбор делегирует, но конкретный runtime-хост и внешний URL не предоставил. Выбран уже согласованный K stack: browser на Windows, сервер на существующем разрешённом native Linux x86_64 компьютере с доступным Linux container engine. Это не новый облачный сервис и не включение виртуализации на текущем ПК. Физический runtime-хост/способ подключения пока не подтверждены; адрес/маршрут не выдумываются. Дополнительных технических настроек от пользователя для review кода сейчас не требуется.

Минимальные условия фактического завершения:

1. **O2:** разрешённый Linux runtime-хост и способ доступа; работающий доступ к Docker engine/Compose; отдельные persistent test roots/private env. Затем настоящие build/start/migrate, worker DB/Redis connectivity плюс запрет egress и volumes/restart; GPU compatibility проверить реально, CPU lock её не доказывает. Review №1 зафиксировал permission denied для своего Linux engine, а не успешный запуск; это не исправляется native client tests на Windows.
2. **O3:** работающий O2 endpoint, разрешённый входящий HTTPS-маршрут, hostname/DNS, соответствующий доверенный TLS, внешний клиент вне сети сервиса. Затем фактические auth/upload/poll/media проверки. Local private CA/TLS не подтверждают внешнюю доступность.
3. **O:** закрытые фактические O2/O3, а не только опубликованный кандидат. **B:** отдельно после принятого I с реальным full-stack fault/recovery/capacity/deadline прогоном. R остаётся software accepted / legal unknown/unsupported.

В этом продолжении изменены только ACCEPTANCE.json и собственный DEV-4 журнал; executable code `1137423` сохранён. Общие STATUS/manifest/audit не редактировались. Реальный Docker/worker/volumes/recovery и внешний HTTPS по-прежнему not_run/blocked; WSL/VirtualMachinePlatform не включались, Docker повторно не устанавливался, перезагрузки не было.

## Проверка runtime и инструкция для релиза — 18 октября 2026

После нового поручения подтверждён `origin`, root/base и чистая ветка №4; fetch — exit 0. Актуальные инструкции/ТЗ и review главного прочитаны. Свежая integration `69f2a3835a3b9964f8fc03922ea7da5ff03e9aa5` получена через fast-forward — exit 0. Пришли только уже интегрированные главным изменения; №4 backend/ML/общие документы самостоятельно не правил. Принятые K `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`, A fix `c46a2c005e2882c0c794bc44cecb7ff3cc393d13`, F `c9317918fad3e3cb8bfccf0d76b6dc4de695ccfc` и infra code `1137423fc1de54b3d6cc5b77c2c14010e72d2ecf` подтверждены объектами/ancestry integration и HEAD — каждый exit 0.

404 больше не открытый backend blocker: из свежего AST api/media проверены все шесть literal 404 calls через настоящий IntakeError.payload и строгий K validator — exit 0, только job_not_found/media_not_found. Предыдущий exit-1 repro относится к старому A; клиент/контракт не ослаблены. Восемь наборов infra/rules/tests/frontend/contracts/locks идентичны 1137423; backend изменён принятым c46a2c0, поэтому старое утверждение о девяти идентичных objects не переносится на новый HEAD. Native tests/build сохраняют фактическую дату 17 октября; полный runtime этим не подтверждён.

На текущем Windows реально выполнены:

| Проверка | Exit | Наблюдение |
| --- | --- | --- |
| Standalone Compose 5.6.0 version | 0 | Только CLI |
| Тот же Compose `ls --format json` | 1 | Engine npipe docker_engine отсутствует; соединение не установлено |
| preflight.ps1 -Strict с собственным Python 3.11 | 2 | service/gpu/docker/compose/toolchain readiness false, Python 3.11 true |
| nvidia-smi host query | 0 | RTX 4060 Laptop, driver 595.79, 8188 MiB; не target RTX 5060 и не container CUDA |
| Native test venv `import torch` | 1 | ModuleNotFoundError; ML extra не установлен в этом venv, не GPU/runtime тест |

Docker/Podman CLI, Docker service/pipe, Docker contexts/config/DOCKER_HOST и SSH config в проверенных стандартных местах отсутствуют. Общий K source pyproject/lock остаётся CPU Torch: даже доступный engine не заменяет согласованный CUDA lock. Запись чужого shared lock не выполнялась. Пользователь сообщил о другом компьютере, затем **отложил предоставление доступа** и поручил записать инструкцию запуска для релиза; дальнейших вопросов о доступе сейчас нет.

По этому прямому поручению добавлен `docs/operations/RELEASE.md` (новый документ в собственной operations-области): Linux/Windows роли, engine prerequisites, точный checkout, private env/key generation, local TLS, отдельный harness build/start, worker network/TCP probes, PostgreSQL/Redis/media/models markers и restart, gated application migration/GPU tensor check, внешний trusted TLS/upload/status, остановка/backup и текст будущих release notes. Новый путь добавлен по текущему указанию пользователя, прежний plan.json не менялся. SETUP ссылается на него, использует исправленный A и больше не содержит активных команд включения WSL; BENCHMARK отмечает закрытие старого 404. [Публичная страница GitHub Releases](https://github.com/AlmazCode/Fortress/releases) при проверке не содержит выпусков; tag/Release/deploy не создавались. Инструкция подготовлена для включения главным в будущий релиз.

Проверка новых команд документа: все **11 Bash blocks — bash -n exit 0**, **5 Python snippets — compile exit 0**, фактически исполненный private-env generator — exit 0. С его временным env настоящий Compose `config --quiet` прошёл для production и harness — оба exit 0. Это синтаксис/настройки инструкции, не исполнение её container/SQL/restart/GPU/внешних шагов. Локальные raw JSON/checkpoints находятся вне Git, secrets не публиковались.

Итог: **O2/O3/O blocked**, actual build/start, worker PostgreSQL/Redis/egress, volumes/restart, container GPU/CUDA и trusted external HTTPS not_run. B остаётся после принятого I, R — software accepted/legal unknown. Следующее действие: когда пользователь предоставит доступ к другому разрешённому хосту и внешний маршрут, выполнить RELEASE.md и заменить not_run фактическими exit codes/артефактами. До этого установщики, WSL/VM и перезагрузка не выполняются; main/force-push/новые чаты не затронуты. Общий manifest/audit обновляет №1 при review нового журнала.

## Docker access denied и scope TLS-диагностики — 18 октября 2026

Новое поручение: выяснить Docker access denied и исправить проблемы HTTPS. Origin/root/base/clean checkout проверены; fetch и fast-forward на актуальную integration `ecce7c2126e8e99e7dea3baff3af7b15b4391891` — оба exit 0. Пришли только четыре shared документа главного. Собственные изменения по-прежнему в своей infra/tests/operations области и DEV-4, без backend/contracts/locks/main.

Разделены **два разных хоста**. `/var/run/docker.sock: permission denied`, exit 1 — наблюдение №1 на его Linux, сохранённое в DEV-1/STATUS. №4 к этому Linux не подключён и его actual группы/ACL/ограничения не проверял. Новый прямой probe №4 на Windows (`standalone Compose ls --format json`) — exit 1, **отсутствует** `npipe docker_engine`; это не тот же permission denied. Docker/Podman/service/context/DOCKER_HOST и внешнего URL на текущем хосте не обнаружено. Другой ПК пользователь ранее подтвердил, доступ отложил; нового адреса/способа входа не предоставлено. Системные permissions не менялись.

Найден и исправлен настоящий дефект tooling: `preflight --network-only`, используемый tls-check.sh, всё равно вызывал полную OS/WSL/Docker/GPU inventory и включал несвязанные blockers в HTTPS report. **Код `d5eb6eff26ffd8039939270b99c8ec6dec12a7e1`** останавливает collect после repository guard + network/TLS inventory; в network-only JSON только network blockers. Strict CA/hostname verification, repository binding и `external_access_verified=false` сохранены. Full preflight не ослаблен. Добавлены regressions: никаких runtime probes даже при переданных GPU flags; mismatch repository не открывает TLS; CLI missing URL/valid TLS/certificate failure сохраняет правильные exits и scope.

Фактические проверки изменённого кода:

- `.venv/Scripts/python.exe -m pytest tests/performance/test_preflight_report.py -q --tb=short` — **exit 0, 21 passed, 3 subtests, 0 skipped**, 1.86s.
- Настоящий `bash infra/scripts/tls-check.sh` против временного native loopback TLS server: нет URL — **exit 2/not_run**, с process-local private CA — **exit 0/ok**, недоверенная цепочка — **exit 2/failed**, несовпадение hostname — **exit 2/failed**. Во всех четырёх actual CLI reports отсутствуют Docker/OS/GPU blockers, external_access_verified=false. CA не устанавливался в систему, secrets/certs временные вне Git. Это TLS CLI проверка, не Nginx/внешний upload/status.
- Новые 14 Bash blocks RELEASE.md — `bash -n`, **exit 0**. Реальные OpenSSL команды публичного ключа/DER/SHA проверены на временной локальной паре: совпадающий ключ подтверждён, чужой ключ обнаружен. Выпуск публичного сертификата не выполнялся.

Для exact code provenance проверены Git blobs прошедших тесты файлов: preflight `f64f4b7666bd3fc648dc0d2c60eca6357b979c2d`, test `4ef0c781ececd1f2501fd29b11ceb462db0a32d7`; committed и working совпадают. Старые 78/50 native checks остаются историческим прогоном 17 октября на 1137423; изменённый preflight проверен заново указанным targeted suite и настоящим CLI.

RELEASE.md теперь содержит условную процедуру Linux socket/groups/context/login по [официальному Docker post-install](https://docs.docker.com/engine/install/linux-postinstall/) и [существующему rootless runtime](https://docs.docker.com/engine/security/rootless/). Для HTTPS добавлены раздельные DNS/route/firewall/bind/CA/hostname/key-pair/upstream проверки и условия DNS-01/HTTP-01 по [Let's Encrypt](https://letsencrypt.org/docs/challenge-types/). Непредоставленный hostname отмечен **not_configured/not_run**, не как наблюдённая certificate failure. Не использованы chmod666, незащищённый Docker TCP, отключение TLS verification или произвольный туннель.

Программная диагностика исправлена; **реальные права Linux Docker и внешний HTTPS не объявляются исправленными** без подключения к тому хосту и настоящего endpoint. O2/O3/O blocked; actual build/start, DB/Redis + egress, volumes/restart, container CUDA, внешний upload/status не выполнены. B — после принятого I, R — software/legal unknown. Runtime host access и hostname/route/TLS остаются конкретными недостающими условиями. ACCEPTANCE.json содержит новые exit codes и exact code SHA; общий manifest/audit по-прежнему обновляет №1.

## Windows Docker/WSL2: новое разрешение и фактическая установка — 18 октября 2026

Пользователь поручил Docker на Windows/GPU/CUDA/внешний доступ и **явно разрешил WSL2 для Docker/GPU**, отменив прежний запрет. Автоматическую перезагрузку не разрешал; она не выполнялась. Также подтвердил домашнюю сеть/свой роутер и отдельно согласился на api.ipify.org + бесплатный sslip.io + Let's Encrypt с раскрытием публичного IP/имени этим сервисам. Новых платных ресурсов/учётных записей/туннелей не создавалось. Контейнеры остаются Linux; native Windows POSIX worker не заявляется.

Fetch после разрешённой network escalation и fast-forward — exit 0; свежая integration **469b2eb841de187d8e3429dc17514254777d3bdc**. Принятые K/A/F и новый ML fix **c68ae819d38cd14b97921c9c76ed1a4b92d89cc8** подтверждены objects/ancestry — exit 0. M4/M теперь software accepted по review №1; I всё ещё blocked по O. №4 не менял ML/backend/contracts/shared locks; пришедшие чужие изменения только из принятой integration.

Фактическая среда: Windows 11 Pro build 26300, Ryzen 7 7435HS, BIOS virtualization true, HypervisorPresent true; host RTX 4060 Laptop/595.79/8188 MiB. Не подменять этим target RTX 5060/CUDA execution evidence. Официальные основания прочитаны: [Docker Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/), [Docker GPU/WSL2](https://docs.docker.com/desktop/features/gpu/), [Microsoft WSL](https://learn.microsoft.com/en-us/windows/wsl/install), [WSL 3.0.3 release](https://github.com/microsoft/WSL/releases/tag/3.0.3).

Через UAC запущен отдельный локальный helper (вне Git), включающий **только** VirtualMachinePlatform и Microsoft-Windows-Subsystem-Linux с All/NoRestart. Оба Disabled -> Enabled, оба RestartNeeded=true; result status restart_required. Затем:

| Действие/проверка | Реальный результат |
| --- | --- |
| Microsoft WSL 3.0.3 x64 MSI | SHA-256 ae977286974255bd26bf925f00f40f5692c6b2084155cbc0563c09aea091f211, Valid Microsoft signature; /qn /norestart REBOOT=ReallySuppress; installer **exit 0** |
| Docker Desktop 4.95.0 build 242831 | Ранее проверенный hash 73431db38491f770543880366228a23c993f84d1e8e045f56d83b8a98940cf76 и Valid Docker signature; install --user --quiet --accept-license --backend=wsl-2 --no-windows-containers; installer **exit 0**, app present |
| wsl --version | **exit 0**, WSL 3.0.3.0, kernel 6.18.54.1-1 |
| Docker CLI --version | **exit 0**, 29.8.2 |
| Installed docker compose version | **exit 0**, 5.6.0 |
| Первый docker version --format Server | **exit 1**, Docker Desktop is unable to start |

Docker Desktop запущен в фоне. Его собственный backend log уточняет причину: `checking preconditions: Virtual Machine Platform not enabled; No virtualization available`. Компоненты уже Enabled, но Windows сообщила обязательную перезагрузку; активация ещё не выполнена. Это **не** прежний Linux docker.sock permission denied и не повод повторять installers/менять BIOS при наблюдённом virtualization=true.

Подготовлены закрытые реальные env/API key/DB password/local TLS/каталог отчётов для **отдельного** Windows infrastructure harness, всё вне Git. Самоподписанный сертификат только для loopback, в системное trust store не устанавливался. Настоящий установленный Compose с этим private env: production config --quiet и harness config --quiet — оба **exit 0**, secrets не печатались. Новые 3 PowerShell blocks в RELEASE.md прошли Parser — **exit 0**. Executable code d5eb6ef и его прежние tests не менялись/не перезапускались без причины; текущие изменения только operations docs/ACCEPTANCE/DEV-4.

Внешняя сеть: первоначальный ipify-запрос отклонён automatic approval review из-за раскрытия публичного IP без отдельного согласия; он не выполнялся. После явного ответа пользователя именно на api.ipify.org/sslip.io/Let's Encrypt повторный запрос разрешён и выполнен. Публичный IP/предложенный hostname сохранены **только локально**, DNS совпадает с наблюдаемым публичным IP. UPnP collection недоступна; локальные TCP 80/443/8080 выбранного gateway не отвечают, WAN/router IP не сопоставлен, CGNAT unknown. Port forwarding/firewall не менялись. Публичный сертификат не выдан; внешний TLS/upload/status не выполнялись. DNS resolution не считается разрешённым входящим маршрутом.

RELEASE/SETUP/NETWORK/RECOVERY теперь отражают новое разрешение и реальную установленную Windows/WSL2 конфигурацию, а не прежний запрет. В RELEASE добавлены: post-reboot engine checks, подготовка NVIDIA nbody image с фиксацией digest и bounded CUDA benchmark без сети, отдельный PowerShell Compose harness. Windows NVIDIA driver используется в WSL; отдельный Linux display driver не устанавливался. App GPU остаётся отдельным gate: K lock CPU-only, его №4 не подменял.

**Далее:** контролируемая пользователем перезагрузка, затем фактические Docker engine/NVIDIA CUDA sample/build/start, worker PostgreSQL/Redis + deny egress и persistent volumes/restart. Для O3 подтвердить WAN/router route, выпустить доверенный сертификат на согласованный private hostname и выполнить независимый внешний smoke. Пока **O2/O3/O blocked**; B после принятого I; R software/legal unknown. Установка CLI/WSL не заменяет runtime acceptance. Checkpoints, installer logs, private env и pending-start данные сохранены вне Git; общие STATUS/manifest/audit ведёт №1.
