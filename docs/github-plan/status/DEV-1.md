# Журнал разработчика №1

Рабочая ветка: `codex/fortress-backend`; интеграционная: `codex/integration`.
Checkout: `/home/almazcode/.codex/worktrees/fortress-backend/Fortress`.
Исходная база: `46b7bc941e64fec5649242b8290607c8f7339819`. Origin: `https://github.com/AlmazCode/Fortress`, rootPath пустой.
Проверка главным совпадает с авторской проверкой; независимая приёмка человеком не заявляется.

| Task | State | Commit | Проверки / следующий шаг |
| --- | --- | --- | --- |
| K | accepted | 2e44bf555ad1a824d92e73770a1ee85d1bf20d0f | 55 passed; доступен в integration |
| A1 | accepted | a84cce5e19c8b5a96286473aa9283c2c6b3a1194 | 10 passed на PostgreSQL 18.6; доступен в integration |
| A2 | accepted | df5dae07b4683afff88bdd06bfbf5b34bd7cc382 | 19 passed; доступен в integration |
| A3 | accepted | 6f7f5bf689440640bdc205642aefe7bf07a4d283 | 8 passed; доступен в integration |
| A4 | accepted | 61a69ce8edc254b4d62ab0652eb8f89df146e434 | 7 passed; реальный Redis/Celery |
| A5 | accepted | 4e5d9b09b292af03f27991b32cadf9aae2af64d6 | 8 fault/deadline tests; A1 rechecked |
| A | accepted | 043eeb6d125f3b77d71b74de3b56c6a1cee91e70 | 116 contracts/API tests; настоящий HTTP/Redis/PostgreSQL |
| I | blocked | — | Требуются A/F/M/R/O |
| Z | blocked | — | Требуются U/E/B после I |

## K — контракт (17 октября 2026)

Base: `46b7bc941e64fec5649242b8290607c8f7339819`; head: `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`. Изменены только:

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

Проверка: `uv run --locked --group test python -m pytest tests/contracts/test_schemas.py -q` → exit 0, **55 passed** на указанном неизменённом коде.
Критерий 1: ancestry/origin и OWNERSHIP. Критерии 2–5: OpenAPI, job/diagnostics, примеры ошибок и раздельных public/UI ответов. Критерии 6/11/13: events/objects/annotations и semantic validators unknown, PTS, evidence, coverage. Критерий 7: release schema с происхождением, хэшами и gate. Критерий 8: STACK/config/manifest. Критерии 9/12: test-only fixtures, lock и установленный Python 3.11. Критерий 10: OWNERSHIP/DEPENDENCIES и аудит 36 задач/48 рёбер.
Ограничения: taxonomy draft; реальных весов, ML-метрик и GPU readiness нет. Fixtures не подтверждают подлинность производственного анализа. Runtime endpoints проверяются A, а не K.

## A1 — persistence (17 октября 2026)

Base: `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`; head: `a84cce5e19c8b5a96286473aa9283c2c6b3a1194`. Изменены только:

- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/jobs.py`
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_jobs_outbox.py`
- `tests/api/test_persistence.py`

Проверка: `FORTRESS_TEST_DATABASE_URL=<private-test-dsn> FORTRESS_TEST_PG_CTL=<pg_ctl> FORTRESS_TEST_PGDATA=<private-cluster> FORTRESS_TEST_PGLOG=<private-log> uv run --locked --group test python -m pytest tests/api/test_persistence.py -q` → exit 0, **10 passed**. DSN задаёт изолированный Unix socket настоящего PostgreSQL 18.6; TCP выключен. Тесты создают/удаляют только собственные UUID-БД. Локальный запуск через `.aster/checkpoints/run-tests.py` подставляет эти параметры; это локальная история, не Aster workflow.
Критерий 1: upgrade/repeat/реальный restart и сохранность jobs/results/outbox. Критерий 2: публичные состояния и атомарный finish с валидацией. Критерий 3: 8 конкурентных create/claim, renewal/reclaim и fencing. Критерий 4: реальный connection outage, trigger-injected rollback create/finish, stale writes. Критерий 5: все persistence checks на настоящей БД, без mock замены.
Ограничения: это модульная проверка repository; Redis/worker, общий API и SLA ещё не проверены.

