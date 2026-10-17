# Fortress — действующий план GitHub

> **С 17 октября 2026 года проект перешёл с Aster на обычный Git/GitHub. Aster MCP, регистрации, claims, leases, heartbeat и сигнал запуска для координации больше не используются.** Источник задач — `plan.json`, исходников и результатов — Git. Слова lease/fencing в backend-коде относятся к надёжности заданий и сохраняют технический смысл.

Сохранены 36 задач и 48 прямых зависимостей. Распределение: №1 — 9, №2 — 6, №3 — 12, №4 — 9. Полные рабочие правила: [WORKFLOW.md](WORKFLOW.md). Проверка миграции: [AUDIT.md](AUDIT.md). Состояние реализации — unverified до сверки фактических commits.

| ID | Задача | Разработчик | После |
| --- | --- | --- | --- |
| O1 | Среда и внешний маршрут | №4 | — |
| K | Контракт API и данных | №1 | — |
| A1 | БД и состояние заданий | №1 | K |
| A2 | Приём и проверка видео | №1 | K |
| A3 | Авторизация и медиа | №1 | K |
| A4 | Outbox и один worker | №1 | A1 |
| A5 | Дедлайны и сбои backend | №1 | A2, A3, A4 |
| A | API и надёжная очередь | №1 | A5 |
| F1 | Клиент API и ключ | №2 | K |
| F2 | Загрузка и статусы | №2 | F1 |
| F3 | Видео и доказательства | №2 | F1 |
| F4 | Ошибки и доступность UI | №2 | F1 |
| F | Интерфейс анализа | №2 | F2, F3, F4 |
| D1 | Аудит данных и среды | №3 | K |
| D2 | Классы и инструкция разметки | №3 | K |
| D3 | Импорт и split без утечки | №3 | K |
| D4 | Кадры и клипы по PTS | №3 | D3 |
| D5 | Разметка объектов и событий | №3 | D2, D4 |
| D | Данные и preflight | №3 | D1, D5 |
| M1 | Preprocessing и кэш | №3 | D |
| M2 | GRU и CPU train/resume | №3 | M1 |
| M3 | Оценка и экспорт пакета | №3 | M2 |
| M4 | Loader и inference adapter | №3 | M3 |
| M | ML CLI и загрузка release | №3 | M4 |
| R1 | Кейсы и нормативные источники | №4 | K |
| R2 | Память ролика и связей | №4 | K |
| R3 | Правила и сложные примеры | №4 | R1, R2 |
| R | Правила и источники | №4 | R3 |
| O2 | Compose и offline worker | №4 | K |
| O3 | TLS и внешний smoke | №4 | O1, O2 |
| O | Compose и доступ по HTTPS | №4 | O3 |
| I | Интеграция без весов | №1 | A, F, M, R, O |
| U | Браузерная приёмка | №2 | I |
| E | Передача ML-инструментов | №3 | I |
| B | Восстановление и benchmark | №4 | I |
| Z | Финальная сдача | №1 | U, E, B |

K и O1 — независимые корни. После K соответствующие API/UI/data/rules/infra задачи могут идти параллельно. №4 начинает O1 рано и чередует только собственные готовые задачи R/O. Общая интеграция I ждёт A/F/M/R/O; U/E/B ждут I; Z ждёт U/E/B. Отсутствие настоящих весов не заменяет обязательные software/network проверки.

## O1 — Среда и внешний маршрут

Разработчик №4. Фаза: implementation. Зависимости: нет.

Проверяемый результат: ранний аппаратный/сетевой инвентарь и воспроизводимые preflight команды; может идти параллельно контракту K.
Исходы: success: Известны реальные возможности/пробелы и путь проверки инфраструктуры. | missingTool: Нет Docker/FFmpeg/Python3.11 — список необходимых условий, не фиктивный pass. | gpu: CUDA/GPU не подтверждены — gpu_ready=false, CPU tooling можно готовить. | cgnat: Нет входящего пути/CGNAT — external_access_blocked до реального разрешённого маршрута. | externalPC: Другой training PC недоступен — handoff instructions готовы, hardware not verified.

### Разрешённые файлы

- `infra/scripts/preflight.sh`
- `infra/scripts/preflight.ps1`
- `infra/scripts/network-check.sh`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`

### Критерии приёмки

1. До чтения исходников проверены origin/main/base/rootPath своей копии. Команды только собирают факты, не меняют ключ/проект/репозиторий.
2. Ubuntu/WSL2, Python3.11, Docker/Compose, FFmpeg/ffprobe, NVIDIA toolkit, драйвер/CUDA/GPU/RAM/VRAM указаны фактическим output; наличие команды не считается работающим runtime.
3. В первые два часа проверяются входящий маршрут/домен/сертификат/CGNAT и допустимый транспорт, без настоящих видео и без скрытого облачного переноса.
4. Отсутствующее оборудование/другой ПК/программа имеет конкретную причину и readiness=false. Сам preflight CLI должен корректно работать и при отсутствии зависимостей.
5. Preflight не запускает training/deploy и не объявляет внешнийHTTPS успешным; фактический внешний smoke после настройки в O3.

### Исходы и блокировки

- **success**: Известны реальные возможности/пробелы и путь проверки инфраструктуры.
- **missingTool**: Нет Docker/FFmpeg/Python3.11 — список необходимых условий, не фиктивный pass.
- **gpu**: CUDA/GPU не подтверждены — gpu_ready=false, CPU tooling можно готовить.
- **cgnat**: Нет входящего пути/CGNAT — external_access_blocked до реального разрешённого маршрута.
- **externalPC**: Другой training PC недоступен — handoff instructions готовы, hardware not verified.

## K — Контракт API и данных

Разработчик №1. Фаза: contract. Зависимости: нет.

Проверяемый результат: единый public/UI/data/release контракт, модульные порты и ownership для36 этапов. Исходные требования и внешняя jury схема сохранены; taxonomy пока draft. Прочитать объединённое ТЗ, фактические приложения и официальные API. Достаточность исследования: каждое независимое направление знает inputs/outputs/errors/versions/files и способы проверки. Отсутствующие25 классов/исходный кейс не выдумывать. Baseline и запрет training/cloud/face/audio сохраняются.
Исходы: success: Контракты/schema fixtures/ownership проходят проверки, можно принять K и открыть leaves. | missing: Неизвестная taxonomy/норма/данные — draft/unknown с точным пробелом; UI/API остаются определимыми. | failure: Противоречивый public/schema/module контракт — blocked до исправления K.

### Разрешённые файлы

- `contracts/openapi.yaml`
- `contracts/job.schema.json`
- `contracts/diagnostics.schema.json`
- `contracts/events.schema.json`
- `contracts/manifest.schema.json`
- `contracts/annotations.schema.json`
- `contracts/release.schema.json`
- `contracts/taxonomy.draft.json`
- `contracts/fixtures.json`
- `contracts/OWNERSHIP.md`
- `contracts/DEPENDENCIES.md`
- `contracts/STACK.md`
- `tests/contracts/test_schemas.py`
- `docs/operations/LOCAL_ARTIFACTS.md`
- `config.example.toml`
- `contracts/__init__.py`
- `contracts/python_ports.py`
- `contracts/objects.schema.json`
- `contracts/dataset_readiness.schema.json`
- `contracts/OUTCOMES.md`
- `pyproject.toml`
- `uv.lock`

### Критерии приёмки

1. Зафиксированы origin/main/baseCommit 46b7bc941e64fec5649242b8290607c8f7339819, rootPath='', проектный корень и точные files всех четырёх ролей; общий файл не редактируется параллельно.
2. POST /api/v1/analyze принимает X-API-Key и multipart file, возвращает 202 {job_id} только после сохранения; GET /api/v1/jobs/{job_id}: processing/done/failed, queued/running остаются внутренними.
3. Публичная схема done содержит verdict violation/no_violation и violations; violation ⇔ violations непуст. События имеют type,timecode_sec,description,evidence_frames[{timestamp_sec,image_base64}]; 1–3 подлинных JPEG без data-префикса. Никакие UI-поля не добавляются во внешний контракт жюри.
4. Отдельно описаны защищённые /api/ui/v1/jobs/{job_id}, /api/ui/v1/model и media/preview endpoints: интервалы, стадии, источники, версии, unknown/unsupported и ограничения. UI ключ хранится в памяти вкладки, fetch с заголовком, Blob видео до 200 МиБ с освобождением Object URL; ключ не попадает в bundle, URL, storage или логи.
5. Схемы фиксируют ошибки 400/401/404/413/415/429/503, model_not_ready до принятия анализа, failed с причиной после приёма; лимиты 200 МиБ/180 с/1920×1080 либо 1080×1920/60 fps, VFR/rotation/исходные PTS и отсутствие облака, audio и face recognition.
6. Внутренний ActionTimeline содержит интервалы исходного времени, scores, visibility/known masks, scene_id и unknown actor/relations; RuleFinding = triggered/not_triggered/unknown с source provenance. Политика неполной наблюдаемости не превращает unknown в доказательство отсутствия нарушения.
7. Release schema требует checkpoint, backbone/config/feature_dim, taxonomy, preprocessing, thresholds, metrics/model card, dataset/split/annotation/rules versions и SHA-256 manifest. Untrained/test fixtures несовместимы с production readiness; без release 503. Draft taxonomy не изображает известные 25 классов.
8. Согласованы manifest/annotation/split formats, ключ кэша preprocessing+encoder+dataset, frozen encoder+GRU baseline и пример конфигурации: 224 letterbox,2 fps,32 frames,50% overlap,hidden=256,1 layer,576 features assertion. Официальный стандартный center crop Torchvision не смешан с проектным letterbox.
9. Все контрактные fixtures явно test-only и валидируются схемами: processing/done/failed, отсутствие модели, unknown, ошибки, synthetic provenance. Определены команды версионирования и lock-файлы; версии/CUDA не объявлены проверенными до фактического preflight.
10. Четыре роли №1–№4, точные files и все36 карточек перечислены сразу. K и ранний O1 — независимые корни; implementation leaves после K доступны по реальным зависимостям. У №4 задачи последовательны по доступности без искусственных depends. Только U/E/B имеют helperFor=Z; сейчас помощники/код не запускаются.
11. Версионированы object bbox/visibility/review schema, temporal annotation, sourcePTS/time_base/origin mapping, dataset readiness и module ports. Object dataset не означает выбранный object detector; legal/actor/observability unknown не превращаются в false.
12. Python3.11 dependencies/CPU test extras и выбранный стек совместно зафиксированы pyproject/uv.lock; target CUDA/GPU readiness проверяется O1, несовместимость версии требует исправления общего контракта, не четырёх локальных копий.
13. Полностью недостаточная наблюдаемость не даёт clean verdict: job становится failed с reason=insufficient_evidence. Частичная coverage/unknown явно описана diagnostics/UI; публичный done не получает третьего verdict. no_violation означает отсутствие найденных поддержанными проверками нарушений, не доказанную безопасность всех кейсов.

### Исходы и блокировки

- **success**: Контракты/schema fixtures/ownership проходят проверки, можно принять K и открыть leaves.
- **missing**: Неизвестная taxonomy/норма/данные — draft/unknown с точным пробелом; UI/API остаются определимыми.
- **failure**: Противоречивый public/schema/module контракт — blocked до исправления K.

## A1 — БД и состояние заданий

Разработчик №1. Фаза: implementation. Зависимости: K.

Проверяемый результат: PostgreSQL repository и миграции jobs/results/outbox с явными состояниями и уникальными ключами.
Исходы: success: Durable repository готов для A4/A. | missing: Нет PostgreSQL/credentials — persistence acceptance blocked, code tests отдельно. | failure: Rollback/миграция/двойной claim — исправить A1; пользовательскую БД не сбрасывать.

### Разрешённые файлы

- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/jobs.py`
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_jobs_outbox.py`
- `tests/api/test_persistence.py`

### Критерии приёмки

1. Migration upgrade на пустой PostgreSQL, повторный запуск и restart проверены: job/result/outbox не теряются.
2. queued/running отображаются как processing; done/failed и invariant verdict↔violations фиксируются транзакционно.
3. JobRepository реализует порт K: durable create, atomic lease/fencing, unique result. Конкурентные транзакции не захватывают одно задание дважды.
4. DB outage/rollback не возвращает ложный202/done; частичный и устаревший результат не виден как успешный.
5. Реальная БД обязательна для persistence acceptance; mock не заменяет этот тест.

### Исходы и блокировки

- **success**: Durable repository готов для A4/A.
- **missing**: Нет PostgreSQL/credentials — persistence acceptance blocked, code tests отдельно.
- **failure**: Rollback/миграция/двойной claim — исправить A1; пользовательскую БД не сбрасывать.

## A2 — Приём и проверка видео

Разработчик №1. Фаза: implementation. Зависимости: K.

Проверяемый результат: Ограниченный upload/ffprobe/decode и подготовка media для durable job port с исходным временем.
Исходы: success: Валидный оригинал и time mapping переданы в durable port. | invalid: Медиа не проходит лимиты/декодирование —4xx без job. | failure: Диск/декодер/сохранение недоступны — service failure, без вердикта. | clientLost: До durable accept — cleanup; после accept job продолжает выполнение.

### Разрешённые файлы

- `backend/app/storage.py`
- `backend/app/video.py`
- `backend/app/api_upload.py`
- `tests/api/test_limits.py`
- `tests/api/test_upload_decode.py`

### Критерии приёмки

1. MP4/MOV:200МиБ,180с,1920×1080 либо1080×1920,≤60fps проверяются metadata и bounded decode; extension недостаточно.
2. VFR, rotation, ненулевой начальныйPTS, битый/обрезанный файл покрыты synthetic clips; sourcePTS/time_base/origin mapping сохраняется.
3. FFmpeg вызывается без shell с лимитами времени/CPU/размера; traversal, over-limit stream, decode hang и disk failure не дают accepted job.
4. 400/413/415 и инфраструктурный503 соответствуют K. Временный файл очищается при отказе до принятия; принятый оригинал не удаляется из-за разрыва клиента.
5. Model missing/busy дают503/429 до принятия;202 возможен только после durable file+job+outbox. Настоящая сборка проверяется в A.

### Исходы и блокировки

- **success**: Валидный оригинал и time mapping переданы в durable port.
- **invalid**: Медиа не проходит лимиты/декодирование —4xx без job.
- **failure**: Диск/декодер/сохранение недоступны — service failure, без вердикта.
- **clientLost**: До durable accept — cleanup; после accept job продолжает выполнение.

## A3 — Авторизация и медиа

Разработчик №1. Фаза: implementation. Зависимости: K.

Проверяемый результат: Авторизация всех endpoints данных и protected media/preview с проверяемым временем.
Исходы: success: Авторизованный оператор видит свой выбранный job и его исходные media. | denied: Нет/неверный ключ→401; нет job→404 без выдачи путей. | partial: Нет preview/кадра — media error, без выдуманного доказательства. | scope: Shared key не означает персональную изоляцию пользователей.

### Разрешённые файлы

- `backend/app/auth.py`
- `backend/app/media.py`
- `tests/api/test_auth_media.py`
- `tests/api/test_media_pts.py`

### Критерии приёмки

1. X-API-Key обязателен для job/result/diagnostics/media/frame endpoints;401 без/с неверным ключом,404 неизвестногоjob.
2. Один shared key не объявляется per-user isolation; multi-user права требуют отдельного контракта. СлучайныйID не заменяет auth.
3. Ключ не попадает в URL/bundle/logs; paths и содержимое видео не логируются. Protected fetch совместим с Blob≤200МиБ.
4. Preview сохраняет исходное time mapping/rotation;1–3 JPEG evidence frames принадлежат исходному видео, base64 без data-prefix.
5. Битый/отсутствующий кадр или preview даёт явную ошибку и не стирает job/result; public jury schema не расширяется.

### Исходы и блокировки

- **success**: Авторизованный оператор видит свой выбранный job и его исходные media.
- **denied**: Нет/неверный ключ→401; нет job→404 без выдачи путей.
- **partial**: Нет preview/кадра — media error, без выдуманного доказательства.
- **scope**: Shared key не означает персональную изоляцию пользователей.

## A4 — Outbox и один worker

Разработчик №1. Фаза: implementation. Зависимости: A1.

Проверяемый результат: Durable outbox PostgreSQL→Celery/Redis и один активный GPU job с fencing/idempotency.
Исходы: success: Одно принятое задание даёт один устойчивый итог. | brokerDown: Outbox сохраняет job и восстанавливает доставку в пределах deadline. | duplicate: Повторная доставка не дублирует анализ/result. | workerCrash: Новый lease/fencing, stale commit отвергается. | busy: Конкурентный intake→429; очередь не расширяется без benchmark.

### Разрешённые файлы

- `backend/app/outbox.py`
- `backend/app/celery_app.py`
- `backend/app/tasks.py`
- `tests/api/test_outbox.py`
- `tests/api/test_idempotency.py`

### Критерии приёмки

1. Job+outbox commit атомарен; crash между DB commit и publish, Redis down и повторный publish восстанавливаются без потери job.
2. Duplicate delivery/конкурентные workers не создают второй анализ/result; stale owner не фиксирует результат после нового lease.
3. Concurrency=1, prefetch/CPU threads ограничены. До benchmark второй незавершённый job получает429 атомарно, backlog отсутствует.
4. Crash/restart/acks/retry имеют управляемые конечные состояния; pending job не висит бесконечно, failed сохраняет причину.
5. Тест с настоящими PostgreSQL/Redis подтверждает один результат. Fixture runner только test profile, production fallback отсутствует.

### Исходы и блокировки

- **success**: Одно принятое задание даёт один устойчивый итог.
- **brokerDown**: Outbox сохраняет job и восстанавливает доставку в пределах deadline.
- **duplicate**: Повторная доставка не дублирует анализ/result.
- **workerCrash**: Новый lease/fencing, stale commit отвергается.
- **busy**: Конкурентный intake→429; очередь не расширяется без benchmark.

## A5 — Дедлайны и сбои backend

Разработчик №1. Фаза: verification. Зависимости: A2, A3, A4.

Проверяемый результат: Fault-injection проверки intake/auth/queue/repository до общей API-сборки.
Исходы: success: Failure/retry/deadline semantics готовы для A. | timeout: Deadline→failed и освобождение capacity. | failure: Потеря job/двойной result/stale commit — blocked до исправления. | notRun: Нет DB/Redis — соответствующие checks not_run, не passed.

### Разрешённые файлы

- `backend/app/deadlines.py`
- `tests/api/test_recovery.py`
- `tests/api/test_capacity_race.py`
- `tests/api/test_deadlines.py`

### Критерии приёмки

1. Kill/restart worker, Redis outage, DB rollback и duplicate delivery не теряют job/result и не создают ложный no_violation.
2. Deadline≤240с от приёма: exceeded→failed; late result не возвращает done. Учтены очередь и декодирование.
3. Concurrent intake сохраняет одно незавершённое задание; failure освобождает capacity корректно.
4. Ошибка после принятия становится durable failed с причиной; падение процесса не считается отрицательным анализом.
5. Command/exitCode/commit и failed/not_run записаны честно; модульный harness не называется полным пользовательским сценарием.

### Исходы и блокировки

- **success**: Failure/retry/deadline semantics готовы для A.
- **timeout**: Deadline→failed и освобождение capacity.
- **failure**: Потеря job/двойной result/stale commit — blocked до исправления.
- **notRun**: Нет DB/Redis — соответствующие checks not_run, не passed.

## A — API и надёжная очередь

Разработчик №1. Фаза: integration. Зависимости: A5.

Проверяемый результат: собранный настоящий FastAPI из принятых A1–A5: upload/status/auth/media, PostgreSQL/outbox/Celery и tests на реальных сервисах. Собрать main/settings/schemas/API routing и fixture runner только test profile. Не повторять модульные задачи отдельными копиями; исправлять существующие карточки. Общие locks K не менять параллельно другим веткам без обновлённого контракта.
Исходы: success: Настоящий API с persistence/queue/auth прошёл проверки. | missing: Нет реальных DB/Redis/runtime — интеграционная acceptance blocked, mocks отдельно. | noModel: Production503 ожидаем, synthetic runner только test. | failure: API/security/persistence regression — исправить соответствующую A1–A5, затем сборку A.

### Разрешённые файлы

- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/settings.py`
- `backend/app/auth.py`
- `backend/app/api.py`
- `backend/app/schemas.py`
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/storage.py`
- `backend/app/video.py`
- `backend/app/media.py`
- `backend/app/outbox.py`
- `backend/app/celery_app.py`
- `backend/app/tasks.py`
- `backend/app/jobs.py`
- `backend/app/deadlines.py`
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_jobs_outbox.py`
- `tests/api/conftest.py`
- `tests/api/fixture_runner.py`
- `tests/api/test_contract.py`
- `tests/api/test_auth_media.py`
- `tests/api/test_limits.py`
- `tests/api/test_outbox.py`
- `tests/api/test_idempotency.py`
- `tests/api/test_recovery.py`
- `backend/README.md`
- `tests/api/test_persistence.py`
- `backend/app/api_upload.py`
- `tests/api/test_upload_decode.py`
- `tests/api/test_media_pts.py`
- `tests/api/test_capacity_race.py`
- `tests/api/test_deadlines.py`

