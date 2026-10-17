# Разработчик №1 — Главный / Backend

Свои задачи: K, A1, A2, A3, A4, A5, A, I, Z.

## Как исполнять этот план через GitHub

Это перенос существующего плана, а не новый граф. ID, исполнители, files, acceptance и зависимости сохранены.
Последняя свежая сверка Aster недоступна из-за ошибки связи. Состояние задач здесь НЕ считается подтверждённым: сначала проверить имеющиеся ветки, коммиты и PR. Не повторять уже доказанную работу и не объявлять её готовой по старому снимку.

1. Каждый разработчик работает только в своей ветке и отдельном checkout/worktree. Номер направления постоянный; другие разработчики того же аккаунта могут работать параллельно. GitHub не запускает и не пробуждает чаты.
2. №1 владеет контрактом K, backend, общей интеграцией и финальной сдачей. №2 — frontend, №3 — ML/data, №4 — rules/infra. Общие файлы изменяет один заранее назначенный владелец.
3. K и O1 не имеют зависимостей. После проверенного K открываются соответствующие ветки; O1 может идти параллельно K. Затем выполнять только собственные задачи с закрытыми depends, а при блокере брать другую собственную готовую задачу.
4. Принятый prerequisite здесь означает проверенный результат в согласованной интеграционной ветке/PR с точным SHA. Открытый PR или локальный commit сами по себе не означают принятие. После интеграции брать актуальный контракт из Git, а не продолжать навечно от исходного initial commit.
5. Результаты передавать через обычные Git-коммиты и PR при действующем разрешении пользователя. Главный проверяет точные коммиты, объединяет совместимые изменения и выполняет финальные сквозные проверки. Защиту веток и требуемые проверки GitHub соблюдать.
6. Каждый редактирует только свой status/DEV-N.md: task ID, состояние, branch, commit/PR, реально запущенные проверки, блокер и следующее действие. Главный ведёт STATUS.md. Не давать четырём разработчикам одновременно менять один общий журнал.
7. Продолжать последовательно по своему направлению без вопроса на каждую задачу в пределах разрешённого запуска. Если ждёшь чужую работу, проверять Git/PR ограниченными интервалами в активном ходе; не изображать фоновое выполнение после остановки чата.
8. Ресёрч только для текущего обязательного пробела, с контрольной точкой после двух бесплодных заходов. Не добавлять карточки, не ослаблять acceptance и не заменять проверки формальным отчётом. Конфликты разрешать по контракту и фактическому коду, сохраняя чужие изменения.
9. Обучение модели остаётся на другом локальном ПК. Сейчас нужны CLI, tiny CPU smoke, инструкции и честный model_not_ready без весов. Не запускать полное обучение и не объявлять качество/производительность подтверждёнными без реальных данных.

### Что меняется относительно Aster

MCP-claim заменяется закреплённым разработчиком, веткой и собственным журналом. Aster accepted заменяется проверенной интеграцией точного Git-коммита. Heartbeat не нужен для разрешения работать через GitHub. Не вызывать Aster MCP ради регистрации, ожидания, смены статуса или сдачи в этом режиме.

Исходные описания ниже дословные и содержат исторические указания «сейчас только план», manual, MCP и запрет push/PR/merge. Экспорт сам по себе не даёт разрешения исполнять код или публиковать что-либо. После явного нового запуска пользователем административный порядок задаётся его текущей инструкцией и этим GitHub-процессом; продуктовые требования и acceptance сохраняются. Новая инструкция не отменяет ограничения на обучение, секреты, данные и внешнюю публикацию.

### K — Контракт API и данных

Разработчик: №1. Тип: contract. Фаза: contract.
Зависимости: нет. Состояние: не сверено с Git.

Файлы:

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

Критерии приёмки:

