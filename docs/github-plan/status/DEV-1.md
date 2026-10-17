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
| A3 | working | — | K принят; auth/preview/evidence |
| A4 | ready | — | A1 принят; после A3 |
| A5 | blocked | — | Требуются A2/A3/A4 |
| A | blocked | — | Требуется A5 |
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
