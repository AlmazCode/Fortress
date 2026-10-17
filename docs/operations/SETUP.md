# Локальная инфраструктура: подготовка и границы проверки

Ветка №4 содержит конфигурацию и проверенные инструменты, а не выполненное развёртывание. На текущем Windows-хосте отдельно запущен официальный standalone Compose v5.6.0: production и test overlay проходят настоящий `config`, включая merge/reset. Docker engine/WSL отсутствуют; build, start, volumes restart, GPU и offline runtime checks **not_run**. Полное приложение строится и запускается после интеграции I. Проверка config и loopback HTTP/TLS не заменяют эти критерии.

Актуальное указание пользователя: **пока без виртуализации/WSL**. Установка системных компонентов отложена. Рабочие native Windows инструменты: frontend build, реальный HTTP/TLS client и process-resource sampler; [BENCHMARK.md](BENCHMARK.md). Native Linux путь без контейнеров — [RECOVERY.md](RECOVERY.md). Принятый POSIX worker не объявляется рабочим native Windows сервисом.

## Подготовка

1. На целевом Ubuntu/WSL2 ПК выполнить [preflight](PREFLIGHT.md). Нужны Docker/Compose ≥2.24.4, NVIDIA runtime, FFmpeg/ffprobe и совместимость Python/locks/GPU. Наличие nvidia-smi на Windows этого не доказывает.
2. Подготовить вне Git private env-файл по `infra/env.example`: новый сильный API-ключ, пароль PostgreSQL, URL-encoded PostgreSQL DSN с hostname `postgres`, абсолютный каталог TLS с `fullchain.pem` и `privkey.pem`. Не копировать секреты в frontend/VITE_*.
3. Для текущей программной проверки обученные веса не требуются: production без usable trained release должен отвечать `503 model_not_ready`. Подготовка локальных весов/совместимого release остаётся отдельным будущим этапом. Runtime ничего не скачивает. Текущий K `uv.lock` использует CPU Torch wheels; CUDA-worker **не считается готовым**, пока №1/№3 не согласуют и не проверят совместимый GPU lock. №4 этот общий lock сам не меняет.
4. Использовать принятый A `043eeb6d125f3b77d71b74de3b56c6a1cee91e70`: API — `python -m backend.app.main api --host 0.0.0.0 --port 8000`, worker — `python -m backend.app.main worker`, миграции — `python -m backend.app.main migrate`. Нет предположения об экспортах `:app`/`:celery_app`, переменные FORTRESS_API_APP/FORTRESS_WORKER_APP больше не нужны. Общая Settings из A требует FORTRESS_API_KEY, DATABASE_URL, REDIS_URL и абсолютный runtime root для каждого CLI mode: worker получает тот же private key через environment. Он не попадает в build args или логи. Release paths сами по себе не открывают readiness.

Примеры ниже используют путь `/PRIVATE/fortress.env` как placeholder. Заменить реальным абсолютным private env-файлом; не публиковать его. `config --quiet` не печатает подставленные secrets.

```sh
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml config --quiet
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml build
# Обязательный порядок: настоящие DB/Redis -> миграция -> API/worker/Nginx.
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml up -d --wait postgres redis
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml run --rm --no-deps api python -m backend.app.main migrate
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml up -d --wait
docker compose --env-file /PRIVATE/fortress.env -f infra/compose.yaml stop
```

Config фактически проверен отдельным Compose CLI с dummy values без подключения к daemon; остальные команды документируют подготовленный интерфейс и не выполнялись. Не запускать production image по одному наличию YAML. Отсутствующие backend/ML/frontend файлы должны прийти из принятых веток перед I.

## До I: только infrastructure harness

`compose.test.yaml` — явный overlay, переключающий api/worker/nginx на изолированные build targets `harness`, снимающий GPU reservation и устанавливающий `FORTRESS_INFRA_SMOKE=1`. Эти targets копируют только stdlib smoke_server.py и помеченную static страницу, не импортируют настоящий backend/ML/frontend. PostgreSQL/Redis остаются настоящими локальными контейнерами, но harness не проверяет durable job/outbox semantics.

Overlay явно заменяет обе команды: test targets запускают только `/opt/fortress-smoke.py`. Настоящий CLI test проверяет итоговые targets/commands и снятие GPU, а не только чтение YAML. API key/database password в отдельном harness env также должны быть случайными локальными значениями; открытый пример из tests не является deployment credential.

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

API healthcheck подтверждает TCP listener, не готовность модели. Worker production health проверяет живой PID 1 и команду `backend.app.main worker` через Linux `/proc/1/cmdline`; entrypoint exec-form, init wrapper не включён. NOSETPS=1 сохраняет этот argv при наличии optional setproctitle. Это local process liveness; DB/broker/model readiness отдельно не подтверждается. Backend A4 отключает remote control, поэтому `inspect ping` здесь неприменим. Принятый backend CLI сам задаёт prefork/concurrency=1; create_celery — prefetch=1, soft/hard limits 239/240s. Dispatcher передаёт уменьшенный остаток deadline. Health PostgreSQL/Redis и startup ordering не заменяют application/migration/release checks. Производственные inference/latency/память не измерены.