## A2 — рабочая проверка

Base: `c221374`. Проверка `python3 .aster/checkpoints/run-tests.py tests/api/test_upload_decode.py tests/api/test_limits.py -q` → exit 0, **17 passed in 3.15s**. Реальные FFmpeg 8.0.1 и PostgreSQL; readiness stub явно только тестовый. До commit/интеграции задача остаётся working.

## GitHub-переход

Документация `c70a6d366c9b48b090368b92ca1bb60b692f6c26` объединена обычным merge `c221374`; K/A1 сохранены. `python3 docs/github-plan/validate_plan.py` → exit 0; 36 задач, 48 рёбер, product criteria сохранены. Ветка integration создана на этом проверенном merge. K/A1 уже опубликованы в backend-ветке; публикация integration выполняется вместе с этим журналом. Aster MCP больше не используется.

## A2 — принят после проверки (17 октября 2026)

Base: `f90cdcd`; head: `df5dae07b4683afff88bdd06bfbf5b34bd7cc382`. Изменены `backend/app/storage.py`, `backend/app/video.py`, `backend/app/api_upload.py`, `tests/api/test_limits.py`, `tests/api/test_upload_decode.py`.
Проверка: `python3 .aster/checkpoints/run-tests.py tests/api/test_upload_decode.py tests/api/test_limits.py -q` → exit 0, **19 passed in 3.18s**, реальные FFmpeg/PostgreSQL. Два новых теста сначала воспроизвели неправильный envelope malformed multipart и незакрытый readiness error (exit 1), затем исправлены и прошли.
Критерий 1: metadata+full decode, обе ориентации, 61fps/181s/oversize и поддельное расширение. Критерий 2: VFR, display matrix rotation, ненулевой PTS, повреждённые/обрезанные файлы. Критерий 3: случайные имена/traversal, bounded multipart, реальный hanging subprocess, fsync fault. Критерий 4: 400/413/415/503 envelopes, уборка до принятия и сохранность оригинала после client cancellation. Критерий 5: model readiness/busy, настоящий durable job+outbox перед 202.
Ограничения: model readiness — явный test stub; auth и весь production routing проверяются A3/A. При неоднозначном исходе DB commit оригинал сохраняется для последующей reference-aware уборки. Принят главным после проверки и fast-forward integration; независимая приёмка не заявляется.

## A3 — авторизация и медиа (17 октября 2026)

Base: `38672c7`; head: `6f7f5bf689440640bdc205642aefe7bf07a4d283`. Файлы: `backend/app/auth.py`, `backend/app/media.py`, `tests/api/test_auth_media.py`, `tests/api/test_media_pts.py`.
`python3 .aster/checkpoints/run-tests.py tests/api/test_auth_media.py tests/api/test_media_pts.py -q` → exit 0, **8 passed in 4.40s**. Начальный RED: отсутствующие модули (7 failures); дополнительный тест выявил выдачу cached preview при изменённом оригинале, исправлено проверкой SHA-256 (RED→GREEN).
Критерий 1: middleware до роутинга/чтения тела, все API пути, missing/wrong/duplicate key, unknown job 404. Критерий 2: явно shared operator key, персональная изоляция не заявляется. Критерий 3: header-only, constant-time compare, no-store, generic errors без путей; приложение не пишет ключи/медиа в лог. Критерий 4: реальное VFR/rotation/nonzero PTS видео, покадровое сравнение времён preview и пикселей JPEG с независимым FFmpeg decode; 1–3 кадра. Критерий 5: missing media/frame, повреждённый original и JSONB JPEG возвращают явные ошибки, job/result сохраняются.
Ограничения: это модульный ASGI harness с реальным PostgreSQL/FFmpeg; итоговая установка middleware и access-log policy — A, browser Blob/seek — F/I/U. Реальная ML-подлинность не заявляется. Evidence provider работает с исходным видео; production runner будет подключён в I. Принято автором-главным и интегрировано.