### Критерии приёмки

1. Реальные API-тесты проверяют 202 после сохранения, статусы processing/done/failed, неизменённую публичную схему, invariant verdict/violations и отдельные UI diagnostics; отказ валидации не создаёт accepted job.
2. Все job/result/media/preview/frame endpoints закрыты авторизацией. Тестами подтверждены 401 без/с неверным ключом, 404 чужого/отсутствующего ID по выбранной модели доступа; ключи, файловые пути и видео отсутствуют в логах/URL.
3. MP4/MOV проверяются метаданными и ограниченным фактическим декодированием: 200 МиБ,180 с,разрешение в обеих ориентациях,60 fps,VFR/rotation/PTS; FFmpeg запускается списком аргументов без shell, имена случайные, лимиты CPU/времени и damaged media покрыты тестами.
4. Миграции PostgreSQL создают jobs/results/outbox и ограничения уникальности. Crash между DB commit и publish, недоступный Redis и повторный publish восстанавливаются без потери задания.
5. Конкурентная повторная доставка даёт один анализ и один результат: атомарный lease/fencing и транзакционная фиксация; падение worker, expired lease и deadline не превращаются в done/no_violation.
6. GPU-worker concurrency=1, prefetch/CPU threads ограничены; до реального benchmark система принимает только одно незавершённое задание без backlog, второму возвращает 429. Последующее разрешение одного ожидающего требует прогнозируемого общего бюджета ≤240 с.
7. Тесты покрывают все ошибки 400/401/404/413/415/429/503 и post-accept failed. Deadline учитывает время от приёма, просроченный результат не становится успешным; успешные fixture timings отдельно от непроверенных SLA модели.
8. Защищённый preview fetch/Blob позволяет HTML video seek с исходным отображением времени; соответствие PTS и 1–3 исходных evidence frames проверено на синтетическом видео. Настоящие model/rules будут подключены в I.
9. Зависимости разрешены для Python 3.11 и согласованного стека, зафиксирован uv.lock; backend/README содержит реальные команды targeted тестов и ограничения; тесты persistence/queue выполнены с реальными PostgreSQL/Redis при исполнении, недоступные сервисы не объявлены пройденными.

### Исходы и блокировки

- **success**: Настоящий API с persistence/queue/auth прошёл проверки.
- **missing**: Нет реальных DB/Redis/runtime — интеграционная acceptance blocked, mocks отдельно.
- **noModel**: Production503 ожидаем, synthetic runner только test.
- **failure**: API/security/persistence regression — исправить соответствующую A1–A5, затем сборку A.

## F1 — Клиент API и ключ

Разработчик №2. Фаза: implementation. Зависимости: K.

Проверяемый результат: TypeScript/Vite scaffold, typed Query client и lifecycle ключа с отдельным test transport.
Исходы: success: Общий client/types готовы для F2/F3/F4. | unauthorized: 401→повторный ввод ключа без storage. | network: Network failure→видимая ошибка/retry GET, без fixtures. | reset: Отмена запросов и освобождение media; принятый backend job продолжает свой lifecycle.

### Разрешённые файлы

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ApiKeyForm.tsx`
- `frontend/src/fixtures/contract-fixtures.ts`
- `frontend/src/api/client.test.ts`

### Критерии приёмки

1. Выбранный React/Vite/TypeScript/Tailwind/Query/Dropzone стек зафиксирован package-lock; typecheck/component test commands работают.
2. Ключ только в памяти вкладки, запросы через X-API-Key; нет секрета в URL/storage/bundle/logs. Reset отменяет query/fetch.
3. Public types соответствуют K; protected diagnostics отдельны, unknown не теряется при преобразовании.
4. Fixtures включаются только explicit test/demo config с видимым provenance. Сетевая ошибка production не включает fixtures.
5. Abort до принятия не выдаёт done; разрыв после202 не отменяет server job. Retry polling не повторяет POST автоматически.

### Исходы и блокировки

- **success**: Общий client/types готовы для F2/F3/F4.
- **unauthorized**: 401→повторный ввод ключа без storage.
- **network**: Network failure→видимая ошибка/retry GET, без fixtures.
- **reset**: Отмена запросов и освобождение media; принятый backend job продолжает свой lifecycle.

## F2 — Загрузка и статусы

Разработчик №2. Фаза: implementation. Зависимости: F1.

Проверяемый результат: Dropzone/upload и polling processing/done/failed с корректными ошибками и busy состоянием.
Исходы: success: 202→processing→done с результатом или failed с причиной. | invalid: 400/413/415→исправить файл без job. | busy: 429→повторить позже без POST спама. | modelMissing: 503 model_not_ready→инструкция release. | network: Состояние неизвестно до повторного GET; не подставлять done/failed.

### Разрешённые файлы

- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`

### Критерии приёмки

1. MP4/MOV,200МиБ и серверные медиаограничения показаны до отправки; client checks не заменяют decode validation.
2. Upload progress отличим от processing. queued/running остаются публичным processing.
3. 202 сохраняет job_id в памяти UI; polling имеет bounded retry/cleanup/terminal stop. Повторный GET не создаёт job.
4. 400/401/404/413/415/429/503, network outage и failed с причиной покрыты компонентными тестами.
5. Отмена upload/закрытие вкладки не называется отменой принятого job. Возврат по job_id требует auth.

### Исходы и блокировки

- **success**: 202→processing→done с результатом или failed с причиной.
- **invalid**: 400/413/415→исправить файл без job.
- **busy**: 429→повторить позже без POST спама.
- **modelMissing**: 503 model_not_ready→инструкция release.
- **network**: Состояние неизвестно до повторного GET; не подставлять done/failed.

## F3 — Видео и доказательства

Разработчик №2. Фаза: implementation. Зависимости: F1.

Проверяемый результат: HTML video/seek и события с исходными кадрами, source time mapping и ограничениями.
Исходы: success: Оператор проверяет тот же ролик, timecode и исходный кадр. | mediaFailure: Нет видео/кадра — явная ошибка, не выдуманное доказательство. | unknown: Неизвестные условия/источники показаны с ограничениями. | resourceLimit: Blob сверх лимита — контролируемый отказ, не падение вкладки.

### Разрешённые файлы

- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`

### Критерии приёмки

1. Protected fetch→Blob≤200МиБ; Object URLs освобождаются при смене job/key/unmount, ключа в URL нет.
2. Click события/кадра использует исходный timecode и preview mapping; VFR/rotation/nonzeroPTS не заменяются frame_index/fps.
3. Карточка показывает1–3 JPEG, интервал, timestamp, source/version/limitations из API. Кадр другого ролика не подставляется.
4. Unknown/unsupported и неподтверждённый источник различимы; пустой список нарушений не обещает абсолютную безопасность.
5. Битый base64/preview/кадр даёт видимую локальную ошибку. UI не скрывает неработающее evidence.

### Исходы и блокировки

- **success**: Оператор проверяет тот же ролик, timecode и исходный кадр.
- **mediaFailure**: Нет видео/кадра — явная ошибка, не выдуманное доказательство.
- **unknown**: Неизвестные условия/источники показаны с ограничениями.
- **resourceLimit**: Blob сверх лимита — контролируемый отказ, не падение вкладки.

## F4 — Ошибки и доступность UI

Разработчик №2. Фаза: implementation. Зависимости: F1.

Проверяемый результат: Model/error panels и адаптивные стили с доступностью для последующей сборки UI.
Исходы: success: Понятные ошибки и доступный адаптивный UI. | missing: Нет модели — инструкция пакета без запуска train из UI. | a11yFailure: Focus/keyboard/читаемость не проходят — исправить F4/F и проверить. | partial: Нет preview/источника — видимое ограничение, не замена фактами.

### Разрешённые файлы

- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/styles.css`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`

### Критерии приёмки

1. Missing/invalid/incompatible/test-only release отображается как model_not_ready с инструкцией локального импорта.
2. Auth/busy/media/network/failed различимы и дают следующее действие без секретов и внутренних paths.
3. Семантические labels, focus/keyboard и сообщения статуса проверены; component harness работает при360/768/1440px.
4. Fixture/demo provenance виден; production показывает фактическую readiness и ограничения.
5. Полный browser journey/адаптивность после F/I проверяются в U; component harness не считается полной приёмкой.

### Исходы и блокировки

- **success**: Понятные ошибки и доступный адаптивный UI.
- **missing**: Нет модели — инструкция пакета без запуска train из UI.
- **a11yFailure**: Focus/keyboard/читаемость не проходят — исправить F4/F и проверить.
- **partial**: Нет preview/источника — видимое ограничение, не замена фактами.

## F — Интерфейс анализа

Разработчик №2. Фаза: integration. Зависимости: F2, F3, F4.

Проверяемый результат: собранный React UI из F1–F4: App/main, полный upload/poll/video/evidence/model-readiness путь на contract fixtures и production API client. Проверить typecheck/build и компонентную интеграцию. Полный браузер с настоящим backend после I проверяется в U.
Исходы: success: UI собран, typed client/fixtures изолированы; готов к I. | noModel: Показана инструкция release, нет выдуманного результата. | failure: Build/contract/a11y/fixture leakage — исправить F1–F4 или F, не подменять API.

### Разрешённые файлы

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ApiKeyForm.tsx`
- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/fixtures/contract-fixtures.ts`
- `frontend/src/App.test.tsx`
- `frontend/README.md`
- `frontend/src/api/client.test.ts`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`

### Критерии приёмки

1. UI принимает MP4/MOV и до отправки показывает ограничения 200 МиБ/180 с/размер/fps; progress upload и processing/polling разделены, queued/running не раскрываются как новые публичные статусы.
2. Есть состояния processing/done/failed и обработка 400/401/404/413/415/429/503, отмены fetch/ошибки сети и повторной проверки; отсутствие модели показывает model_not_ready и инструкцию локального импорта release, без выдуманного результата.
3. Ключ вводится пользователем, хранится только в памяти вкладки и передаётся X-API-Key через fetch; отсутствует в bundle/URL/localStorage/sessionStorage/logs, сброс ключа отменяет polling и освобождает медиа.
4. HTML video получает защищённый Blob в согласованном лимите до 200 МиБ; Object URLs освобождаются. Нажатие события/кадра устанавливает исходный timecode с учётом preview mapping; ошибки preview честно показаны.
5. Карточка события показывает 1–3 кадра, интервалы и исходные таймкоды, provenance/source/редакцию/ограничения из diagnostics; public jury response не расширяется, unknown/unsupported не маскируются зелёным успешным ML-вердиктом.
6. Contract fixtures имеют видимую метку synthetic test/demo, отдельную конфигурацию и не подключаются при production build. Синтетическое видео используется лишь для UI/seek проверки.
7. Компонентные проверки реального поведения покрывают upload/poll/error/seek; интерфейс проверен при 360,768,1440 px, с клавиатурой, читаемыми состояниями и без горизонтального переполнения.
8. npm lock, typecheck и production build воспроизводимы; frontend/README содержит фактические команды и различает fixture mode и production. Интеграция реального API и браузерная приёмка выполняются в I/U.

### Исходы и блокировки

- **success**: UI собран, typed client/fixtures изолированы; готов к I.
- **noModel**: Показана инструкция release, нет выдуманного результата.
- **failure**: Build/contract/a11y/fixture leakage — исправить F1–F4 или F, не подменять API.

## D1 — Аудит данных и среды

Разработчик №3. Фаза: implementation. Зависимости: K.

Проверяемый результат: Инвентарь исходников/разметки/прав использования и CPU/GPU preflight CLI без обучения.
Исходы: success: Инвентарь и preflight команды готовы. | noData: Нет видео/labels — data_missing, synthetic только code smoke. | imagesOnly: Только фото — object/frame dataset возможен, temporal training ждёт видео. | hardware: Нет CUDA/другого ПК — CPU smoke, hardware gate unverified. | license: Права данных неизвестны — не использовать для train, указать конкретный пробел.

### Разрешённые файлы

- `ml/__init__.py`
- `ml/preflight.py`
- `tests/ml/test_preflight.py`
- `docs/model/MISSING_MATERIALS.md`
- `docs/model/DATA_INVENTORY.md`

### Критерии приёмки

1. Для каждого материала указаны источник, path/hash, тип, доступность, права использования и неизвестное; отсутствующие приложения не выдумываются.
2. Видео, фото, annotations и release учтены раздельно; фото без порядка не считаются temporal GRU выборкой.
3. Preflight собирает Python3.11/PyTorch/Torchvision/CUDA/device/RAM/VRAM с реальным output; недоступный другой ПК не называется проверенным.
4. CPU-only self-test на tiny fixture работает; full train/fine-tune/GPU search/dataset evaluation не запускаются.
5. Отчёт различает tools_ready/data_missing/annotation_missing/hardware_unverified/license_unknown; training gate закрыт при отсутствии условий.

### Исходы и блокировки

- **success**: Инвентарь и preflight команды готовы.
- **noData**: Нет видео/labels — data_missing, synthetic только code smoke.
- **imagesOnly**: Только фото — object/frame dataset возможен, temporal training ждёт видео.
- **hardware**: Нет CUDA/другого ПК — CPU smoke, hardware gate unverified.
- **license**: Права данных неизвестны — не использовать для train, указать конкретный пробел.

## D2 — Классы и инструкция разметки

Разработчик №3. Фаза: implementation. Зависимости: K.

Проверяемый результат: Отдельные versioned taxonomies объектов, действий и состояний; гайд разметчика и связь с C01–C15.
Исходы: success: Определения и гайд позволяют начать локальную разметку. | noCase: Нет исходного кейса — draft и gap report, не окончательный набор. | ambiguous: Не различимы объект/действие — unknown/needs_review. | architecture: Датасет объектов не означает готовый detector. Его обучение/интеграция — отдельный этап.

### Разрешённые файлы

- `ml/data/taxonomy.py`
- `ml/config/object_taxonomy.draft.json`
- `ml/config/action_taxonomy.draft.json`
- `tests/ml/test_taxonomy.py`
- `docs/model/ANNOTATION_GUIDE.md`
- `docs/model/CASE_DATA_MAP.md`

### Критерии приёмки

1. Кандидаты объектов: пачка денег, документ, ключ, печать, сумка, сосуд, хранилище, дверь, экран. Это draft по кейсам; неизвестные25 ID не придумываются.
2. Для класса определены включения/исключения, похожие negatives, visibility/occlusion/truncation, small-object limits и unknown; ID append-only.
3. Bbox объекта не равен действию или юридическому вердикту; action score не actor ID. Role/track/party links nullable/unknown без данных.
4. Для C01–C15 записаны наблюдения, нужные объекты/интервалы/состояния и недоказуемое по видео. Нормативная применимость принадлежит R1.
5. Гайд задаёт human review/disagreement resolution, explicit negatives vs unlabeled, сложные примеры и отдельный holdout. Псевдоразметка не gold.

### Исходы и блокировки

- **success**: Определения и гайд позволяют начать локальную разметку.
- **noCase**: Нет исходного кейса — draft и gap report, не окончательный набор.
- **ambiguous**: Не различимы объект/действие — unknown/needs_review.
- **architecture**: Датасет объектов не означает готовый detector. Его обучение/интеграция — отдельный этап.

## D3 — Импорт и split без утечки

Разработчик №3. Фаза: implementation. Зависимости: K.

Проверяемый результат: Read-only импорт, manifest/hashes, дубли и grouped split до формирования кадров/окон.
Исходы: success: Versioned manifest/split без утечки source groups. | invalidArchive: Небезопасный архив отвергнут без скрытого частичного импорта. | corrupt: Источник quarantine с причиной, original сохранён. | leakage: Группы/дубли пересекают partitions — split invalid, train gate закрыт. | empty: Инструмент проверен на fixture; пустой manifest не объявляется реальным датасетом.

### Разрешённые файлы

- `ml/data/__init__.py`
- `ml/data/manifest.py`
- `ml/data/splits.py`
- `ml/data/safe_archive.py`
- `ml/data/deduplicate.py`
- `ml/config/data.example.yaml`
- `tests/ml/test_manifest.py`
- `tests/ml/test_splits.py`
- `tests/ml/test_safe_archive.py`
- `tests/ml/test_deduplicate.py`

### Критерии приёмки

1. ZIP traversal/absolute/symlink escape/zip bomb/лимит файлов отвергаются; вложенные scripts не выполняются, originals не меняются.
2. Manifest содержит source/video IDs,SHA256,метаданные,доступность и quarantine reason. Битый источник не попадает в train молча.
3. Exact duplicates и кандидаты near-duplicate имеют проверяемые clusters/config threshold; оригиналы автоматически не удаляются.
4. Все сцены/кадры исходного видео и duplicate cluster находятся в одном partition. Split детерминирован seed+manifest; independent final не участвует в train/thresholds.
5. 30/10 и минимальный объём не выдумываются. Нет источников/групп — data_not_ready; synthetic fixture хранится отдельно.

### Исходы и блокировки

- **success**: Versioned manifest/split без утечки source groups.
- **invalidArchive**: Небезопасный архив отвергнут без скрытого частичного импорта.
- **corrupt**: Источник quarantine с причиной, original сохранён.
- **leakage**: Группы/дубли пересекают partitions — split invalid, train gate закрыт.
- **empty**: Инструмент проверен на fixture; пустой manifest не объявляется реальным датасетом.

## D4 — Кадры и клипы по PTS

Разработчик №3. Фаза: implementation. Зависимости: D3.

Проверяемый результат: CLI извлечения сцен, кадров и клипов с source PTS и provenance для object/action datasets.
Исходы: success: Кадры/клипы и mapping manifest готовы для разметки. | short: Хвост получает padding mask; неполный интервал не даёт false absence. | scene: Смена сцены разрывает окно/память. | missingPTS: Невосстановимое время — quarantine/unsupported, не вымышленные timecodes. | noData: CLI проверен на synthetic; реальные clips ждут originals.

### Разрешённые файлы

- `ml/data/pts_index.py`
- `ml/data/scenes.py`
- `ml/data/extract_frames.py`
- `ml/data/extract_clips.py`
- `tests/ml/test_pts_index.py`
- `tests/ml/test_extraction.py`
- `docs/model/EXTRACTION.md`

### Критерии приёмки

1. Кадр связан с video_id/scene_id/sourcePTS/time_base/origin offset/rotation/sourcehash;0-based время обратимо соответствует original.
2. Частота configurable. Базовые2fps не гарантируют быстрые передачи/мелкие объекты; object frame export может иметь иную версионированную частоту.
3. Temporal window:32 samples при2fps, шаг16 samples(8с), padding/known masks хвоста. Длительность покрытия окна16с и span между первым/последним sample различаются явно.
4. Окно/клип не пересекает сцену/split; clipstart/decoded boundaries проверяются. VFR не index/fps, stream-copy seek по keyframe не называется точной нарезкой.
5. Frame/clip/crop artifacts воспроизводимы по sourcehash+config и вне Git; bbox/crop сохраняет transform к original, crop не заменяет temporal sequence.
6. Тесты покрывают VFR/rotation/nonzeroPTS/короткий/битый clip/re-run/диск и decode limits. Без исходников — только synthetic smoke.

### Исходы и блокировки

- **success**: Кадры/клипы и mapping manifest готовы для разметки.
- **short**: Хвост получает padding mask; неполный интервал не даёт false absence.
- **scene**: Смена сцены разрывает окно/память.
- **missingPTS**: Невосстановимое время — quarantine/unsupported, не вымышленные timecodes.
- **noData**: CLI проверен на synthetic; реальные clips ждут originals.

## D5 — Разметка объектов и событий

Разработчик №3. Фаза: implementation. Зависимости: D2, D4.

Проверяемый результат: Локальные annotation bundles, canonical JSONL/interval CSV, COCO roundtrip и QA без выдуманного gold.
Исходы: success: Annotation/COCO/QA инструменты готовы; dataset_ready только по реальным reviewed labels. | noLabels: Есть кадры без labels — annotation_missing и очередь ручной разметки. | badLabels: Неверные bbox/time/class/split — validation failure, train gate закрыт. | objectsOnly: Object annotation ready; temporal gate остаётся закрыт. | disagreement: Расхождения — needs_review, не автоматический gold. | toolAbsent: Нет локального annotation UI — bundles/validators доступны, ручная разметка отложена.

### Разрешённые файлы

- `ml/data/annotations.py`
- `ml/data/objects.py`
- `ml/data/coco_io.py`
- `ml/data/annotation_tasks.py`
- `ml/data/quality.py`
- `tests/ml/test_annotations.py`
- `tests/ml/test_objects_coco.py`
- `tests/ml/test_annotation_quality.py`
- `docs/model/ANNOTATION_WORKFLOW.md`

### Критерии приёмки