Ресурсные caps: worker 3 GiB, api 512 MiB, postgres 384 MiB, redis/nginx по 128 MiB; CPU worker 2, threads 2, concurrency/prefetch 1. Это настройки, не измеренное потребление всего сервиса или гарантия SLA. Host/Docker overhead и модель требуют отдельного benchmark.

## Зафиксированные источники образов

17.10.2026 фактически прочитаны официальные Docker Hub tag API и получены index digests; Dockerfiles/Compose закрепляют эти SHA-256:

- [Python 3.11 slim bookworm](https://hub.docker.com/v2/repositories/library/python/tags/3.11-slim-bookworm)
- [Node 22 bookworm slim](https://hub.docker.com/v2/repositories/library/node/tags/22-bookworm-slim)
- [Nginx stable alpine](https://hub.docker.com/v2/repositories/library/nginx/tags/stable-alpine)
- [Redis 7.4 bookworm](https://hub.docker.com/v2/repositories/library/redis/tags/7.4-bookworm)
- [PostgreSQL 17 bookworm](https://hub.docker.com/v2/repositories/library/postgres/tags/17-bookworm)

Получение digest не означает, что image скачан, собран или проверен на нужной архитектуре. OS FFmpeg определяется подписанным Debian snapshot `20261001T000000Z`; доступность snapshot/build не проверена. Python dependency graph берётся из общего uv.lock; uv bootstrap фиксирован версией 0.13.1 и SHA-256 Linux x86_64 wheel из фактически прочитанного [PyPI release JSON](https://pypi.org/pypi/uv/0.13.1/json). Эти Dockerfiles предназначены для согласованного x86_64 ПК; bootstrap на другой архитектуре fail-closed по hash. Frontend использует собственный package-lock №2; API-ключа в build args нет.

Для локальной проверки config скачан только [официальный Compose v5.6.0](https://github.com/docker/compose/releases/tag/v5.6.0), `docker-compose-windows-x86_64.exe`, SHA-256 `8aeaa0055e660e12cf07cd70680dc8333957fe6718528b91ec3da084eab62483`; hash сверён с digest asset в GitHub API до запуска. Файл хранится вне Git, системные программы/службы не менялись. `FORTRESS_COMPOSE_CLI=/absolute/path/docker-compose.exe python -m pytest tests/performance/test_compose_isolation.py -q` включает настоящие config tests; без переменной они явно skipped. Это не установка Docker engine.

## Подготовка Windows-хоста: наблюдённый blocker

17.10.2026 с разрешения пользователя подготовлен официальный Docker Desktop 4.95.0 (build 242831). Winget source сообщил [installer URL](https://desktop.docker.com/win/main/amd64/242831/Docker%20Desktop%20Installer.exe) и SHA-256 `73431db38491f770543880366228a23c993f84d1e8e045f56d83b8a98940cf76`; скачанный файл совпал по hash, Authenticode status Valid, publisher Docker Inc. Installer и логи находятся только в закрытой локальной tooling-папке, не Git.

Реальный запуск `install --user --quiet --accept-license --backend=wsl-2 --no-windows-containers` завершился **exit 1**, Docker не установлен. Его prerequisite check сообщил: `VirtualMachinePlatform` выключен; per-user installer не может включить системный компонент без administrator privileges. Сам Codex запущен без этих прав. `wsl --status` вернул exit 50.

Следующий системный шаг выполняет пользователь в PowerShell **от администратора**:

```powershell
wsl --install --no-distribution
```

Этот системный шаг **отложен пользователем**, сейчас не выполняется. Если позднее будет выбран WSL-хост: после требуемой Windows перезагрузки повторить проверенный per-user installer, запустить Docker Desktop и проверить `wsl --version`, `docker version`, `docker compose version`, затем preflight. Готовность engine/GPU остаётся false до реального успешного запуска. Официальные основания: [Docker Windows install / per-user prerequisites](https://docs.docker.com/desktop/setup/install/windows-install/), [Microsoft WSL install](https://learn.microsoft.com/en-us/windows/wsl/install).

Для Linux checkout сохранять LF shell scripts; при новом Windows clone использовать repository-local настройку line endings. Внеплановый `infra/.gitattributes` удалён по замечанию review; общие Git settings и чужие checkout не менялись.

## Проверка frontend build inputs без Docker

Frontend импортирует общие contracts из относительного пути `../../../contracts/*.json`. Build stage теперь копирует contracts в `/contracts` рядом с `/frontend`. До этого TS2307 воспроизведён интегратором; после исправления №4 воспроизвёл точный COPY layout в отдельной новой локальной папке, выполнил `npm ci --ignore-scripts --no-audit --no-fund` и `npm run build`: **exit 0**, typecheck и Vite production build прошли, 173 modules. Node 22.22.2. Frontend/src/lock №2 не изменены. Это настоящая проверка inputs/build на native Windows, не `docker build` и не проверка Nginx runtime.