## A4 — очередь и worker (17 октября 2026)

Base: `14e322a`; head: `61a69ce8edc254b4d62ab0652eb8f89df146e434`. Файлы: `backend/app/celery_app.py`, `backend/app/outbox.py`, `backend/app/tasks.py`, `tests/api/test_outbox.py`, `tests/api/test_idempotency.py`.
`python3 .aster/checkpoints/run-tests.py tests/api/test_outbox.py tests/api/test_idempotency.py -q` → exit 0, **7 passed in 4.55s** (первичный RED: 7 отсутствующих модулей). Настоящие PostgreSQL 18.6 и Redis 8.0.5 по закрытым Unix sockets, настоящий consumer Celery; fixture runner только внутри теста.
Критерий 1: job переживает отсутствие Redis; потеря данных Redis после publish восстанавливается из DB; crash-window publish-before-mark приводит к допустимому дублю. Критерий 2: 8 конкурентных исполнителей дают один вызов/один result, реальная duplicate delivery, stale owner rejected. Критерий 3: concurrency/prefetch=1, CPU env=2, shared host flock держится до конца вычисления даже при потере lease; admission race проверен A1. Критерий 4: heartbeat продлевает lease, expired owner заменяется, исключение становится durable failed, dispatcher завершает просроченный job. Критерий 5: один результат через настоящий транспорт и настоящую DB, production fallback отсутствует.
Ограничения: поддерживается один локальный GPU-хост и общий runtime-root/lock для всех его workers; распределённый GPU-кластер не заявляется. В тесте транспорта pool=solo; production prefork и принудительный kill проверяются A5/A. Реальный ML/SLA не проверялся.

## A5 и исправление A1 — сбои и дедлайны (17 октября 2026)

Base: `e0a1700`; head: `4e5d9b09b292af03f27991b32cadf9aae2af64d6`. A5: `backend/app/deadlines.py`, `tests/api/test_recovery.py`, `tests/api/test_capacity_race.py`, `tests/api/test_deadlines.py`. По воспроизведённой регрессии повторно открыт собственный A1: `backend/app/jobs.py` и `backend/app/db.py`; область других ролей не менялась.
Первый запуск выявил настоящий дефект: row lock задерживал finish после deadline, а старый caller timestamp позволял done. Исправлено: свежий PostgreSQL clock после захвата строки и после flush, rollback просроченного результата; ограничены statement/lock/idle transaction waits.
Проверки: `python3 .aster/checkpoints/run-tests.py tests/api/test_persistence.py tests/api/test_deadlines.py tests/api/test_capacity_race.py tests/api/test_recovery.py -q` → exit 0, **17 passed in 9.05s** (10 A1 + 7 A5). После добавления отдельного regression для медленной вставки: `python3 .aster/checkpoints/run-tests.py tests/api/test_deadlines.py -q` → exit 0, **5 passed in 3.56s**. Всего A5 покрыт 8 уникальными тестами, A1 повторно принят с исправлением в этом SHA.
Критерий 1: настоящий prefork Celery worker SIGKILL/restart, lease expiry, PostgreSQL result-trigger rollback/retry, уникальный итог; Redis outage/duplicates также проверены A4. Критерий 2: SIGALRM прерывает игнорирующий бюджет runner; из 240s вычитается upload/queue time; поздний return, row lock и slow insert не становятся done. Критерий 3: 8 настоящих upload/decode конкурируют за один durable slot, после failed слот освобождается. Критерий 4: durable reasons/нет результата при timeout/падении. Критерий 5: это модульные harness checks на настоящих сервисах, не внешний HTTPS/ML SLA.
Ограничения: runtime Linux, production prefork+жёсткий Celery limit; threaded harness не обеспечивает принудительное прерывание произвольного C/GPU вызова. Настоящие веса/GPU SLA отложены.

## A — собранный backend (17 октября 2026)