1. Object record:video/scene/frame/sourcePTS,class_id,bbox_xyxy в original decoded coordinates,visibility/occluded/truncated,nullable track_id,annotator/reviewer/status/taxonomy version.
2. COCO roundtrip проверяет image/category IDs,xyxy→xywh,границы/площадь и rotation/crop mapping. Temporal/unknown metadata сохраняется sidecar, а не теряется молча.
3. Action record:video_id/scene_id/start_sec/end_sec/event_type,known/visibility и explicit negatives. Unlabeled не negative; независимые действия могут пересекаться.
4. Гайд/taskbundle/import validators проверены на tiny fixture; совместимость COCO не означает установленный CVAT. Данные не отправляются в облачную разметку.
5. QA показывает per-class/per-case/per-video coverage,small objects/occlusion/truncation,unknown rate,disagreement/duplicates/leakage/review status; достигнутые объём/точность не выдумываются.
6. Без human-approved реальных labels data_ready=false; objects-only не GRU dataset. Псевдоразметка не gold, изменения labels версионируют dataset.

### Исходы и блокировки

- **success**: Annotation/COCO/QA инструменты готовы; dataset_ready только по реальным reviewed labels.
- **noLabels**: Есть кадры без labels — annotation_missing и очередь ручной разметки.
- **badLabels**: Неверные bbox/time/class/split — validation failure, train gate закрыт.
- **objectsOnly**: Object annotation ready; temporal gate остаётся закрыт.
- **disagreement**: Расхождения — needs_review, не автоматический gold.
- **toolAbsent**: Нет локального annotation UI — bundles/validators доступны, ручная разметка отложена.

## D — Данные и preflight

Разработчик №3. Фаза: integration. Зависимости: D1, D5.

Проверяемый результат: собранные D1–D5 и единый data preparation CLI: inventory→safe import/dedup/group split→PTS/scenes/frame/clip export→object/action annotation import→QA/readiness. Документировать команды в DATA.md и отдельный data readiness report. Tools ready, object dataset ready и temporal dataset ready — разные состояния. Без оригиналов/labels инструменты проверяются tiny synthetic, а реальные gates остаются закрыты.
Исходы: success: Все инструменты подготовки проверены, readiness report воспроизводим. | noData: Tools ready/data_missing — UI/API и ML tooling могут продолжаться; реальные clips/dataset не существуют. | objectsOnly: Object annotation ready, temporal dataset ещё not_ready. | invalid: Leakage/bad labels/missing human review — training gate закрыт, исправить D2–D5. | readyData: Только реальные reviewed видео/labels и valid split позволяют data_ready; полный train всё равно отдельное поручение.

### Разрешённые файлы

- `ml/__init__.py`
- `ml/data/__init__.py`
- `ml/data/manifest.py`
- `ml/data/annotations.py`
- `ml/data/splits.py`
- `ml/data/safe_archive.py`
- `ml/data/pts_index.py`
- `ml/preflight.py`
- `ml/config/data.example.yaml`
- `tests/ml/test_manifest.py`
- `tests/ml/test_annotations.py`
- `tests/ml/test_splits.py`
- `tests/ml/test_safe_archive.py`
- `tests/ml/test_preflight.py`
- `docs/model/DATA.md`
- `docs/model/MISSING_MATERIALS.md`
- `docs/model/DATA_INVENTORY.md`
- `ml/data/taxonomy.py`
- `ml/config/object_taxonomy.draft.json`
- `ml/config/action_taxonomy.draft.json`
- `tests/ml/test_taxonomy.py`
- `docs/model/ANNOTATION_GUIDE.md`
- `docs/model/CASE_DATA_MAP.md`
- `ml/data/deduplicate.py`
- `tests/ml/test_deduplicate.py`
- `ml/data/scenes.py`
- `ml/data/extract_frames.py`
- `ml/data/extract_clips.py`
- `tests/ml/test_pts_index.py`
- `tests/ml/test_extraction.py`
- `docs/model/EXTRACTION.md`
- `ml/data/objects.py`
- `ml/data/coco_io.py`
- `ml/data/annotation_tasks.py`
- `ml/data/quality.py`
- `tests/ml/test_objects_coco.py`
- `tests/ml/test_annotation_quality.py`
- `docs/model/ANNOTATION_WORKFLOW.md`
- `ml/data_cli.py`
- `docs/model/DATA_READINESS.json`
- `tests/ml/test_data_pipeline.py`

### Критерии приёмки

1. Аудит отмечает фактическое наличие/отсутствие TECHNICAL_SPEC.md, DATA_AND_TRAINING.md, CASE_COVERAGE.md, исходного кейса, контрактов, taxonomy, видео и аннотаций. Для текущего чистого base с одним README приложения считаются отсутствующими; старые результаты не выдумываются.
2. Manifest CLI формирует SHA-256,video_id/scene_id,медиаметаданные и provenance без изменения оригиналов; validators ловят повреждения, дубли и неподходящие медиа; большие данные остаются вне Git.
3. ZIP обработчик тестируется на traversal, absolute/symlink escape и превышение распакованного размера/количества; ничего из архива не выполняется.
4. Аннотации video_id,scene_id,start_sec,end_sec,event_type валидируются с visibility,unknown и explicit negatives. Не размеченное не трактуется как negative; фотографии без временного порядка не выдаются за GRU sequence.
5. Split строится по исходным видео/сценам, без пересечения групп и дублей train/dev/final. Финальные независимые видео другого ракурса не используются для подбора thresholds; старое 30/10 не фиксируется без manifest.
6. PTS index сохраняет исходное время,VFR/rotation и scene boundaries; тесты на tiny synthetic clips проверяют порядок/диапазоны и masks, без утверждения предметного качества.
7. Preflight CLI печатает Python/PyTorch/Torchvision/CUDA/device/доступную RAM/VRAM и проверяет 576 feature shape; CPU-only режим работает. Команда для RTX 5060 8 ГБ/RAM16/Ryzen5 8400 документирована, наличие этого оборудования и совместимость CUDA локально не выдумываются.
8. Выполнен только короткий CPU smoke validators на synthetic fixture; GPU train/fine-tune/подбор и датасетная оценка не запускаются. DATA.md/MISSING_MATERIALS.md различают проверенное, неизвестное и внешние зависимости.
9. Проверен единый CLI import/split/extract/annotation-import/validate/report. Отдельные readiness поля для tools/object annotations/temporal annotations/training, с reasons и evidence; отсутствие реальных данных не считается готовым датасетом.

### Исходы и блокировки

- **success**: Все инструменты подготовки проверены, readiness report воспроизводим.
- **noData**: Tools ready/data_missing — UI/API и ML tooling могут продолжаться; реальные clips/dataset не существуют.
- **objectsOnly**: Object annotation ready, temporal dataset ещё not_ready.
- **invalid**: Leakage/bad labels/missing human review — training gate закрыт, исправить D2–D5.
- **readyData**: Только реальные reviewed видео/labels и valid split позволяют data_ready; полный train всё равно отдельное поручение.

## M1 — Preprocessing и кэш

Разработчик №3. Фаза: implementation. Зависимости: D.

Проверяемый результат: единый train/inference preprocessing и воспроизводимый кэш последовательностей с полным происхождением.
Исходы: success: Единый preprocessing и проверяемый cache готовы для M2. | changedInput: Версия/хэш изменились — пересчитать затронутый кэш, не использовать старый marker. | interrupted: Неполная запись — восстановить из source manifest, не принять за готовую. | dataMissing: Code smoke возможен; cache_ready=false до реальных данных и локальных weights.

### Разрешённые файлы

- `ml/preprocessing.py`
- `ml/windows.py`
- `ml/cache.py`
- `tests/ml/test_pts_preprocessing.py`
- `tests/ml/test_cache_resume.py`
- `docs/model/PREPROCESSING.md`

### Критерии приёмки

1. Letterbox 224, ImageNet normalization, порядок каналов и masks совпадают в train/inference; размеры, rotation и inverse transform проверены.
2. Окна имеют исходные timestamps, scene/split IDs и padding/known masks; объединение перекрытий не смешивает сцены и partitions.
3. Ключ кэша включает source/dataset/split/annotation/taxonomy/encoder/preprocessing/config hashes. Смена любого значимого входа инвалидирует кэш.
4. Прерванная запись не создаёт valid cache marker; resume не принимает повреждённый или чужой кэш. Paths и объём настраиваемы, данные вне Git.
5. CPU tiny fixture подтверждает детерминизм и invalidation; реальный feature cache без исходников и pretrained local weights не объявляется построенным.

### Исходы и блокировки

- **success**: Единый preprocessing и проверяемый cache готовы для M2.
- **changedInput**: Версия/хэш изменились — пересчитать затронутый кэш, не использовать старый marker.
- **interrupted**: Неполная запись — восстановить из source manifest, не принять за готовую.
- **dataMissing**: Code smoke возможен; cache_ready=false до реальных данных и локальных weights.

## M2 — GRU и CPU train/resume

Разработчик №3. Фаза: implementation. Зависимости: M1.

Проверяемый результат: MobileNetV3-Small features + pooling → 576 → GRU 1×256 → Linear и работоспособный ограниченный CPU train/resume.
Исходы: success: Код модели и CLI train/resume работает на CPU fixture. | mismatch: Несовместимые shape/config/taxonomy — отказ resume с причиной. | oom: Smoke OOM/NaN/invalid loss — blocked, исправить размер tiny fixture/код; не объявлять train успешным. | futureTraining: Реальное обучение ждёт отдельного поручения, готовых данных и другого локального ПК.

### Разрешённые файлы

- `ml/models/__init__.py`
- `ml/models/encoder.py`
- `ml/models/temporal.py`
- `ml/train.py`
- `tests/ml/test_shapes_masks.py`
- `tests/ml/test_training_resume.py`

### Критерии приёмки

1. Shape assertions: [B,T,3,224,224]→[B,T,576]→[B,T,C]; ImageNet classifier удалён, production encoder IMAGENET1K_V1 загружается из локального подготовленного пути без runtime download.
2. Frozen encoder baseline, AdamW и BCEWithLogitsLoss учитывают unknown/padding masks; неизвестные labels не отрицательные.
3. Scene reset и состояния последовательности проверены; action score не является actor ID. Дополнительные views/backbone/object detector не вводятся.
4. Короткий CPU smoke на tiny synthetic data проверяет loss/gradient/checkpoint/resume, seed/config/runtime metadata и согласованность после возобновления.
5. Random-init smoke weights имеют test-only provenance и не могут активировать production readiness. Полный train, fine-tuning, GPU search и оценка реального датасета не выполняются.
6. Окно, где все labels неизвестны/padded, корректно пропускается или маскируется без NaN/деления на ноль; тест не превращает его в negative example.

### Исходы и блокировки

- **success**: Код модели и CLI train/resume работает на CPU fixture.
- **mismatch**: Несовместимые shape/config/taxonomy — отказ resume с причиной.
- **oom**: Smoke OOM/NaN/invalid loss — blocked, исправить размер tiny fixture/код; не объявлять train успешным.
- **futureTraining**: Реальное обучение ждёт отдельного поручения, готовых данных и другого локального ПК.
- **allUnknown**: Полностью unknown/padded окно не создаёт NaN и не становится negative.

## M3 — Оценка и экспорт пакета

Разработчик №3. Фаза: implementation. Зависимости: M2.

Проверяемый результат: реализованные evaluator/calibration/export CLI и неизменяемый release со всеми версиями и SHA-256.
Исходы: success: CLI оценки/thresholds/export готов и проверен на synthetic. | leakage: Final использован в настройке или split пересекается — оценка invalid, training/validation gate закрыт. | overBudget: Реальный экспорт превысил бюджет — честный failure/ограничение, не исключать encoder из подсчёта. | noWeights: Production release отсутствует, модель not trained/not validated; current software delivery возможна с503.

### Разрешённые файлы

- `ml/evaluate.py`
- `ml/thresholds.py`
- `ml/export.py`
- `ml/config/train.example.yaml`
- `ml/config/release.example.json`
- `tests/ml/test_evaluation_export.py`
- `tests/ml/test_export_format.py`

### Критерии приёмки

1. Evaluator считает verdict accuracy, balanced accuracy, macro-F1, support/FP/FN/coverage/unknown/абсолютные ошибки; события — precision/recall/F1 по заранее фиксированному tolerance, базово 0,5 с с версией.
2. Thresholds подбираются только на dev; train/dev/final groups не пересекаются, final другого ракурса не используется для обучения или настройки.
3. Release включает state_dict/config/backbone/576/taxonomy/preprocessing/thresholds/model card/metrics/dataset+split+annotation+rules versions и hashes. Новый release не затирает предыдущий.
4. Измеряется весь FP32 encoder+GRU+head ≤12 МБ и все модели ≤35 МБ без optimizer; encoder/head/training checkpoint и единицы отдельно. Smoke taxonomy не подтверждает бюджет неизвестной production taxonomy.
5. CPU fixture проверяет вычисления и export format; реальные цели ≥0,80 и performance остаются not evaluated. Ни один smoke metric не публикуется как качество реальной модели.

### Исходы и блокировки

- **success**: CLI оценки/thresholds/export готов и проверен на synthetic.
- **leakage**: Final использован в настройке или split пересекается — оценка invalid, training/validation gate закрыт.
- **overBudget**: Реальный экспорт превысил бюджет — честный failure/ограничение, не исключать encoder из подсчёта.
- **noWeights**: Production release отсутствует, модель not trained/not validated; current software delivery возможна с503.

## M4 — Loader и inference adapter

Разработчик №3. Фаза: implementation. Зависимости: M3.

Проверяемый результат: строгая локальная загрузка release, ActionTimeline и безопасные отказы до production анализа.
Исходы: success: Совместимый подтверждённый release может быть загружен после отдельного обучения/передачи. | missing: Нет пакета — model_not_ready/503 через backend. | invalid: Hash/version/shape/test-only mismatch — отказ с причиной и сохранение прежнего пакета. | failure: OOM/decode/inference exception — failed с причиной, не no_violation. | uncertain: Непроверенная наблюдаемость/actors остаются unknown в timeline.

### Разрешённые файлы