- Зафиксированы origin/main/baseCommit 46b7bc941e64fec5649242b8290607c8f7339819, rootPath='', проектный корень и точные files всех четырёх ролей; общий файл не редактируется параллельно.
- POST /api/v1/analyze принимает X-API-Key и multipart file, возвращает 202 {job_id} только после сохранения; GET /api/v1/jobs/{job_id}: processing/done/failed, queued/running остаются внутренними.
- Публичная схема done содержит verdict violation/no_violation и violations; violation ⇔ violations непуст. События имеют type,timecode_sec,description,evidence_frames[{timestamp_sec,image_base64}]; 1–3 подлинных JPEG без data-префикса. Никакие UI-поля не добавляются во внешний контракт жюри.
- Отдельно описаны защищённые /api/ui/v1/jobs/{job_id}, /api/ui/v1/model и media/preview endpoints: интервалы, стадии, источники, версии, unknown/unsupported и ограничения. UI ключ хранится в памяти вкладки, fetch с заголовком, Blob видео до 200 МиБ с освобождением Object URL; ключ не попадает в bundle, URL, storage или логи.
- Схемы фиксируют ошибки 400/401/404/413/415/429/503, model_not_ready до принятия анализа, failed с причиной после приёма; лимиты 200 МиБ/180 с/1920×1080 либо 1080×1920/60 fps, VFR/rotation/исходные PTS и отсутствие облака, audio и face recognition.
- Внутренний ActionTimeline содержит интервалы исходного времени, scores, visibility/known masks, scene_id и unknown actor/relations; RuleFinding = triggered/not_triggered/unknown с source provenance. Политика неполной наблюдаемости не превращает unknown в доказательство отсутствия нарушения.
- Release schema требует checkpoint, backbone/config/feature_dim, taxonomy, preprocessing, thresholds, metrics/model card, dataset/split/annotation/rules versions и SHA-256 manifest. Untrained/test fixtures несовместимы с production readiness; без release 503. Draft taxonomy не изображает известные 25 классов.
- Согласованы manifest/annotation/split formats, ключ кэша preprocessing+encoder+dataset, frozen encoder+GRU baseline и пример конфигурации: 224 letterbox,2 fps,32 frames,50% overlap,hidden=256,1 layer,576 features assertion. Официальный стандартный center crop Torchvision не смешан с проектным letterbox.
- Все контрактные fixtures явно test-only и валидируются схемами: processing/done/failed, отсутствие модели, unknown, ошибки, synthetic provenance. Определены команды версионирования и lock-файлы; версии/CUDA не объявлены проверенными до фактического preflight.
- Четыре роли №1–№4, точные files и все36 карточек перечислены сразу. K и ранний O1 — независимые корни; implementation leaves после K доступны по реальным зависимостям. У №4 задачи последовательны по доступности без искусственных depends. Только U/E/B имеют helperFor=Z; сейчас помощники/код не запускаются.
- Версионированы object bbox/visibility/review schema, temporal annotation, sourcePTS/time_base/origin mapping, dataset readiness и module ports. Object dataset не означает выбранный object detector; legal/actor/observability unknown не превращаются в false.
- Python3.11 dependencies/CPU test extras и выбранный стек совместно зафиксированы pyproject/uv.lock; target CUDA/GPU readiness проверяется O1, несовместимость версии требует исправления общего контракта, не четырёх локальных копий.
- Полностью недостаточная наблюдаемость не даёт clean verdict: job становится failed с reason=insufficient_evidence. Частичная coverage/unknown явно описана diagnostics/UI; публичный done не получает третьего verdict. no_violation означает отсутствие найденных поддержанными проверками нарушений, не доказанную безопасность всех кейсов.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: единый public/UI/data/release контракт, модульные порты и ownership для36 этапов. Исходные требования и внешняя jury схема сохранены; taxonomy пока draft. Прочитать объединённое ТЗ, фактические приложения и официальные API. Достаточность исследования: каждое независимое направление знает inputs/outputs/errors/versions/files и способы проверки. Отсутствующие25 классов/исходный кейс не выдумывать. Baseline и запрет training/cloud/face/audio сохраняются.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Контракты/schema fixtures/ownership проходят проверки, можно принять K и открыть leaves. | missing: Неизвестная taxonomy/норма/данные — draft/unknown с точным пробелом; UI/API остаются определимыми. | failure: Противоречивый public/schema/module контракт — blocked до исправления K.

