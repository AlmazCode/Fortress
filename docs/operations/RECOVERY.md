# Восстановление: границы готовности и порядок проверки

Пользователь 17.10.2026 отложил WSL/виртуализацию. Они не устанавливаются/не включаются в этой работе. Без контейнеров принятый backend можно запускать на **native Linux**; он использует fcntl/flock, POSIX signals и Celery prefork. На текущем native Windows полная эквивалентность не реализована. Замена на solo/SQLite/in-memory queue не закрывает требования надёжности. Клиент HTTP, frontend build и sampler работают на Windows без VM.

Реальные recovery/capacity/offline acceptance B выполняются после принятого I в изолированном runtime, с явным synthetic runner и своими DB/Redis/media/model каталогами. До этого здесь есть runbook и инструменты, не отчёт о выполненном восстановлении. Не менять общий STATUS/граф и не выдавать модульные A1–A5 за full-stack B.

## Native Linux, production без весов

Установленные и проверенные локальные PostgreSQL/Redis/FFmpeg, Python 3.11 и shared lock; private environment из backend README. Runtime/model paths — вне checkout. В трёх терминалах:

```sh
uv sync --locked
uv run --locked python -m backend.app.main migrate
uv run --locked python -m backend.app.main api --host 127.0.0.1 --port 8000
# Другой терминал с тем же private environment/runtime root:
uv run --locked python -m backend.app.main worker
```

Это команды принятого A. Перед стартом API/worker миграция должна успешно закончиться. CLI требует FORTRESS_API_KEY, DATABASE_URL, REDIS_URL, absolute FORTRESS_RUNTIME_ROOT; release root не означает model readiness. API содержит outbox/deadline sweep. Для отдельного dispatcher есть `python -m backend.app.main dispatch`. Native запуск сам по себе не блокирует worker internet: нужная OS policy и проверка DB/Redis connectivity/egress остаются отдельным gate.

Production upload без trained release ожидаемо 503. Настоящий test runner CLI ещё должен дать I; подстановка несуществующих flags/env не допускается. Nginx/TLS/внешний маршрут требуют фактического hostname/certificate и разрешённого incoming transport; случайный туннель или upload в облако не используются.

## Безопасная остановка и backup

Остановить intake, дождаться bounded worker либо зарегистрировать намеренный test fault. До обслуживания runtime исключить активный worker, сохранить общий gpu.lock path, lease/fencing history и original references. Не удалять принятые originals при client cancellation/неоднозначном DB commit; orphan cleanup разрешён только после reference-aware проверки с закрытым intake.

Backup: согласованный PostgreSQL dump и закрытая копия media/models, Redis persistence. Например `pg_dump --format=custom --file /PRIVATE/fortress.dump` с отдельным private libpq environment/PGPASSFILE; пароль/DSN не помещать в командную историю/лог. Проверить dump и восстановить в **новую отдельную тестовую БД/папку**, затем сверить jobs/results/outbox и media/release SHA. Рабочую БД не очищать ради проверки. Версия pg_dump/pg_restore должна соответствовать серверу и фактически пройти restore test.

Для Compose сохранены named volumes; stop/up без удаления volumes. Не использовать down -v/prune/FLUSHALL/clean пользовательских файлов для recovery. При замене модели сначала проверить новый release/hashes в отдельном каталоге; сохранить предыдущий пригодный release и выполнить согласованный rollback без удаления данных.

## Матрица после I

| Сбой в отдельном synthetic stack | Наблюдение и проверяемый результат |
| --- | --- |
| API после durable 202 | Accepted job/original/outbox остаются в PostgreSQL/на диске; после restart тот же ID доступен, нет ложного done |
| Worker SIGKILL на своём зарегистрированном PID | До завершения прежнего вычисления shared host flock не даёт второй GPU execution; после lease expiry repair/retry даёт один durable result до deadline либо failed |
| Redis outage / утрата только отдельного test broker state | Job не теряется, outbox из PostgreSQL перепубликует; duplicate task не создаёт второй результат/вычисление |
| Поздний/stale owner | Fencing/version/deadline отвергают result; failed не перезаписывается done |
| DB outage / finish rollback | Нет частичного result; принятый original сохраняется; после восстановления подтверждается ровно один итог |
| 8 одновременных upload | При одном atomic unfinished slot только один 202, остальные 429; после failed/done слот освобождается |
| Runtime restart с теми же persistent roots | Сохраняются jobs/media/models/hashes; чужие каталоги не заменяются пустыми |
| Полностью unknown fixture | Durable failed/insufficient_evidence, без clean verdict; partial unknown явно остаётся в diagnostics |
| Worker offline policy | DB/Redis доступны, исходящие probes отвергнуты, runtime downloads отсутствуют; TCP probes не доказывают изоляцию всех протоколов |

На native Linux SIGKILL применим только к PID, полученному от собственного test launcher и сверённому с command/UID/runtime root. Не искать общий worker через широкие pidof/pkill. В этой сессии такие faults и service restarts не выполнялись. Windows C/GPU timeout не заменять threaded alarm или solo.

Для модульных A1–A5 существуют настоящие проверки `tests/api/test_persistence.py`, `test_outbox.py`, `test_idempotency.py`, `test_recovery.py`, `test_capacity_race.py`, `test_deadlines.py`; запускать по backend README на своём PostgreSQL с правом создавать UUID test DB и закрытых Redis Unix sockets. Их успех подтверждает соответствующие модули. После I нужна отдельная full-stack проверка через [реальный HTTP-клиент](BENCHMARK.md), с командами test launcher/fault/restart, точными SHA и exit codes. Пока I не принят, недостающий full-stack fault test не подменяется parser/static/fixture pass.

## Текущее состояние

O2: исправлены backend CLI/env/health и frontend COPY; Compose config и native frontend build проверены, container build/start/volume restart/offline/GPU не выполнены. O3: local HTTP/TLS clients проверены, trusted внешний маршрут не предоставлен. B: tooling подготовлено, actual recovery/server-stage timings/память модели/внешний путь не измерены. Общий outcome **blocked**, а не accepted; [ACCEPTANCE.json](ACCEPTANCE.json) перечисляет фактические доказательства.