- `ml/release.py`
- `ml/inference.py`
- `ml/intervals.py`
- `tests/ml/test_release_loader.py`
- `tests/ml/test_inference_timeline.py`

### Критерии приёмки

1. Loader валидирует manifest/hashes, версии, architecture/576/shapes/taxonomy/thresholds/preprocessing/rules и обязательные metadata; произвольный best.pt не принимается.
2. Загружается tensor state_dict с явным weights_only=True и ограничениями размера/структуры; нет автоматического weights_only=False, произвольных allowlist imports или выполнения checkpoint-кода. weights_only не считается защитой от всех DoS.
3. Untrained/test-only/неполный/повреждённый/несовместимый пакет даёт model_not_ready, без случайных предсказаний и runtime скачивания весов.
4. Inference объединяет overlapping scores по исходному времени, учитывает masks/scene reset, выдаёт интервалы, visibility и unknown relations через K.
5. Локальное переключение release атомарно, прежний работоспособный пакет доступен для отката. CPU fixture проверяет код, но не ML качество; production не активируется synthetic release.

### Исходы и блокировки

- **success**: Совместимый подтверждённый release может быть загружен после отдельного обучения/передачи.
- **missing**: Нет пакета — model_not_ready/503 через backend.
- **invalid**: Hash/version/shape/test-only mismatch — отказ с причиной и сохранение прежнего пакета.
- **failure**: OOM/decode/inference exception — failed с причиной, не no_violation.
- **uncertain**: Непроверенная наблюдаемость/actors остаются unknown в timeline.

## M — ML CLI и загрузка release

Разработчик №3. Фаза: integration. Зависимости: M4.

Проверяемый результат: собранные M1–M4 и реальные CLI cache/train/resume/evaluate/thresholds/export/import. ml/cli.py, CLI.md и TRAINING.md дают другому локальному ПК точные команды подготовки данных/окружения, CUDA preflight, annotation QA, обучение/оценку, export/hash/import и rollback. Проверяется только короткий CPU tiny pipeline; полное обучение/fine-tune/GPU search/реальная ML-оценка отложены.
Исходы: success: CPU pipeline и handoff работают, production пока not trained/not validated. | missing: Нет real data/pretrained local weights/другого ПК — условие будущего этапа, не выдуманный success. | failure: Smoke/loader/schema/CLI regression — blocked до исправления M1–M4. | future: Отдельное разрешение+данные+hardware→train/evaluate/export→import; до этого503.

### Разрешённые файлы

- `ml/cli.py`
- `ml/models/__init__.py`
- `ml/models/encoder.py`
- `ml/models/temporal.py`
- `ml/preprocessing.py`
- `ml/windows.py`
- `ml/cache.py`
- `ml/train.py`
- `ml/evaluate.py`
- `ml/thresholds.py`
- `ml/export.py`
- `ml/release.py`
- `ml/inference.py`
- `ml/intervals.py`
- `ml/config/train.example.yaml`
- `ml/config/release.example.json`
- `tests/ml/test_shapes_masks.py`
- `tests/ml/test_pts_preprocessing.py`
- `tests/ml/test_cache_resume.py`
- `tests/ml/test_tiny_pipeline.py`
- `tests/ml/test_release_loader.py`
- `docs/model/TRAINING.md`
- `docs/model/CLI.md`
- `docs/model/PREPROCESSING.md`
- `tests/ml/test_training_resume.py`
- `tests/ml/test_evaluation_export.py`
- `tests/ml/test_export_format.py`
- `tests/ml/test_inference_timeline.py`

### Критерии приёмки

1. Shape tests подтверждают [B,T,3,224,224]→[B,T,576]→[B,T,C], feature_dim assertion=576; базово letterbox224,2 fps,window32,overlap50%,GRU1×256. Train/inference используют одну версию preprocessing/normalization; four-view тензор автоматически не вводится.
2. Masked BCEWithLogitsLoss не учитывает unknown labels и padded frames; scene reset обнуляет temporal state, overlapping windows агрегируются по исходным PTS с masks. Frame preprocessing, padding, unknown и scene boundaries покрыты targeted tests.
3. Реальные CLI cache/train/resume/evaluate/thresholds/export работают на tiny synthetic CPU fixture: frozen encoder+GRU baseline, AdamW, checkpoint/resume,seed/config/runtime metadata. Полный train/fine-tuning/GPU search/оценка реального датасета не запускаются; случайные smoke weights помечены test-only и отвергаются production loader.
4. Кэш инвалидируется при смене dataset/encoder/preprocessing версии и хэшей; resume проверяет совместимость конфигурации. Пороги выбираются только на dev, final split заблокирован от обучения/подбора.
5. Evaluator реализует accuracy,balanced accuracy,macro-F1 verdict, support/FP/FN/coverage/unknown/числа ошибок и event precision/recall/F1 с конфигурируемым заранее записанным временным допуском; реальная цель ≥0,80 на независимых видео остаётся not evaluated, метрики не выдумываются.
6. Release неизменяем и включает checkpoint/config/backbone/576/taxonomy/preprocessing/thresholds/metrics/model card/dataset+split+annotation+rules versions/SHA-256 manifest. Классы append-only, unconfirmed predictions не gold; новые release не затирают старые.
7. Loader отвергает случайный best.pt, untrained/test package, hash mismatch, неизвестные/несовместимые taxonomy/preprocessing/rules версии и недостающие файлы; загрузка локальная и безопасная без выполнения произвольного checkpoint-кода. Отсутствие validated usable release даёт model_not_ready, не synthetic predictions.
8. Бюджеты экспорта измеряются как весь MobileNetV3-Small+GRU+head ≤12 МБ FP32 и все модели ≤35 МБ без optimizer; encoder/head/training checkpoint отражены отдельно с явными единицами. На synthetic taxonomy измеряется только smoke variant; фактический budget production taxonomy и latency/VRAM/RAM не объявляются подтверждёнными.
9. docs/model/TRAINING.md содержит проверенные реализованными CLI команды установки другого локального ПК,CUDA preflight,manifest/annotations/split/cache/train+resume/evaluate/thresholds/export/SHA-256/переноса/импорта/отката и smoke; пример config,OOM/recovery,настраиваемые пути,ресурсы и ограничения. Доступ к тому ПК не prerequisite текущей сдачи.
10. CLI и TRAINING.md включают реальную нарезку по sourcePTS, object/temporal annotation workflow, COCO exchange и training-readiness validation. Отдельный object detector не обучается и не подменяет выбранный MobileNet+GRU.

### Исходы и блокировки

- **success**: CPU pipeline и handoff работают, production пока not trained/not validated.
- **missing**: Нет real data/pretrained local weights/другого ПК — условие будущего этапа, не выдуманный success.
- **failure**: Smoke/loader/schema/CLI regression — blocked до исправления M1–M4.
- **future**: Отдельное разрешение+данные+hardware→train/evaluate/export→import; до этого503.

## R1 — Кейсы и нормативные источники

Разработчик №4. Фаза: implementation. Зависимости: K.

Проверяемый результат: матрица C01–C15: необходимые наблюдения, границы доказуемости, подтверждённые источники и точные пробелы.
Исходы: success: Для подтверждённого подмножества есть применимый source-backed mapping. | missingSource: Нет нормы/редакции/исходного кейса — unsupported/unknown; юридическая приёмка соответствующего кейса не пройдена. | notObservable: Сумма/подделка/проводка/полномочия/закрытая сумка недоказуемы — не делать вывод. | changedRule: Новая редакция источника требует новой rules version и повторной проверки затронутых кейсов.

### Разрешённые файлы

- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/sources/snapshots.jsonl`
- `docs/operations/SOURCES.md`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`

### Критерии приёмки

1. Все C01–C15 сохранены; у каждого prerequisites, объекты/состояния/интервалы, исключения и supported/unsupported/unknown. Кейс не превращается автоматически в action class.
2. Источник реально открыт: редакция, применимость, исключения, дата, source_kind, URL, локальный текст и SHA-256. Отсутствующий исходный кейс/юрисдикция не заменяется похожей нормой.
3. Неподтверждённый источник не создаёт юридически названное нарушение; форма объяснения факт→возможное несоответствие→источник→ограничение.
4. Для отсутствия действия требуются полный существенный интервал, видимость, проверенный recognizer, определённый конец этапа и альтернативы; недоказуемое остаётся unknown.
5. Исследование ограничено вопросами поддержки C01–C15: после двух бесплодных заходов сохранить URL/вывод/неизвестное и конкретный недостающий материал, продолжить независимый код.

### Исходы и блокировки

- **success**: Для подтверждённого подмножества есть применимый source-backed mapping.
- **missingSource**: Нет нормы/редакции/исходного кейса — unsupported/unknown; юридическая приёмка соответствующего кейса не пройдена.
- **notObservable**: Сумма/подделка/проводка/полномочия/закрытая сумка недоказуемы — не делать вывод.
- **changedRule**: Новая редакция источника требует новой rules version и повторной проверки затронутых кейсов.

## R2 — Память ролика и связей

Разработчик №4. Фаза: implementation. Зависимости: K.

Проверяемый результат: память существенных интервалов обслуживания/партий на весь ролик с неизвестными actors/relations и reset по сцене.
Исходы: success: Последовательные наблюдения образуют воспроизводимое состояние ролика. | scene: Новая сцена — reset и границы unknown, без переноса участников/денег. | missingActor: Нет проверенного actor/party link — unknown, не подстановка наиболее вероятного. | truncated: Начало/конец этапа отсутствует — недостаточная наблюдаемость для absence rule.

### Разрешённые файлы

- `rules/__init__.py`
- `rules/types.py`
- `rules/session_memory.py`
- `tests/rules/test_scene_reset.py`
- `tests/rules/test_session_memory.py`

### Критерии приёмки

1. Состояния и переходы session/party references определены контрактом K; неизвестная роль/связь явно nullable/unknown.
2. Память не теряется между overlapping windows того же ролика, но не переносится через смену сцены/новое видео.
3. Глобальный action score не считается actor ID; нет незаявленного face/person detector или выдуманного назначения роли.
4. Тесты проверяют cross-session, unresolved state, поздние события, неполный интервал, окклюзию и два независимых job.
5. Невидимость не закрывает unresolved state как resolved; отсутствие проверяемой связи не превращается в уверенный trigger.

### Исходы и блокировки

- **success**: Последовательные наблюдения образуют воспроизводимое состояние ролика.
- **scene**: Новая сцена — reset и границы unknown, без переноса участников/денег.
- **missingActor**: Нет проверенного actor/party link — unknown, не подстановка наиболее вероятного.
- **truncated**: Начало/конец этапа отсутствует — недостаточная наблюдаемость для absence rule.

## R3 — Правила и сложные примеры

Разработчик №4. Фаза: implementation. Зависимости: R1, R2.

Проверяемый результат: engine пяти шаблонов с трёхзначной логикой и покрытием всех кейсов без ложной юридической уверенности.
Исходы: success: Поддержанное правило объяснимо и покрыто сценарными тестами. | unknown: Нет видимости/полного этапа/recognizer/источника — unknown, не not_triggered. | exception: Подтверждённое исключение снимает trigger по явной логике, а не эвристической догадке. | failure: Ложный trigger на hard-negative — blocked до исправления, критерии не ослабляются.

### Разрешённые файлы

- `rules/engine.py`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`

### Критерии приёмки

1. prerequisite/unresolved-state/cross-session/presence/response возвращают triggered/not_triggered/unknown по явным входам; нет invisible=false.
2. У каждого поддержанного правила есть positive, hard-negative, truncated interval, occlusion и exception tests; неподдержанные C01–C15 отдельно проверяют unknown/unsupported.
3. Стол с деньгами, касание ПК, светлый кадр или уход сами по себе не trigger; сумма/подделка/проводка/OS lock/полномочия не выводятся по отсутствующим признакам.
4. Только source-backed applicable rule получает нормативное имя; source/версии/limitations доступны diagnostics, внешний jury contract не расширяется.
5. Синтетические observations проверяют rule logic, не являются доказательством ML accuracy или реальной видимости.

### Исходы и блокировки

- **success**: Поддержанное правило объяснимо и покрыто сценарными тестами.
- **unknown**: Нет видимости/полного этапа/recognizer/источника — unknown, не not_triggered.
- **exception**: Подтверждённое исключение снимает trigger по явной логике, а не эвристической догадке.
- **failure**: Ложный trigger на hard-negative — blocked до исправления, критерии не ослабляются.

## R — Правила и источники

Разработчик №4. Фаза: integration. Зависимости: R3.

Проверяемый результат: собранные R1–R3: versioned case/source mapping, session memory и tri-state rules с положительными, сложными отрицательными, неполными/закрытыми интервалами и исключениями. Проверить source provenance и объяснение на всём rule output. Отсутствие источника/наблюдаемости не выдавать за отсутствие нарушения.
Исходы: success: Поддержанное подмножество engine/source mappings проверено. | unknown: Нет применимой нормы/видимости/actors — unknown/unsupported; юридический gate не пройден. | failure: Ложный trigger/ложное not_triggered — исправить R1–R3, критерии не ослаблять.

### Разрешённые файлы

- `rules/__init__.py`
- `rules/engine.py`
- `rules/session_memory.py`
- `rules/types.py`
- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`
- `tests/rules/test_scene_reset.py`
- `docs/operations/RULES.md`
- `docs/operations/SOURCES.md`
- `rules/sources/snapshots.jsonl`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`
- `tests/rules/test_session_memory.py`

### Критерии приёмки

1. cases.v1.json содержит все маршруты C01–C15: пачка,документ,смешение/остаток партий,оставленные ценности,хранилище,ключ,документы/печати,экран после ухода,дверь/вход,пересчёт до хранения,без клиента,повторная обработка купюр,личные вещи,сосуд/питьё,приборы после смены; для каждого условия,данные,ограничения,тесты и support status.
2. Engine выдаёт triggered/not_triggered/unknown; невидимое не false. Для отсутствия действия требуются полный существенный интервал,visibility,проверенный recognizer,конец этапа и альтернативы; неполный/невалидированный recognizer возвращает unknown.
3. Пять шаблонов prerequisite,unresolved-state,cross-session,presence,response имеют явные входы,выходы и positive/hard-negative/truncated/occlusion/exception тесты для каждого поддержанного правила; unsupported маршруты отдельно тестируют честный unknown.
4. Session memory ведётся весь ролик для интервалов обслуживания/денежных партий/неизвестных связей. Scene reset разделяет сессии, score действия не actor ID; неизвестные actors/roles/связи не выдумываются.
5. Нормативно именованное нарушение допускается лишь при открытом первоисточнике с редакцией/применимостью/исключениями,локальной копией/хэшем,датой,source_kind и provenance. Если первоисточник/исходный кейс недоступен, юридическая приёмка соответствующего правила остаётся unknown/blocked, нормативные названия не фабрикуются.
6. Проверки не выводят сумму/подделку/системную проводку/блокировку ОС/полномочия/содержимое непрозрачной сумки из отсутствующих признаков; стол с деньгами,касание ПК,светлый кадр или уход сами по себе не trigger.
7. Объяснение строго факт → признак возможного несоответствия → источник → ограничение; подлинные кадры/таймкоды приходят из pipeline, а не из шаблона rule pack. rules version и source provenance доступны diagnostics.
8. Тесты engine/session memory выполняются на явных synthetic observations, не выдаются за ML validation; docs/operations/RULES.md и SOURCES.md фиксируют критерии достаточности,фактически открытые URL,неизвестное и конкретные внешние пробелы без бесконечного поиска.

### Исходы и блокировки

- **success**: Поддержанное подмножество engine/source mappings проверено.
- **unknown**: Нет применимой нормы/видимости/actors — unknown/unsupported; юридический gate не пройден.
- **failure**: Ложный trigger/ложное not_triggered — исправить R1–R3, критерии не ослаблять.

## O2 — Compose и offline worker

Разработчик №4. Фаза: implementation. Зависимости: K.

Проверяемый результат: конфигурация nginx/api/worker/redis/postgres с локальными volumes и изоляцией GPU/сети.
Исходы: success: Воспроизводимые контейнеры/volumes/изоляция готовы для I. | noDocker: Config может быть подготовлен, но реальный container/offline test остаётся blocked/not_run. | noGPU: Нет подтверждённого GPU runtime — gpu_ready=false, CPU test profile отдельно. | egress: Интернет доступен worker — isolation failure, устранить до финала. | volume: Данные пропали после restart — blocked, пользовательские volumes не удалять для исправления.

### Разрешённые файлы

- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/redis.conf`
- `infra/env.example`
- `tests/performance/test_compose_isolation.py`