</details>

### A1 — БД и состояние заданий

Разработчик: №1. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/jobs.py`
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_jobs_outbox.py`
- `tests/api/test_persistence.py`

Критерии приёмки:

- Migration upgrade на пустой PostgreSQL, повторный запуск и restart проверены: job/result/outbox не теряются.
- queued/running отображаются как processing; done/failed и invariant verdict↔violations фиксируются транзакционно.
- JobRepository реализует порт K: durable create, atomic lease/fencing, unique result. Конкурентные транзакции не захватывают одно задание дважды.
- DB outage/rollback не возвращает ложный202/done; частичный и устаревший результат не виден как успешный.
- Реальная БД обязательна для persistence acceptance; mock не заменяет этот тест.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: PostgreSQL repository и миграции jobs/results/outbox с явными состояниями и уникальными ключами.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Durable repository готов для A4/A. | missing: Нет PostgreSQL/credentials — persistence acceptance blocked, code tests отдельно. | failure: Rollback/миграция/двойной claim — исправить A1; пользовательскую БД не сбрасывать.

</details>

### A2 — Приём и проверка видео

Разработчик: №1. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `backend/app/storage.py`
- `backend/app/video.py`
- `backend/app/api_upload.py`
- `tests/api/test_limits.py`
- `tests/api/test_upload_decode.py`

Критерии приёмки:

- MP4/MOV:200МиБ,180с,1920×1080 либо1080×1920,≤60fps проверяются metadata и bounded decode; extension недостаточно.
- VFR, rotation, ненулевой начальныйPTS, битый/обрезанный файл покрыты synthetic clips; sourcePTS/time_base/origin mapping сохраняется.
- FFmpeg вызывается без shell с лимитами времени/CPU/размера; traversal, over-limit stream, decode hang и disk failure не дают accepted job.
- 400/413/415 и инфраструктурный503 соответствуют K. Временный файл очищается при отказе до принятия; принятый оригинал не удаляется из-за разрыва клиента.
- Model missing/busy дают503/429 до принятия;202 возможен только после durable file+job+outbox. Настоящая сборка проверяется в A.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Ограниченный upload/ffprobe/decode и подготовка media для durable job port с исходным временем.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Валидный оригинал и time mapping переданы в durable port. | invalid: Медиа не проходит лимиты/декодирование —4xx без job. | failure: Диск/декодер/сохранение недоступны — service failure, без вердикта. | clientLost: До durable accept — cleanup; после accept job продолжает выполнение.

</details>

### A3 — Авторизация и медиа

Разработчик: №1. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `backend/app/auth.py`
- `backend/app/media.py`
- `tests/api/test_auth_media.py`
- `tests/api/test_media_pts.py`

Критерии приёмки:

- X-API-Key обязателен для job/result/diagnostics/media/frame endpoints;401 без/с неверным ключом,404 неизвестногоjob.
- Один shared key не объявляется per-user isolation; multi-user права требуют отдельного контракта. СлучайныйID не заменяет auth.
- Ключ не попадает в URL/bundle/logs; paths и содержимое видео не логируются. Protected fetch совместим с Blob≤200МиБ.
- Preview сохраняет исходное time mapping/rotation;1–3 JPEG evidence frames принадлежат исходному видео, base64 без data-prefix.
- Битый/отсутствующий кадр или preview даёт явную ошибку и не стирает job/result; public jury schema не расширяется.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Авторизация всех endpoints данных и protected media/preview с проверяемым временем.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Авторизованный оператор видит свой выбранный job и его исходные media. | denied: Нет/неверный ключ→401; нет job→404 без выдачи путей. | partial: Нет preview/кадра — media error, без выдуманного доказательства. | scope: Shared key не означает персональную изоляцию пользователей.

