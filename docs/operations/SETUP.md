# Локальная инфраструктура: подготовка и границы проверки

Ветка №4 содержит конфигурацию, а не выполненное развёртывание. Docker/WSL на текущем хосте отсутствуют; `docker compose config`, build, start, volumes restart, GPU и offline runtime checks **not_run**. Полное приложение строится и запускается после интеграции I. Статические тесты YAML и HTTP harness не заменяют эти критерии.

## Подготовка

1. На целевом Ubuntu/WSL2 ПК выполнить [preflight](PREFLIGHT.md). Нужны Docker/Compose ≥2.24.4, NVIDIA runtime, FFmpeg/ffprobe и совместимость Python/locks/GPU. Наличие nvidia-smi на Windows этого не доказывает.
2. Подготовить вне Git private env-файл по `infra/env.example`: новый сильный API-ключ, пароль PostgreSQL, URL-encoded PostgreSQL DSN с hostname `postgres`, абсолютный каталог TLS с `fullchain.pem` и `privkey.pem`. Не копировать секреты в frontend/VITE_*.
3. Подготовить локальные веса и совместимый trained release отдельно. Runtime ничего не скачивает. Текущий K `uv.lock` использует CPU Torch wheels; CUDA-worker **не считается готовым**, пока №1/№3 не согласуют и не проверят совместимый GPU lock. №4 этот общий lock сам не меняет.
4. После I сверить реальные entry points: `backend.app.main:app` и `backend.app.celery_app:celery_app`, environment `FORTRESS_API_KEY`, DATABASE_URL, REDIS_URL, пути media/release. Сейчас wiring подготовлен по карте файлов K; полный runtime не проверен.

Примеры ниже используют путь `/PRIVATE/fortress.env` как placeholder. Заменить реальным абсолютным private env-файлом; не публиковать его. `config --quiet` не печатает подставленные secrets.

```sh
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml config --quiet
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml build
# После проверенной интеграции и готовности миграций backend:
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml run --rm api alembic -c backend/alembic.ini upgrade head
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml up -d --wait
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml stop
```

Эти команды документируют подготовленный интерфейс; на текущем хосте они не выполнялись. Не запускать production image по одному наличию YAML. Отсутствующие backend/ML/frontend файлы должны прийти из принятых веток перед I.

## До I: только infrastructure harness

`compose.test.yaml` — явный overlay, переключающий api/worker/nginx на изолированные build targets `harness`, снимающий GPU reservation и устанавливающий `FORTRESS_INFRA_SMOKE=1`. Эти targets копируют только stdlib smoke_server.py и помеченную static страницу, не импортируют настоящий backend/ML/frontend. PostgreSQL/Redis остаются настоящими локальными контейнерами, но harness не проверяет durable job/outbox semantics.

```sh
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml -f infra/compose.test.yaml config --quiet
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml -f infra/compose.test.yaml build
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml -f infra/compose.test.yaml up -d --wait
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml -f infra/compose.test.yaml exec worker python /opt/fortress-smoke.py probe-worker
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml -f infra/compose.test.yaml stop
```

Эти container commands также not_run. В probe проверяются только TCP-доступность postgres/redis и отказ двух исходящих TCP-проб; это конкретные наблюдения, не доказательство блокировки всех возможных протоколов. Не подключать worker к edge ради прохождения теста.

## Volumes и health

Named volumes `media/models/postgres/redis` постоянны. Приложение и worker используют UID 10001; image готовит начальные каталоги media/models с нужным владельцем. `models` в runtime read-only. Docker не меняет права уже существующего пользовательского volume: их подготовка проверяется отдельно владельцем, без рекурсивной перезаписи чужих данных.

Остановка/повторный up не должна стирать volumes. Не применять `down -v`, prune или удаление данных ради теста. Перед обновлением сделать согласованный backup: `pg_dump` согласованной PostgreSQL БД и копию media/models/Redis AOF в закрытое локальное хранилище, с проверкой восстановления. Конкретный recovery/fencing/outbox прогон принадлежит B после I; сейчас persistence/restart не проверены.

API healthcheck подтверждает TCP listener, не готовность модели. Worker production health подтверждает Celery ping, не ML readiness. Health PostgreSQL/Redis и startup ordering не заменяют application/migration/release checks. Производственные inference/latency/память не измерены.

Ресурсные caps: worker 3 GiB, api 512 MiB, postgres 384 MiB, redis/nginx по 128 MiB; CPU worker 2, threads 2, concurrency/prefetch 1. Это настройки, не измеренное потребление всего сервиса или гарантия SLA. Host/Docker overhead и модель требуют отдельного benchmark.

## Зафиксированные источники образов

17.10.2026 фактически прочитаны официальные Docker Hub tag API и получены index digests; Dockerfiles/Compose закрепляют эти SHA-256:

- [Python 3.11 slim bookworm](https://hub.docker.com/v2/repositories/library/python/tags/3.11-slim-bookworm)
- [Node 22 bookworm slim](https://hub.docker.com/v2/repositories/library/node/tags/22-bookworm-slim)
- [Nginx stable alpine](https://hub.docker.com/v2/repositories/library/nginx/tags/stable-alpine)
- [Redis 7.4 bookworm](https://hub.docker.com/v2/repositories/library/redis/tags/7.4-bookworm)
- [PostgreSQL 17 bookworm](https://hub.docker.com/v2/repositories/library/postgres/tags/17-bookworm)

Получение digest не означает, что image скачан, собран или проверен на нужной архитектуре. OS FFmpeg определяется подписанным Debian snapshot `20261001T000000Z`; доступность snapshot/build не проверена. Python dependency graph берётся из общего uv.lock; uv bootstrap фиксирован версией 0.13.1 и SHA-256 Linux x86_64 wheel из фактически прочитанного [PyPI release JSON](https://pypi.org/pypi/uv/0.13.1/json). Эти Dockerfiles предназначены для согласованного x86_64 ПК; bootstrap на другой архитектуре fail-closed по hash. Frontend использует собственный package-lock №2; API-ключа в build args нет.