### Критерии приёмки

1. Compose config валиден; production GPU только worker, concurrency=1/prefetch/CPU threads ограничены; Redis/PostgreSQL без внешних published ports.
2. DB/media/model volumes постоянны; readiness приложения/модели разделена с container health, restart не стирает данные.
3. Worker не имеет интернет-egress, но доступ к локальным DB/queue остаётся; packages/weights готовятся отдельно, runtime downloads отсутствуют.
4. Образы используют общие согласованные locks K и frontend lock; secrets передаются вне Git, примеры только placeholders.
5. До I инфраструктура проверяется config и явно synthetic harness; build/start всего готового приложения проверяется только после принятой интеграции, не объявляется выполненным по YAML.

### Исходы и блокировки

- **success**: Воспроизводимые контейнеры/volumes/изоляция готовы для I.
- **noDocker**: Config может быть подготовлен, но реальный container/offline test остаётся blocked/not_run.
- **noGPU**: Нет подтверждённого GPU runtime — gpu_ready=false, CPU test profile отдельно.
- **egress**: Интернет доступен worker — isolation failure, устранить до финала.
- **volume**: Данные пропали после restart — blocked, пользовательские volumes не удалять для исправления.

## O3 — TLS и внешний smoke

Разработчик №4. Фаза: implementation. Зависимости: O1, O2.

Проверяемый результат: настроенный Nginx/HTTPS и наблюдённый внешний upload/status smoke на явном synthetic harness.
Исходы: success: Trusted внешний HTTPS маршрут наблюдён на synthetic data. | localOnly: Доступен только localhost — local_only, обязательный внешний критерий не пройден. | certificate: Нет валидной цепочки/имени/срока — TLS failure до исправления. | network: CGNAT/firewall/маршрут не разрешены — external_access_blocked, без самовольного туннеля. | leak: Сервис БД/Redis/media стал публичен безauth — blocked до исправления.

### Разрешённые файлы

- `infra/nginx.conf`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

### Критерии приёмки

1. TLS завершает Nginx; сертификат/hostname/expiry/chain и разрешённый внешний маршрут проверены, ключи/сертификатные секреты вне Git.
2. Proxy limits соответствуют200МиБ и полному deadline; auth headers сохраняются, media/diagnostics не становятся публичными.
3. Через внешний клиент проверены tiny synthetic upload→status и ошибки; до I это только обозначенный test harness, а не проверка модели/всего продукта.
4. CGNAT/нет домена/сертификата/разрешённого транспорта — точный blocker; local self-signed smoke не объявляется внешним trustedHTTPS.
5. Не подключать облачный transport/AI и не раскрывать видео ради smoke. Реальный API/browser повтор внешнего пути выполняется в I/B.

### Исходы и блокировки

- **success**: Trusted внешний HTTPS маршрут наблюдён на synthetic data.
- **localOnly**: Доступен только localhost — local_only, обязательный внешний критерий не пройден.
- **certificate**: Нет валидной цепочки/имени/срока — TLS failure до исправления.
- **network**: CGNAT/firewall/маршрут не разрешены — external_access_blocked, без самовольного туннеля.
- **leak**: Сервис БД/Redis/media стал публичен безauth — blocked до исправления.

## O — Compose и доступ по HTTPS

Разработчик №4. Фаза: integration. Зависимости: O3.

Проверяемый результат: собранные O1–O3: preflight, Compose isolation/volumes, Nginx/TLS и фактически наблюдённый внешний synthetic smoke. Начать O1 в первые два часа; №4 выполняет свои готовые R/O карточки последовательно без искусственных связей. До I проверка на infra harness не считается запуском всего приложения; после I внешний real-API повтор в B.
Исходы: success: Среда/изоляция/volumes/внешний HTTPS подтверждены реальными checks. | localOnly: Только localhost — local_only; внешний обязательный критерий blocked. | missing: Нет Docker/GPU/FFmpeg/сертификата/маршрута — конкретный blocker, остальные ветки продолжаются. | failure: Public DB/Redis,worker egress,потеря volumes или TLS error — blocked до исправления.

### Разрешённые файлы

- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/nginx.conf`
- `infra/redis.conf`
- `infra/env.example`
- `infra/scripts/preflight.sh`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-check.sh`
- `infra/scripts/smoke.sh`
- `docs/operations/SETUP.md`
- `docs/operations/NETWORK.md`
- `infra/scripts/preflight.ps1`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`
- `tests/performance/test_compose_isolation.py`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

### Критерии приёмки

1. Compose содержит nginx/api/worker/redis/postgres; GPU устройства доступны только worker, GPU concurrency=1/prefetch/CPU threads и memory limits согласованы с 16 ГБ RAM. postgres/redis не публикуют внешние порты.
2. Локальные media/model/DB volumes переживают restart; restart/healthcheck и startup ordering не принимают readiness модели за readiness контейнера. Runtime analysis не скачивает пакеты/веса.
3. Preflight проверяет реальную ОС/WSL2,Docker Compose,NVIDIA Container Toolkit,GPU/CUDA/Python3.11/FFmpeg и совместимость версий; отсутствующее или непроверенное фиксируется, никаких заявлений о целевом железе по названию.
4. Nginx завершает TLS,проксирует защищённые API/media и frontend,согласует upload200 МиБ/timeouts. Сертификат/секреты не входят в Git, нет API ключа в bundle/URL/logs.
5. network-check/tls-check наблюдают внешний HTTPS upload→status на synthetic media без настоящих видео. CGNAT/нет домена/сертификата/разрешённого транспорта — конкретный blocker внешнего доступа; local-only smoke не объявляется внешним.
6. Worker не имеет доступа к интернету в runtime,но видит только необходимые локальные сервисы; firewall/network topology и offline smoke подтверждают отсутствие egress без блокировки PostgreSQL/Redis.
7. infra/env.example и SETUP/NETWORK описывают реальные команды подготовки/запуска/остановки,порты,paths,healthcheck,сертификат,резервирование volumes и ограничения; контейнеры и зависимости зафиксированы совместимыми lock/digest в реализации, не проверены заранее в плане.

### Исходы и блокировки

- **success**: Среда/изоляция/volumes/внешний HTTPS подтверждены реальными checks.
- **localOnly**: Только localhost — local_only; внешний обязательный критерий blocked.
- **missing**: Нет Docker/GPU/FFmpeg/сертификата/маршрута — конкретный blocker, остальные ветки продолжаются.
- **failure**: Public DB/Redis,worker egress,потеря volumes или TLS error — blocked до исправления.

## I — Интеграция без весов

Разработчик №1. Фаза: integration. Зависимости: A, F, M, R, O.

Проверяемый результат: интегрированные A/F/M/R/O и все их текущие принятые ancestors в одной собственной ветке с реальными commits. Соединить UI/API/repository/outbox/worker/inference/rules/media/diagnostics, реально запустить полный Compose при доступной среде. Без trained compatible release production возвращает503; test/demo fixtures явно отделены. Приёмочные U/E/B — отдельные задачи своих разработчиков перед Z. Их зависимости и области заданы этим GitHub-планом; создание чатов не требуется.
Исходы: success: Полная software интеграция прошла, открываются U/E/B. | noRelease: Production503 и инструкция импорта; test journey только с explicit synthetic profile. | failure: Контракт/медиа/очередь/Compose/rules wiring не проходит — fix профильной карточки и повтор I. | unknown: Неизвестные ML/legal capabilities явно в diagnostics; fixtures не валидируют их.

### Разрешённые файлы

- `contracts/openapi.yaml`
- `contracts/job.schema.json`
- `contracts/diagnostics.schema.json`
- `contracts/events.schema.json`
- `contracts/manifest.schema.json`
- `contracts/annotations.schema.json`
- `contracts/release.schema.json`
- `contracts/taxonomy.draft.json`
- `contracts/fixtures.json`
- `contracts/OWNERSHIP.md`
- `contracts/DEPENDENCIES.md`
- `contracts/STACK.md`
- `tests/contracts/test_schemas.py`
- `docs/operations/LOCAL_ARTIFACTS.md`
- `config.example.toml`
- `pyproject.toml`
- `uv.lock`
- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/settings.py`
- `backend/app/auth.py`
- `backend/app/api.py`
- `backend/app/schemas.py`
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/storage.py`
- `backend/app/video.py`
- `backend/app/media.py`
- `backend/app/outbox.py`
- `backend/app/celery_app.py`
- `backend/app/tasks.py`
- `backend/app/jobs.py`
- `backend/app/deadlines.py`
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_jobs_outbox.py`
- `tests/api/conftest.py`
- `tests/api/fixture_runner.py`
- `tests/api/test_contract.py`
- `tests/api/test_auth_media.py`
- `tests/api/test_limits.py`
- `tests/api/test_outbox.py`
- `tests/api/test_idempotency.py`
- `tests/api/test_recovery.py`
- `backend/README.md`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ApiKeyForm.tsx`
- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/fixtures/contract-fixtures.ts`
- `frontend/src/App.test.tsx`
- `frontend/README.md`
- `ml/__init__.py`
- `ml/data/__init__.py`
- `ml/data/manifest.py`
- `ml/data/annotations.py`
- `ml/data/splits.py`
- `ml/data/safe_archive.py`
- `ml/data/pts_index.py`
- `ml/preflight.py`
- `ml/config/data.example.yaml`
- `tests/ml/test_manifest.py`
- `tests/ml/test_annotations.py`
- `tests/ml/test_splits.py`
- `tests/ml/test_safe_archive.py`
- `tests/ml/test_preflight.py`
- `docs/model/DATA.md`
- `docs/model/MISSING_MATERIALS.md`
- `ml/cli.py`
- `ml/models/__init__.py`
- `ml/models/encoder.py`
- `ml/models/temporal.py`
- `ml/preprocessing.py`
- `ml/windows.py`
- `ml/cache.py`
- `ml/train.py`
- `ml/evaluate.py`
- `ml/thresholds.py`
- `ml/export.py`
- `ml/release.py`
- `ml/inference.py`
- `ml/intervals.py`
- `ml/config/train.example.yaml`
- `ml/config/release.example.json`
- `tests/ml/test_shapes_masks.py`
- `tests/ml/test_pts_preprocessing.py`
- `tests/ml/test_cache_resume.py`
- `tests/ml/test_tiny_pipeline.py`
- `tests/ml/test_release_loader.py`
- `docs/model/TRAINING.md`
- `docs/model/CLI.md`
- `rules/__init__.py`
- `rules/engine.py`
- `rules/session_memory.py`
- `rules/types.py`
- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`
- `tests/rules/test_scene_reset.py`
- `docs/operations/RULES.md`
- `docs/operations/SOURCES.md`
- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/nginx.conf`
- `infra/redis.conf`
- `infra/env.example`
- `infra/scripts/preflight.sh`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-check.sh`
- `infra/scripts/smoke.sh`
- `docs/operations/SETUP.md`
- `docs/operations/NETWORK.md`
- `backend/app/pipeline.py`
- `backend/app/model_status.py`
- `backend/app/diagnostics.py`
- `tests/integration/conftest.py`
- `tests/integration/test_pipeline.py`
- `tests/integration/test_model_not_ready.py`
- `tests/integration/test_evidence_pts.py`
- `tests/integration/test_fixture_isolation.py`
- `tests/integration/test_release_import.py`
- `rules/sources/snapshots.jsonl`
- `tests/api/test_persistence.py`
- `backend/app/api_upload.py`
- `tests/api/test_upload_decode.py`
- `tests/api/test_media_pts.py`
- `tests/api/test_capacity_race.py`
- `tests/api/test_deadlines.py`
- `contracts/__init__.py`
- `contracts/python_ports.py`
- `contracts/objects.schema.json`
- `contracts/dataset_readiness.schema.json`
- `contracts/OUTCOMES.md`
- `frontend/src/api/client.test.ts`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`
- `docs/model/PREPROCESSING.md`
- `tests/ml/test_training_resume.py`
- `tests/ml/test_evaluation_export.py`
- `tests/ml/test_export_format.py`
- `tests/ml/test_inference_timeline.py`
- `docs/model/DATA_INVENTORY.md`
- `ml/data/taxonomy.py`
- `ml/config/object_taxonomy.draft.json`
- `ml/config/action_taxonomy.draft.json`
- `tests/ml/test_taxonomy.py`
- `docs/model/ANNOTATION_GUIDE.md`
- `docs/model/CASE_DATA_MAP.md`
- `ml/data/deduplicate.py`
- `tests/ml/test_deduplicate.py`
- `ml/data/scenes.py`
- `ml/data/extract_frames.py`
- `ml/data/extract_clips.py`
- `tests/ml/test_pts_index.py`
- `tests/ml/test_extraction.py`
- `docs/model/EXTRACTION.md`
- `ml/data/objects.py`
- `ml/data/coco_io.py`
- `ml/data/annotation_tasks.py`
- `ml/data/quality.py`
- `tests/ml/test_objects_coco.py`
- `tests/ml/test_annotation_quality.py`
- `docs/model/ANNOTATION_WORKFLOW.md`
- `ml/data_cli.py`
- `docs/model/DATA_READINESS.json`
- `tests/ml/test_data_pipeline.py`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`
- `tests/rules/test_session_memory.py`
- `infra/scripts/preflight.ps1`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`
- `tests/performance/test_compose_isolation.py`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