</details>

### A4 — Outbox и один worker

Разработчик: №1. Тип: code. Фаза: implementation.
Зависимости: A1. Состояние: не сверено с Git.

Файлы:

- `backend/app/outbox.py`
- `backend/app/celery_app.py`
- `backend/app/tasks.py`
- `tests/api/test_outbox.py`
- `tests/api/test_idempotency.py`

Критерии приёмки:

- Job+outbox commit атомарен; crash между DB commit и publish, Redis down и повторный publish восстанавливаются без потери job.
- Duplicate delivery/конкурентные workers не создают второй анализ/result; stale owner не фиксирует результат после нового lease.
- Concurrency=1, prefetch/CPU threads ограничены. До benchmark второй незавершённый job получает429 атомарно, backlog отсутствует.
- Crash/restart/acks/retry имеют управляемые конечные состояния; pending job не висит бесконечно, failed сохраняет причину.
- Тест с настоящими PostgreSQL/Redis подтверждает один результат. Fixture runner только test profile, production fallback отсутствует.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Durable outbox PostgreSQL→Celery/Redis и один активный GPU job с fencing/idempotency.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Одно принятое задание даёт один устойчивый итог. | brokerDown: Outbox сохраняет job и восстанавливает доставку в пределах deadline. | duplicate: Повторная доставка не дублирует анализ/result. | workerCrash: Новый lease/fencing, stale commit отвергается. | busy: Конкурентный intake→429; очередь не расширяется без benchmark.

</details>

### A5 — Дедлайны и сбои backend

Разработчик: №1. Тип: test. Фаза: verification.
Зависимости: A2, A3, A4. Состояние: не сверено с Git.

Файлы:

- `backend/app/deadlines.py`
- `tests/api/test_recovery.py`
- `tests/api/test_capacity_race.py`
- `tests/api/test_deadlines.py`

Критерии приёмки:

- Kill/restart worker, Redis outage, DB rollback и duplicate delivery не теряют job/result и не создают ложный no_violation.
- Deadline≤240с от приёма: exceeded→failed; late result не возвращает done. Учтены очередь и декодирование.
- Concurrent intake сохраняет одно незавершённое задание; failure освобождает capacity корректно.
- Ошибка после принятия становится durable failed с причиной; падение процесса не считается отрицательным анализом.
- Command/exitCode/commit и failed/not_run записаны честно; модульный harness не называется полным пользовательским сценарием.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Fault-injection проверки intake/auth/queue/repository до общей API-сборки.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Failure/retry/deadline semantics готовы для A. | timeout: Deadline→failed и освобождение capacity. | failure: Потеря job/двойной result/stale commit — blocked до исправления. | notRun: Нет DB/Redis — соответствующие checks not_run, не passed.

</details>

### A — API и надёжная очередь

Разработчик: №1. Тип: code. Фаза: integration.
Зависимости: A5. Состояние: не сверено с Git.

Файлы:

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

Критерии приёмки:

- Реальные API-тесты проверяют 202 после сохранения, статусы processing/done/failed, неизменённую публичную схему, invariant verdict/violations и отдельные UI diagnostics; отказ валидации не создаёт accepted job.
- Все job/result/media/preview/frame endpoints закрыты авторизацией. Тестами подтверждены 401 без/с неверным ключом, 404 чужого/отсутствующего ID по выбранной модели доступа; ключи, файловые пути и видео отсутствуют в логах/URL.
- MP4/MOV проверяются метаданными и ограниченным фактическим декодированием: 200 МиБ,180 с,разрешение в обеих ориентациях,60 fps,VFR/rotation/PTS; FFmpeg запускается списком аргументов без shell, имена случайные, лимиты CPU/времени и damaged media покрыты тестами.
- Миграции PostgreSQL создают jobs/results/outbox и ограничения уникальности. Crash между DB commit и publish, недоступный Redis и повторный publish восстанавливаются без потери задания.
- Конкурентная повторная доставка даёт один анализ и один результат: атомарный lease/fencing и транзакционная фиксация; падение worker, expired lease и deadline не превращаются в done/no_violation.
- GPU-worker concurrency=1, prefetch/CPU threads ограничены; до реального benchmark система принимает только одно незавершённое задание без backlog, второму возвращает 429. Последующее разрешение одного ожидающего требует прогнозируемого общего бюджета ≤240 с.
- Тесты покрывают все ошибки 400/401/404/413/415/429/503 и post-accept failed. Deadline учитывает время от приёма, просроченный результат не становится успешным; успешные fixture timings отдельно от непроверенных SLA модели.
- Защищённый preview fetch/Blob позволяет HTML video seek с исходным отображением времени; соответствие PTS и 1–3 исходных evidence frames проверено на синтетическом видео. Настоящие model/rules будут подключены в I.
- Зависимости разрешены для Python 3.11 и согласованного стека, зафиксирован uv.lock; backend/README содержит реальные команды targeted тестов и ограничения; тесты persistence/queue выполнены с реальными PostgreSQL/Redis при исполнении, недоступные сервисы не объявлены пройденными.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: собранный настоящий FastAPI из принятых A1–A5: upload/status/auth/media, PostgreSQL/outbox/Celery и tests на реальных сервисах. Собрать main/settings/schemas/API routing и fixture runner только test profile. Не повторять модульные задачи отдельными копиями; исправлять существующие карточки. Общие locks K не менять параллельно другим веткам без обновлённого контракта.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Настоящий API с persistence/queue/auth прошёл проверки. | missing: Нет реальных DB/Redis/runtime — интеграционная acceptance blocked, mocks отдельно. | noModel: Production503 ожидаем, synthetic runner только test. | failure: API/security/persistence regression — исправить соответствующую A1–A5, затем сборку A.

</details>

### I — Интеграция без весов

Разработчик: №1. Тип: code. Фаза: integration.
Зависимости: A, F, M, R, O. Состояние: не сверено с Git.

Файлы:

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

Критерии приёмки:

- В integration packet присутствуют принятые A/F/M/R/O и их транзитивные K/D, реальные SHA доступны и интегрированы; изменённые пути находятся в files, конфликты разрешены, итоговый commit зафиксирован.
- UI production build общается с настоящим FastAPI,PostgreSQL и Celery; contract tests проверяют публичную схему и отдельный diagnostics,авторизацию,ошибки и persistence.
- Без обученного совместимого usable release POST analyze возвращает 503 model_not_ready и UI инструкцию импорта; нет случайного результата,ложного done/no_violation и скрытого fallback на fixtures.
- Fixture runner и tiny smoke releases доступны только явно отдельному test/demo profile с меткой synthetic. Production config отвергает их и не принимает untrained package.
- На явно тестовом synthetic media пройден путь upload→outbox→worker→интервалы→rules→result→video seek; 1–3 evidence frames взяты из соответствующего исходного файла/PTS,а не нарисованы/взяты из другого ролика.
- Память сбрасывается при смене сцены,unknown actors/observability и неподтверждённые нормы сохраняются в diagnostics; unsupported кейсы не становятся юридически названными нарушениями.
- Проверены retry/duplicate dispatch,auth на media,защищённый Blob playback и корректные failed/deadline; production code не вызывает cloud AI,face recognition,audio analysis или runtime network downloads.
- Сборка и targeted integration checks фактически выполнены с командами/exitCode/commit. Итог — программная интеграция; training/independent ML evaluation/реальный model benchmark остаются отложенными, обязательный software failure фиксируется blocked.
- E2E fixture полностью unknown даёт failed insufficient_evidence; partial coverage/unknown явно видна UI. Пустой violations не используется как доказательство отсутствия невидимого действия.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: интегрированные A/F/M/R/O и все их текущие принятые ancestors в одной собственной ветке с реальными commits. Соединить UI/API/repository/outbox/worker/inference/rules/media/diagnostics, реально запустить полный Compose при доступной среде. Без trained compatible release production возвращает503; test/demo fixtures явно отделены. Приёмочные U/E/B — заранее перечисленные дочерние Z; на стадии планирования чаты не создаются.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Полная software интеграция прошла, открываются U/E/B. | noRelease: Production503 и инструкция импорта; test journey только с explicit synthetic profile. | failure: Контракт/медиа/очередь/Compose/rules wiring не проходит — fix профильной карточки и повтор I. | unknown: Неизвестные ML/legal capabilities явно в diagnostics; fixtures не валидируют их.

