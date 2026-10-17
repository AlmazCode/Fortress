# Fortress backend

Рабочая копия №1: `/home/almazcode/.codex/worktrees/fortress-backend/Fortress`. Ветки `codex/fortress-backend` и `codex/integration`; точные принятые SHA и проверки — в [журнале №1](../docs/github-plan/status/DEV-1.md).

Это собранная программная часть API/очереди. Production сейчас **не загружает обученную модель**: `/api/ui/v1/model` сообщает `not_ready`, upload возвращает `503 model_not_ready`. Подключение проверенных M/R/F/O выполняется в I. Никаких случайных весов, фиктивных production verdict или полного обучения здесь нет.

## Требования и подготовка

Linux (в том числе Linux-контейнер), Python 3.11, uv, FFmpeg/ffprobe с libx264, PostgreSQL и Redis. Зависимости Python зафиксированы в корневом `uv.lock`. Фактически проверены PostgreSQL 18.6, Redis 8.0.5, FFmpeg 8.0.1. CUDA и ML SLA не проверялись.

Из корня checkout:

```sh
uv sync --locked --group test
```

Настройте переменные окружения локально, без записи секретов в Git или командную историю:

- `FORTRESS_API_KEY`: случайный общий ключ оператора, не менее 16 ASCII-символов без пробелов. Одинаковый ключ не обеспечивает персональные права пользователей.
- `DATABASE_URL`: DSN PostgreSQL, доступный API и worker; роль имеет права на схему Fortress. Для тестов используйте отдельную роль/кластер с правом создавать временные БД.
- `REDIS_URL`: локальный Redis (`redis://…`, `rediss://…` или `redis+socket:///…?virtual_host=0`). У API и worker один брокер.
- `FORTRESS_RUNTIME_ROOT`: абсолютный локальный каталог **вне Git**, общий для API и всех worker-процессов этого GPU-хоста. Он содержит private originals, previews и `gpu.lock`.
- `FORTRESS_RELEASE_ROOT`: необязательный абсолютный каталог будущего release; сам по себе путь не открывает readiness gate.
- `FORTRESS_CONFIG`: необязательный путь к TOML на основе `config.example.toml`; runtime/release paths можно задать там, секреты читаются только из окружения. CLI допускает только production.

Не меняйте `gpu.lock` между workers. Поддерживается один локальный GPU-хост; кластер с разными host-local locks не поддерживается. Сервисы PostgreSQL/Redis не следует публиковать наружу. TLS/Compose/offline-worker принадлежат O и не подтверждаются этими локальными тестами.

## Запуск и остановка

На настроенной PostgreSQL выполните идемпотентную миграцию, затем запустите API и worker в отдельных терминалах:

```sh
uv run --locked python -m backend.app.main migrate
uv run --locked python -m backend.app.main api --host 127.0.0.1 --port 8000
uv run --locked python -m backend.app.main worker
```

API lifespan уже выполняет outbox/deadline sweep раз в секунду. Если dispatcher требуется отдельным процессом, доступна команда `uv run --locked python -m backend.app.main dispatch`; одновременные sweep допускают безопасную повторную доставку. API следует держать активным для завершения просроченных заданий, либо запускать отдельный dispatcher.

Остановка: `Ctrl+C` в терминалах API/worker/dispatcher. Дождитесь завершения worker перед обслуживанием runtime-каталога. Не удаляйте originals/results при остановке и не сбрасывайте PostgreSQL. После рестарта queued/expired-lease задания восстанавливаются из outbox до дедлайна; после дедлайна получают durable failed. Принятый original сохраняется при разрыве клиента. Неоднозначный DB commit тоже сохраняет файл: автоматическая очистка таких orphan-файлов пока не реализована, удалять их можно только после проверки ссылок БД и остановки intake/worker.

`/healthz` проверяет только liveness. Все `/api/…` защищены `X-API-Key`, включая model/status/diagnostics/media/preview/frame. Access logs отключены командой запуска; не включайте запись заголовков/query/body в reverse proxy. Передавайте ключ только заголовком, не URL. Документация API — [зафиксированный OpenAPI](../contracts/openapi.yaml).

## Поведение

- MP4/MOV: ≤200 МиБ, ≤180 секунд, ≤60 fps, максимум 1920×1080 или 1080×1920. Metadata и настоящее декодирование проверяются; имя/расширение недостаточны. VFR, display rotation и исходные PTS сохраняются.
- `202 {job_id}` выдаётся после fsync оригинала и атомарного commit jobs/outbox. До benchmark принимается одно незавершённое задание; остальные получают 429.
- Public endpoint сохраняет jury-схему `processing/done/failed`. `violation` эквивалентен непустому violations. Полностью неподдержанная наблюдаемость — `failed/insufficient_evidence`.
- Worker: concurrency=1, prefetch=1, CPU-пулы=2. Общий host flock, lease/fencing и уникальный result защищают от конкурентной/повторной доставки. Outbox восстанавливает даже утраченную Redis-публикацию.
- Бюджет 240 секунд начинается до multipart parse/decode. Worker получает оставшееся время. Preview строится в том же бюджете. SIGALRM ограничивает Python runner в prefork-процессе, Celery hard limit завершает зависший task; dispatcher/poll сохраняют просроченное состояние. Свежий DB clock проверяется после row lock и flush. Это software checks, не измеренный GPU SLA.
- Preview — silent H.264 MP4 с проверенной исходной временной шкалой; rotation применяется к пикселям. UI fetch с заголовком получает Blob ≤200 МиБ и должен освобождать Object URL. Source evidence — настоящий JPEG из исходного видео. Frame IDs имеют вид `v0f0` (индекс события/кадра в public violations).
- API выдаёт generic error envelope без ключей, путей и видео. Media имеет `private, no-store`; повреждение медиа не стирает job/result. Preview checksum позволяет переиспользовать готовый файл API и worker. Исходный SHA-256 проверяется перед выдачей original/preview.

## Проверки

Для полного набора задайте `FORTRESS_TEST_DATABASE_URL` на отдельный PostgreSQL с правом CREATE DATABASE. Тесты создают и удаляют только свои `fortress_test_a1_<uuid>` базы. Redis тесты сами запускают временный redis-server без TCP на закрытом Unix socket. Не указывайте пользовательскую или production БД/кластер.

Для **реального restart-теста** дополнительно нужны `FORTRESS_TEST_PG_CTL`, `FORTRESS_TEST_PGDATA`, `FORTRESS_TEST_PGLOG`, указывающие на выделенный тестовый кластер. При их отсутствии соответствующий тест явно skipped, это не pass. При использовании извлечённых пакетов задайте нужный `LD_LIBRARY_PATH`.

```sh
uv run --locked --group test python -m pytest tests/contracts tests/api -q
uv run --locked --group test python -m pytest tests/api/test_contract.py -q
uv run --locked --group test python -m pytest tests/api/test_recovery.py tests/api/test_deadlines.py -q
python3 docs/github-plan/validate_plan.py
```

Проверки включают настоящий localhost HTTP → FastAPI → PostgreSQL/outbox → Redis/Celery → result/media; остальные модульные harness проверяют decode limits, concurrent uploads, SIGKILL/restart prefork worker, broker outage, DB rollback, deadline и stale transaction. Это не внешний HTTPS, не браузерная приёмка и не ML validation.

`tests/api/fixture_runner.py` подключается только явным `TestComponents` в `Settings(profile='test')`; production запрещает это, CLI не запускает test profile. Даже test model endpoint честно сообщает `test_only=true`, `trained=false`, `validated=false`. Синтетические fixtures не являются пользовательскими видео, нормативными выводами или обученными весами.