### Критерии приёмки

1. В integration packet присутствуют принятые A/F/M/R/O и их транзитивные K/D, реальные SHA доступны и интегрированы; изменённые пути находятся в files, конфликты разрешены, итоговый commit зафиксирован.
2. UI production build общается с настоящим FastAPI,PostgreSQL и Celery; contract tests проверяют публичную схему и отдельный diagnostics,авторизацию,ошибки и persistence.
3. Без обученного совместимого usable release POST analyze возвращает 503 model_not_ready и UI инструкцию импорта; нет случайного результата,ложного done/no_violation и скрытого fallback на fixtures.
4. Fixture runner и tiny smoke releases доступны только явно отдельному test/demo profile с меткой synthetic. Production config отвергает их и не принимает untrained package.
5. На явно тестовом synthetic media пройден путь upload→outbox→worker→интервалы→rules→result→video seek; 1–3 evidence frames взяты из соответствующего исходного файла/PTS,а не нарисованы/взяты из другого ролика.
6. Память сбрасывается при смене сцены,unknown actors/observability и неподтверждённые нормы сохраняются в diagnostics; unsupported кейсы не становятся юридически названными нарушениями.
7. Проверены retry/duplicate dispatch,auth на media,защищённый Blob playback и корректные failed/deadline; production code не вызывает cloud AI,face recognition,audio analysis или runtime network downloads.
8. Сборка и targeted integration checks фактически выполнены с командами/exitCode/commit. Итог — программная интеграция; training/independent ML evaluation/реальный model benchmark остаются отложенными, обязательный software failure фиксируется blocked.
9. E2E fixture полностью unknown даёт failed insufficient_evidence; partial coverage/unknown явно видна UI. Пустой violations не используется как доказательство отсутствия невидимого действия.

### Исходы и блокировки

- **success**: Полная software интеграция прошла, открываются U/E/B.
- **noRelease**: Production503 и инструкция импорта; test journey только с explicit synthetic profile.
- **failure**: Контракт/медиа/очередь/Compose/rules wiring не проходит — fix профильной карточки и повтор I.
- **unknown**: Неизвестные ML/legal capabilities явно в diagnostics; fixtures не валидируют их.
- **insufficientEvidence**: Все существенные наблюдения unknown — failed insufficient_evidence, без clean verdict; partial coverage явно в diagnostics.

## U — Браузерная приёмка

Разработчик №2. Фаза: verification. Зависимости: I.

Проверяемый результат: браузерная приёмка интегрированного UI с настоящим API: production503 и отдельно synthetic test-mode полный путь. Проверить клавиатуру, адаптивность, auth/reset, tab/network interruption, video/seek/evidence/source/unknown. Исправления только frontend/e2e после I; backend дефекты возвращать в существующую профильную карточку.
Исходы: success: Реальный browser journey/seek/auth/адаптивность проверены. | missingFrames: Нет реальных исходников — это limitation, synthetic frame provenance проверяется фактически. | failure: Browser/API/evidence mismatch — вернуть в F/I/A по месту, не прятать ошибку. | noRelease: 503 UI ожидаем и проверен, не чистый вердикт.

### Разрешённые файлы

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ApiKeyForm.tsx`
- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/fixtures/contract-fixtures.ts`
- `frontend/src/App.test.tsx`
- `frontend/README.md`
- `tests/e2e/playwright.config.ts`
- `tests/e2e/upload.spec.ts`
- `tests/e2e/video-evidence.spec.ts`
- `tests/e2e/errors-model.spec.ts`
- `tests/e2e/responsive-auth.spec.ts`
- `tests/e2e/report.json`
- `frontend/ACCEPTANCE.md`
- `frontend/src/api/client.test.ts`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`

### Критерии приёмки

1. Браузерные тесты на работающем API проходят upload/poll/done/failed,event click/seek,1–3 JPEG evidence frames и отображение источника/версий/ограничений; synthetic provenance видна.
2. Production без release показывает503 model_not_ready/инструкцию локального импорта и не показывает fixture result. Проверены401,400/413/415,429,network failure,retry и отмена polling.
3. Для synthetic clip timestamp→HTML video seek и исходный evidence frame сопоставлены с допуском не больше одного исходного кадра при известном PTS. Доступные настоящие кадры проверяются только если реально предоставлены; иначе отсутствие документируется.
4. При360/768/1440px нет горизонтального переполнения,контролы доступны с клавиатуры,upload/status/video/result читаемы; фактические screenshot/vision наблюдения записаны.
5. Проверено отсутствие API ключа в bundle,URL,browser storage и логах,auth защищает media,Blob ограничен200МиБ и освобождается при смене задания/ключа.
6. Отчёт содержит браузер/версию,точный commit,команды/exitCode,покрытие acceptance и реальные дефекты/ограничения; авторские проверки не называются независимым approval.
7. Проверены разрыв сети после202, возврат к job_id, reset ключа, отмена fetch и освобождение Blob. Принятый серверомjob не объявляется отменённым из-за закрытия вкладки.

### Исходы и блокировки

- **success**: Реальный browser journey/seek/auth/адаптивность проверены.
- **missingFrames**: Нет реальных исходников — это limitation, synthetic frame provenance проверяется фактически.
- **failure**: Browser/API/evidence mismatch — вернуть в F/I/A по месту, не прятать ошибку.
- **noRelease**: 503 UI ожидаем и проверен, не чистый вердикт.

## E — Передача ML-инструментов

Разработчик №3. Фаза: verification. Зависимости: I.

Проверяемый результат: проверенная передача всех data/annotation/ML инструментов другого локального ПК: CLI, object COCO roundtrip, temporal labels/split/windows, preprocessing/cache/model/train-resume/evaluation/export/import, readiness gates и документация. CPU tiny fixture подтверждает код, не датасет/обучение/качество. Образец model card содержит реальные неизвестные, а не выдуманные metrics.
Исходы: success: Инструменты/команды/форматы переданы и воспроизведены на CPU tiny. | noDataset: Реальные объекты/temporal labels не предоставлены — readiness=false, без выдуманного датасета. | future: Full training/independent ML evaluation/production size budget отложены. | failure: Инструкция не соответствует CLI/format или leakage — blocked до исправления D/M.

### Разрешённые файлы

- `ml/__init__.py`
- `ml/data/__init__.py`
- `ml/data/manifest.py`
- `ml/data/annotations.py`
- `ml/data/splits.py`
- `ml/data/safe_archive.py`
- `ml/data/pts_index.py`
- `ml/preflight.py`
- `ml/config/data.example.yaml`
- `tests/ml/test_manifest.py`
- `tests/ml/test_annotations.py`
- `tests/ml/test_splits.py`
- `tests/ml/test_safe_archive.py`
- `tests/ml/test_preflight.py`
- `docs/model/DATA.md`
- `docs/model/MISSING_MATERIALS.md`
- `ml/cli.py`
- `ml/models/__init__.py`
- `ml/models/encoder.py`
- `ml/models/temporal.py`
- `ml/preprocessing.py`
- `ml/windows.py`
- `ml/cache.py`
- `ml/train.py`
- `ml/evaluate.py`
- `ml/thresholds.py`
- `ml/export.py`
- `ml/release.py`
- `ml/inference.py`
- `ml/intervals.py`
- `ml/config/train.example.yaml`
- `ml/config/release.example.json`
- `tests/ml/test_shapes_masks.py`
- `tests/ml/test_pts_preprocessing.py`
- `tests/ml/test_cache_resume.py`
- `tests/ml/test_tiny_pipeline.py`
- `tests/ml/test_release_loader.py`
- `docs/model/TRAINING.md`
- `docs/model/CLI.md`
- `tests/ml/test_cli_handoff.py`
- `tests/ml/test_release_compatibility.py`
- `tests/ml/test_export_budgets.py`
- `docs/model/EVALUATION.md`
- `docs/model/MODEL_CARD.template.md`
- `docs/model/HANDOFF.md`
- `docs/model/ACCEPTANCE.json`
- `docs/model/DATA_INVENTORY.md`
- `ml/data/taxonomy.py`
- `ml/config/object_taxonomy.draft.json`
- `ml/config/action_taxonomy.draft.json`
- `tests/ml/test_taxonomy.py`
- `docs/model/ANNOTATION_GUIDE.md`
- `docs/model/CASE_DATA_MAP.md`
- `ml/data/deduplicate.py`
- `tests/ml/test_deduplicate.py`
- `ml/data/scenes.py`
- `ml/data/extract_frames.py`
- `ml/data/extract_clips.py`
- `tests/ml/test_pts_index.py`
- `tests/ml/test_extraction.py`
- `docs/model/EXTRACTION.md`
- `ml/data/objects.py`
- `ml/data/coco_io.py`
- `ml/data/annotation_tasks.py`
- `ml/data/quality.py`
- `tests/ml/test_objects_coco.py`
- `tests/ml/test_annotation_quality.py`
- `docs/model/ANNOTATION_WORKFLOW.md`
- `ml/data_cli.py`
- `docs/model/DATA_READINESS.json`
- `tests/ml/test_data_pipeline.py`
- `docs/model/PREPROCESSING.md`
- `tests/ml/test_training_resume.py`
- `tests/ml/test_evaluation_export.py`
- `tests/ml/test_export_format.py`
- `tests/ml/test_inference_timeline.py`

### Критерии приёмки

1. Все команды TRAINING.md/CLI.md --help и короткий CPU путь manifest→validation→split→PTS/windows→cache→train/resume→evaluate→thresholds→export→hash→test import воспроизведены на tiny synthetic data; команды и точный commit записаны.
2. Пример конфигурации и release schema валидны; hashes/backbone/576/taxonomy/preprocessing/thresholds/dataset+split+rules versions проверяются loader. Неполный,повреждённый,несовместимый,untrained/test release production не загружает.
3. Инструкция другого ПК включает Python3.11/CUDA preflight,ресурсы,настраиваемые paths,данные/аннотации/групповой split,seed/версии,OOM/resume/откат,локальный перенос и проверку SHA-256; не содержит требований дать доступ к тому ПК сейчас.
4. EVALUATION.md заранее фиксирует event tolerance (базовое обратимое значение 0,5 с с версией, до любых реальных оценок), независимый video/scene split другого ракурса и цели verdict accuracy/balanced accuracy/macro-F1 ≥0,80; support/FP/FN/coverage/unknown/числа ошибок и event P/R/F1 обязательны.
5. MODEL_CARD.template явно not trained/not validated без выдуманных цифр; отсутствующий реальный dataset/taxonomy,исходные приложения,нормативные материалы и весь последующий training/evaluation перечислены.
6. Команда измерения всего FP32 export проверена на smoke taxonomy с явными единицами и отдельными encoder/head/checkpoint; цели≤12МБ основной комплект/≤35МБ все модели и production-taxonomy budget пока не заявлены достигнутыми.
7. Не запускались полный train/fine-tune/GPU search и реальная датасетная ML-оценка. Отчёт передаёт только наблюдённую программную готовность и конкретные ограничения; Проверка точного commit и отчёта выполняется по GitHub-процессу.
8. Воспроизведены extraction/COCO import-export/annotation QA/split leak checks на tiny synthetic; исходные frames/clip provenance сохранены. Objects-only/data_missing/annotation_missing не активируют temporal training gate.

### Исходы и блокировки

- **success**: Инструменты/команды/форматы переданы и воспроизведены на CPU tiny.
- **noDataset**: Реальные объекты/temporal labels не предоставлены — readiness=false, без выдуманного датасета.
- **future**: Full training/independent ML evaluation/production size budget отложены.
- **failure**: Инструкция не соответствует CLI/format или leakage — blocked до исправления D/M.

## B — Восстановление и benchmark

Разработчик №4. Фаза: verification. Зависимости: I.

Проверяемый результат: сквозные fault/offline/capacity/deadline/HTTPS проверки после I плюс готовая benchmark-команда для будущего trained release. Реальные сервисные failure/recovery тесты обязательны сейчас; latency/VRAM/RAM модели остаются не измерены до weights. Не удалять пользовательские volumes и не открывать worker internet ради прохождения проверки.
Исходы: success: Fault/offline/queue/HTTPS проверки прошли; benchmark инструменты готовы. | noWeights: Настоящие latency/VRAM/RAM не измерены, synthetic цифры отдельно. | networkBlocked: Нет trusted external route — обязательный network gate blocked. | failure: Crash/retry/stale job/security regression — исправить A/O/I, затем повторить затронутые проверки.

### Разрешённые файлы

- `rules/__init__.py`
- `rules/engine.py`
- `rules/session_memory.py`
- `rules/types.py`
- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`
- `tests/rules/test_scene_reset.py`
- `docs/operations/RULES.md`
- `docs/operations/SOURCES.md`
- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/nginx.conf`
- `infra/redis.conf`
- `infra/env.example`
- `infra/scripts/preflight.sh`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-check.sh`
- `infra/scripts/smoke.sh`
- `docs/operations/SETUP.md`
- `docs/operations/NETWORK.md`
- `tests/performance/benchmark.py`
- `tests/performance/test_offline.py`
- `tests/performance/test_crash_retry.py`
- `tests/performance/test_capacity_deadline.py`
- `tests/performance/test_https.py`
- `tests/performance/test_service_resources.py`
- `docs/operations/RECOVERY.md`
- `docs/operations/BENCHMARK.md`
- `docs/operations/ACCEPTANCE.json`
- `rules/sources/snapshots.jsonl`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`
- `tests/rules/test_session_memory.py`
- `infra/scripts/preflight.ps1`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`
- `tests/performance/test_compose_isolation.py`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