</details>

### Z — Финальная сдача

Разработчик: №1. Тип: code. Фаза: integration.
Зависимости: U, E, B. Состояние: не сверено с Git.

Файлы:

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

Критерии приёмки:

- Все ветки K,A,F,D,M,R,O,I,U,E,B приняты по manual policy,точные commit доступны и объединены в отдельной ветке. Нет потерянных изменений/секретов,git diff --name-status включает add/modify/delete и оба пути rename в разрешённой области.
- На итоговом commit пройдены реальные integrated software checks:contract/auth/persistence/outbox/idempotency/recovery,UI с реальным API,production503 model_not_ready,test-only synthetic scenario с video seek и настоящими исходными кадрами fixture.
- Поддержанные rule templates проверены positive/hard-negative/truncated/occlusion/exceptions; неподтверждённые нормы/неизвестные actors/невидимые условия остаются diagnostics unknown/unsupported с provenance и ограничениями.
- ML preparation/train/resume/evaluate/export/import tools и инструкция другого ПК проверены только CPU tiny smoke; full training/fine-tuning/independent ML validation/реальные accuracy-F1/latency/VRAM/RAM и production export budget не приписаны текущей сборке.
- Инфраструктура,ошибки,worker offline,volumes,retry/queue и внешнийHTTPS имеют фактическое evidence. Непройденный обязательный software/network критерий даёт blocked с точной причиной; отсутствие будущего trained release само по себе ожидаемо и честно отмечено.
- README/DELIVERY содержат точный абсолютный projectDirectory итогового checkout(worktree)+rootPath,проверенный commit,команды подготовки/запуска/остановки,entrypoint,config/paths/секреты вне Git,лицензии зависимостей/весов,медиалимиты и подтверждённые ограничения. Не предлагают вложенную demo/test копию приложения.
- Финальное evidence содержит настоящий baseCommit/head,изменённые пути,команды/exitCode и каждый актуальный acceptance; delivery v1 содержит фактический run projectDirectory/entryPoint/инструкцию,только реально доступный URL и все limitations.
- Статус текущей сдачи только implementation ready / training deferred либо blocked. Product ready + ML validated возможен лишь после отдельного будущего обучения,импорта release и независимой сквозной оценки; красивый UI и fixtures не означают ML приёмку.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: окончательная интеграция всех36 карточек через U/E/B, итоговый commit, software E2E и инструкция с готовностью/ограничениями. Все прямые и транзитивные prerequisites должны быть приняты по manual policy. Текущий итог только implementation ready / training deferred либо blocked. Product ready + ML validated требует отдельного будущего обучения, imports и независимой ML/performance оценки.
Исполнитель №1. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Все обязательные software/network acceptance подтверждены → implementation ready / training deferred. | blocked: Любой обязательный software/network критерий не пройден → blocked с точной причиной. | futureValidated: Только отдельный будущий train/import/independent ML+performance evaluation даёт product ready + ML validated. | manual: Submitted/review не accepted. Нужен другой реальный участник или явная ручная приёмка, самопроверка автора не разблокирует зависимости.

</details>