Base: `cc6f29a`; head: `043eeb6d125f3b77d71b74de3b56c6a1cee91e70`. Файлы: `backend/README.md`, `backend/app/api.py`, `main.py`, `schemas.py`, `settings.py`, `media.py`, `tasks.py`; `tests/api/conftest.py`, `fixture_runner.py`, `test_contract.py`, `test_idempotency.py`. Все 11 путей входят в files A.
Итог: `python3 .aster/checkpoints/run-tests.py tests/contracts tests/api -q` → exit 0, **116 passed in 32.34s**, без skipped. К этой проверке относятся фактические PostgreSQL 18.6 restart, Redis 8.0.5, FFmpeg 8.0.1 и localhost HTTP. `uv run --locked --group test python -m backend.app.main --help` → exit 0. `git diff --cached --check` → exit 0. Код после полного набора не менялся.
Критерий 1: реальный HTTP upload→durable job/outbox→Celery→done, processing/done/failed схемы и отдельные diagnostics. Критерий 2: middleware и все data/media маршруты; ошибочный ключ 401, отсутствующий ID 404; shared-key модель явно описана. Критерий 3: A2 decode/limits и новый HTTP 415. Критерий 4: настоящие миграции/outbox/Redis outage/повторный publish. Критерий 5: concurrent executor, unique result, SIGKILL/restart prefork, stale owner. Критерий 6: атомарный single-slot intake, concurrency/prefetch/CPU limits. Критерий 7: вся матрица 400/401/404/413/415/429/503, durable failed/unknown/deadline. Критерий 8: защищённые original/preview/frame по HTTP; preview PTS/rotation и JPEG source pixels проверены A3; Blob browser seek остаётся F/I/U. Preview входит в общий job budget и переиспользуется между API и worker по SHA. Критерий 9: locked окружение, README с запуском/остановкой/проверками/ограничениями.
При сборке выявлен shared-registration дефект Celery: новый app получал factory предыдущего runtime. Минимальный RED воспроизвёл 0 вместо 1 для второго app; app-local eager registration исправила причину. Targeted queue+HTTP набор → 12 passed; затем полный набор 116 passed.
Production не импортирует tests/fixtures: CLI production-only, явная test injection отвергается production settings. Test model endpoint сохраняет trained=false/validated=false/test_only=true; production без release возвращает model_not_ready. Это авторская проверка главного; ML/внешний HTTPS/browser acceptance не приписаны backend.

## Входящие кандидаты после обновления Git

После завершения A получены F1 `bab9998bb094605ceadbfb42412080fa1e0f3b3f` (отчёт `7e4279d`), D1 `536fe7af06cadb4ff9513da1bf8dcafb6e6198e6` (отчёт `9aa9dda`) и №4 `5834064` (O1/R и частичные O2/O3). Начинается проверка точных commits; они не приняты по одному отчёту. I ждёт F/M/R/O, O явно blocked по настоящему Docker/offline/external HTTPS.

## Проверка входящего F1

Авторский head: `bab9998bb094605ceadbfb42412080fa1e0f3b3f`; опубликованный отчёт: `7e4279d`. Главный прочитал 10 файлов F1, schema validators/key lifecycle/abort/retry/media byte cap/test-only transport, сверил scope и K. Обычный merge `f4ae1b5` содержит точный candidate и журнал №2; чужой код не исправлялся.
Собственные проверки на Node 24.21.0 / npm 12.2.0: `npm ci --ignore-scripts --no-fund --no-audit --registry=https://registry.npmjs.org` → 0; `npm run typecheck` → 0; `npm test -- src/api/client.test.ts` → 0, **42 passed**; `npm run build` → 0. `npm exec vite build -- --mode fixture` → 1, ожидаемый явный запрет. Production JS не содержит тестового ключа/fixture transport/payload markers. Lock использует только registry.npmjs.org.
F1 принят и интегрирован: это API-client scaffold, полный экран ещё не реализован (index загружает client.ts). Критерии 1–5 покрыты установленным lock/build/component tests, header-only memory key/reset, AJV K public/UI schemas, explicit synthetic transport и ограниченными retry/abort без повторного POST. Browser workflow/seek/адаптивность не заявляются. F2/F3/F4 теперь ready.