### Критерии приёмки

1. Fault injection подтверждает durable PostgreSQL/outbox recovery при падении API/worker/Redis,повторной доставке и истёкшем lease: одно выполнение/один итог,без потерянного задания или ошибочного no_violation.
2. Capacity race допускает одно незавершённое задание до benchmark,остальным429; deadline≤240с от приёма приводит к failed при превышении,late result не затирает failure. Не более одного waiting job разрешается только после реальной оценки общего≤240с.
3. Worker offline smoke не делает интернет-запросов и сохраняет необходимые DB/queue связи; restart volumes восстанавливает jobs/media/models. Runtime downloads и облачная обработка отсутствуют.
4. Внешний HTTPS smoke на synthetic media реально проверяет сертификат,маршрут,auth,upload/poll/media и ошибки. CGNAT/сертификат/маршрут без подтверждения остаются blocked; конфигурация сама по себе не считается прохождением.
5. Benchmark CLI измеряет receipt→queue→decode→inference→rules→preview/evidence→response,elapsed от приёма и внешний upload→ответ; описаны warm/cold,p95,число прогонов,hardware/runtime/commit/dataset/release hashes и единицы памяти.
6. Для последующего trained release заложены цели service≤240с,внешний путь≤300с,145с video warm p95≤60с и каждый≤120с,VRAM train≤6,5ГБ/inference≤3ГБ,RAM train≤10ГБ/всего сервиса≤5ГБ. Сейчас реальные latency/память/ML performance остаются not measured,synthetic timings явно отдельно.
7. RECOVERY/BENCHMARK/ACCEPTANCE содержат фактические команды/exitCode/commit и blockers; отсутствие Docker/FFmpeg/CUDA/внешнего доступа не отмечается passed и не ослабляет обязательную программную/сетевую приёмку.
8. Проверены fencing stale worker и capacity race; safe checkpoint/volumes recovery не требует удаления пользовательских данных или повторной публикации проекта.

### Исходы и блокировки

- **success**: Fault/offline/queue/HTTPS проверки прошли; benchmark инструменты готовы.
- **noWeights**: Настоящие latency/VRAM/RAM не измерены, synthetic цифры отдельно.
- **networkBlocked**: Нет trusted external route — обязательный network gate blocked.
- **failure**: Crash/retry/stale job/security regression — исправить A/O/I, затем повторить затронутые проверки.

## Z — Финальная сдача

Разработчик №1. Фаза: integration. Зависимости: U, E, B.

Проверяемый результат: окончательная интеграция всех36 карточек через U/E/B, итоговый commit, software E2E и инструкция с готовностью/ограничениями. Все прямые и транзитивные prerequisites должны быть приняты после фактической проверки точных commits и критериев по GitHub-процессу. Текущий итог только implementation ready / training deferred либо blocked. Product ready + ML validated требует отдельного будущего обучения, imports и независимой ML/performance оценки.
Исходы: success: Все обязательные software/network acceptance подтверждены → implementation ready / training deferred. | blocked: Любой обязательный software/network критерий не пройден → blocked с точной причиной. | futureValidated: Только отдельный будущий train/import/independent ML+performance evaluation даёт product ready + ML validated. | review: Фактическая проверка точного commit и критериев по GitHub-процессу; самопроверка автора не называется независимой человеческой приёмкой.

### Разрешённые файлы

- `contracts/openapi.yaml`
- `contracts/job.schema.json`
- `contracts/diagnostics.schema.json`
- `contracts/events.schema.json`
- `contracts/manifest.schema.json`
- `contracts/annotations.schema.json`
- `contracts/release.schema.json`
- `contracts/taxonomy.draft.json`
- `contracts/fixtures.json`
- `contracts/OWNERSHIP.md`
- `contracts/DEPENDENCIES.md`
- `contracts/STACK.md`
- `tests/contracts/test_schemas.py`
- `docs/operations/LOCAL_ARTIFACTS.md`
- `config.example.toml`
- `pyproject.toml`
- `uv.lock`
- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/settings.py`
- `backend/app/auth.py`
- `backend/app/api.py`
- `backend/app/schemas.py`
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/storage.py`
- `backend/app/video.py`
- `backend/app/media.py`
- `backend/app/outbox.py`
- `backend/app/celery_app.py`
- `backend/app/tasks.py`
- `backend/app/jobs.py`
- `backend/app/deadlines.py`
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_jobs_outbox.py`
- `tests/api/conftest.py`
- `tests/api/fixture_runner.py`
- `tests/api/test_contract.py`
- `tests/api/test_auth_media.py`
- `tests/api/test_limits.py`
- `tests/api/test_outbox.py`
- `tests/api/test_idempotency.py`
- `tests/api/test_recovery.py`
- `backend/README.md`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ApiKeyForm.tsx`
- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/fixtures/contract-fixtures.ts`
- `frontend/src/App.test.tsx`
- `frontend/README.md`
- `ml/__init__.py`
- `ml/data/__init__.py`
- `ml/data/manifest.py`
- `ml/data/annotations.py`
- `ml/data/splits.py`
- `ml/data/safe_archive.py`
- `ml/data/pts_index.py`
- `ml/preflight.py`
- `ml/config/data.example.yaml`
- `tests/ml/test_manifest.py`
- `tests/ml/test_annotations.py`
- `tests/ml/test_splits.py`
- `tests/ml/test_safe_archive.py`
- `tests/ml/test_preflight.py`
- `docs/model/DATA.md`
- `docs/model/MISSING_MATERIALS.md`
- `ml/cli.py`
- `ml/models/__init__.py`
- `ml/models/encoder.py`
- `ml/models/temporal.py`
- `ml/preprocessing.py`
- `ml/windows.py`
- `ml/cache.py`
- `ml/train.py`
- `ml/evaluate.py`
- `ml/thresholds.py`
- `ml/export.py`
- `ml/release.py`
- `ml/inference.py`
- `ml/intervals.py`
- `ml/config/train.example.yaml`
- `ml/config/release.example.json`
- `tests/ml/test_shapes_masks.py`
- `tests/ml/test_pts_preprocessing.py`
- `tests/ml/test_cache_resume.py`
- `tests/ml/test_tiny_pipeline.py`
- `tests/ml/test_release_loader.py`
- `docs/model/TRAINING.md`
- `docs/model/CLI.md`
- `rules/__init__.py`
- `rules/engine.py`
- `rules/session_memory.py`
- `rules/types.py`
- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`
- `tests/rules/test_scene_reset.py`
- `docs/operations/RULES.md`
- `docs/operations/SOURCES.md`
- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/nginx.conf`
- `infra/redis.conf`
- `infra/env.example`
- `infra/scripts/preflight.sh`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-check.sh`
- `infra/scripts/smoke.sh`
- `docs/operations/SETUP.md`
- `docs/operations/NETWORK.md`
- `backend/app/pipeline.py`
- `backend/app/model_status.py`
- `backend/app/diagnostics.py`
- `tests/integration/conftest.py`
- `tests/integration/test_pipeline.py`
- `tests/integration/test_model_not_ready.py`
- `tests/integration/test_evidence_pts.py`
- `tests/integration/test_fixture_isolation.py`
- `tests/integration/test_release_import.py`
- `tests/e2e/playwright.config.ts`
- `tests/e2e/upload.spec.ts`
- `tests/e2e/video-evidence.spec.ts`
- `tests/e2e/errors-model.spec.ts`
- `tests/e2e/responsive-auth.spec.ts`
- `tests/e2e/report.json`
- `frontend/ACCEPTANCE.md`
- `tests/ml/test_cli_handoff.py`
- `tests/ml/test_release_compatibility.py`
- `tests/ml/test_export_budgets.py`
- `docs/model/EVALUATION.md`
- `docs/model/MODEL_CARD.template.md`
- `docs/model/HANDOFF.md`
- `docs/model/ACCEPTANCE.json`
- `tests/performance/benchmark.py`
- `tests/performance/test_offline.py`
- `tests/performance/test_crash_retry.py`
- `tests/performance/test_capacity_deadline.py`
- `tests/performance/test_https.py`
- `tests/performance/test_service_resources.py`
- `docs/operations/RECOVERY.md`
- `docs/operations/BENCHMARK.md`
- `docs/operations/ACCEPTANCE.json`
- `README.md`
- `docs/DELIVERY.md`
- `docs/licenses/THIRD_PARTY.md`
- `tests/integration/test_delivery.py`
- `tests/integration/delivery-evidence.json`
- `rules/sources/snapshots.jsonl`
- `contracts/__init__.py`
- `contracts/python_ports.py`
- `contracts/objects.schema.json`
- `contracts/dataset_readiness.schema.json`
- `contracts/OUTCOMES.md`
- `tests/api/test_persistence.py`
- `backend/app/api_upload.py`
- `tests/api/test_upload_decode.py`
- `tests/api/test_media_pts.py`
- `tests/api/test_capacity_race.py`
- `tests/api/test_deadlines.py`
- `frontend/src/api/client.test.ts`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`
- `docs/model/DATA_INVENTORY.md`
- `ml/data/taxonomy.py`
- `ml/config/object_taxonomy.draft.json`
- `ml/config/action_taxonomy.draft.json`
- `tests/ml/test_taxonomy.py`
- `docs/model/ANNOTATION_GUIDE.md`
- `docs/model/CASE_DATA_MAP.md`
- `ml/data/deduplicate.py`
- `tests/ml/test_deduplicate.py`
- `ml/data/scenes.py`
- `ml/data/extract_frames.py`
- `ml/data/extract_clips.py`
- `tests/ml/test_pts_index.py`
- `tests/ml/test_extraction.py`
- `docs/model/EXTRACTION.md`
- `ml/data/objects.py`
- `ml/data/coco_io.py`
- `ml/data/annotation_tasks.py`
- `ml/data/quality.py`
- `tests/ml/test_objects_coco.py`
- `tests/ml/test_annotation_quality.py`
- `docs/model/ANNOTATION_WORKFLOW.md`
- `ml/data_cli.py`
- `docs/model/DATA_READINESS.json`
- `tests/ml/test_data_pipeline.py`
- `docs/model/PREPROCESSING.md`
- `tests/ml/test_training_resume.py`
- `tests/ml/test_evaluation_export.py`
- `tests/ml/test_export_format.py`
- `tests/ml/test_inference_timeline.py`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`
- `tests/rules/test_session_memory.py`
- `infra/scripts/preflight.ps1`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`
- `tests/performance/test_compose_isolation.py`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

### Критерии приёмки

1. Все ветки K,A,F,D,M,R,O,I,U,E,B приняты после фактической проверки точных commits и критериев по GitHub-процессу,точные commit доступны и объединены в отдельной ветке. Нет потерянных изменений/секретов,git diff --name-status включает add/modify/delete и оба пути rename в разрешённой области.
2. На итоговом commit пройдены реальные integrated software checks:contract/auth/persistence/outbox/idempotency/recovery,UI с реальным API,production503 model_not_ready,test-only synthetic scenario с video seek и настоящими исходными кадрами fixture.
3. Поддержанные rule templates проверены positive/hard-negative/truncated/occlusion/exceptions; неподтверждённые нормы/неизвестные actors/невидимые условия остаются diagnostics unknown/unsupported с provenance и ограничениями.
4. ML preparation/train/resume/evaluate/export/import tools и инструкция другого ПК проверены только CPU tiny smoke; full training/fine-tuning/independent ML validation/реальные accuracy-F1/latency/VRAM/RAM и production export budget не приписаны текущей сборке.
5. Инфраструктура,ошибки,worker offline,volumes,retry/queue и внешнийHTTPS имеют фактическое evidence. Непройденный обязательный software/network критерий даёт blocked с точной причиной; отсутствие будущего trained release само по себе ожидаемо и честно отмечено.
6. README/DELIVERY содержат точный абсолютный projectDirectory итогового checkout(worktree)+rootPath,проверенный commit,команды подготовки/запуска/остановки,entrypoint,config/paths/секреты вне Git,лицензии зависимостей/весов,медиалимиты и подтверждённые ограничения. Не предлагают вложенную demo/test копию приложения.
7. Финальное evidence содержит настоящий baseCommit/head,изменённые пути,команды/exitCode и каждый актуальный acceptance; delivery v1 содержит фактический run projectDirectory/entryPoint/инструкцию,только реально доступный URL и все limitations.
8. Статус текущей сдачи только implementation ready / training deferred либо blocked. Product ready + ML validated возможен лишь после отдельного будущего обучения,импорта release и независимой сквозной оценки; красивый UI и fixtures не означают ML приёмку.

### Исходы и блокировки

- **success**: Все обязательные software/network acceptance подтверждены → implementation ready / training deferred.
- **blocked**: Любой обязательный software/network критерий не пройден → blocked с точной причиной.
- **futureValidated**: Только отдельный будущий train/import/independent ML+performance evaluation даёт product ready + ML validated.
- **review**: Фактическая проверка точного commit и критериев по GitHub-процессу; самопроверка автора не называется независимой человеческой приёмкой.
