# Fortress: инструкция по запуску для релиза

Состояние на 18 октября 2026: код инфраструктуры интегрирован, WSL и Docker Desktop на Windows установлены; фактические container build/start, offline worker, volumes/restart, GPU/CUDA и внешний HTTPS ещё **не подтверждены**. Windows запросила перезагрузку для активации включённых компонентов. Это инструкция, не отчёт об успешном запуске контейнеров.

**Windows может быть хостом Docker Desktop с WSL2; серверные контейнеры остаются Linux.** Пользователь разрешил этот вариант 18 октября, прежний запрет на WSL снят. Браузер работает на Windows. Автоматическая перезагрузка не разрешалась и не выполнялась; native Windows backend/worker этим не подтверждаются. Ниже сохранён также путь для native Linux.

## Windows: продолжение после перезагрузки

На текущем ПК уже включены VirtualMachinePlatform/WSL (NoRestart), установлены Microsoft WSL 3.0.3 и Docker Desktop 4.95.0 с WSL2 backend — installer exits 0. BIOS virtualization включена. Первый engine probe вернул exit 1: Docker backend видит Virtual Machine Platform not enabled до активации после reboot. Сначала сохранить работу и выполнить обычную перезагрузку Windows; повторная установка не заменяет её.

После входа запустить Docker Desktop и проверить в PowerShell:

```powershell
$FortressDocker = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$FortressDesktop = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'
Start-Process -FilePath $FortressDesktop -WindowStyle Hidden
wsl --version
& $FortressDocker version
if ($LASTEXITCODE -ne 0) { throw 'Docker engine is not ready; check Docker Desktop/WSL before continuing.' }
& $FortressDocker info --format '{{.OSType}}'
& $FortressDocker compose version
```

Дождаться готовности Desktop: нужен настоящий Server response и тип `linux`. По [Docker GPU guide](https://docs.docker.com/desktop/features/gpu/) проверить CUDA на официальном отдельном sample image; это короткое вычисление, не обучение:

```powershell
$GpuImage = 'nvcr.io/nvidia/k8s/cuda-sample:nbody'
& $FortressDocker pull $GpuImage
if ($LASTEXITCODE -ne 0) { throw 'GPU sample image preparation failed.' }
$GpuDigest = (& $FortressDocker image inspect $GpuImage --format '{{index .RepoDigests 0}}').Trim()
if ($LASTEXITCODE -ne 0 -or -not $GpuDigest) { throw 'GPU sample digest was not verified.' }
& $FortressDocker run --rm --pull never --network none --gpus all $GpuDigest nbody -gpu -benchmark -numbodies=1024
if ($LASTEXITCODE -ne 0) { throw 'Container CUDA check failed.' }
```

Сохранить digest/output/exit code. Windows driver уже видит RTX 4060 Laptop; не устанавливать Linux NVIDIA display driver внутри WSL. Host CUDA Toolkit не требуется для исполнения готового CUDA container. Успех sample не закрывает GPU-worker Fortress: shared lock пока CPU Torch и требует согласованного GPU решения №1/№3.

Для отдельного infrastructure harness из корня checkout те же Compose files можно использовать напрямую из PowerShell, без установки отдельного Ubuntu distro. Подготовить private env/TLS по SETUP; заменить путь ниже. Для текущего запуска закрытые env/key/local TLS уже подготовлены вне Git, точный путь хранится в локальном checkpoint.

```powershell
$CheckEnv = 'C:\PRIVATE\fortress.env'
$CheckProject = 'fortress-infra-check'
$ComposeArgs = @('compose', '-p', $CheckProject, '--env-file', $CheckEnv, '-f', 'infra/compose.yaml', '-f', 'infra/compose.test.yaml')
& $FortressDocker @ComposeArgs config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed.' }
& $FortressDocker @ComposeArgs build
if ($LASTEXITCODE -ne 0) { throw 'Harness image build failed.' }
& $FortressDocker @ComposeArgs up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Harness startup failed.' }
& $FortressDocker @ComposeArgs exec -T worker python /opt/fortress-smoke.py probe-worker
if ($LASTEXITCODE -ne 0) { throw 'Worker local connectivity/egress probe failed.' }
# Остановка сохраняет volumes:
& $FortressDocker @ComposeArgs stop
```

Это CPU infrastructure overlay с настоящими PostgreSQL/Redis, не production app/ML или B. GPU проверяется отдельно sample выше. Полную production сборку/запуск и synthetic API profile выполнять после принятого I.

Согласован бесплатный внешний DNS `sslip.io` и сертификат Let's Encrypt; hostname подготовлен в закрытом локальном файле, DNS совпадает с наблюдаемым публичным IP. Это ещё не маршрут: UPnP недоступен, проверенные local admin ports роутера не отвечают; port forwarding/firewall не менялись, CGNAT не установлен/не исключён, публичный сертификат не выпущен. Прежде чем публиковать Nginx, подтвердить WAN/router route и выполнить раздел 7. Публичный IP/hostname и ключи в Git не добавлять.

## 1. Что подготовить на Linux

- Доступ к работающему Docker engine и Compose >=2.24.4, Git, Python 3.11, OpenSSL; для реального API/видео — FFmpeg/ffprobe и shared Python lock.
- Для GPU: NVIDIA driver и Container Toolkit. **Текущий общий lock использует CPU Torch.** До согласованного CUDA lock от №1/№3 GPU-проверка не может считаться пройденной. Не заменять dependencies локально в обход общего lock.
- Для внешнего доступа: разрешённый входящий маршрут к Nginx, настоящий hostname/DNS и соответствующий сертификат доверенного CA. Сам hostname в env или локальный сертификат маршрут не создаёт.

На Linux, под тем же пользователем, который будет запускать Compose:

```bash
set -euo pipefail
docker version
docker info --format '{{.OSType}}'
docker compose version
nvidia-smi
```

Нужен ответ **Server** у `docker version`, тип `linux` и успешный доступ к engine. Permission denied / socket missing — остановиться и исправить доступ вместе с владельцем компьютера. Наличие Compose без engine недостаточно. На NVIDIA-хосте успешный `nvidia-smi` подтверждает только host driver; контейнерная проверка ниже отдельная.

### Если Docker отвечает permission denied

В журнале №1 это ошибка **его Linux-хоста**, `/var/run/docker.sock`; текущий Windows №4 сообщает отсутствие engine pipe. Это разные причины. На Linux сначала собрать факты:

```bash
id
docker context show
docker context inspect --format '{{.Endpoints.docker.Host}}'
if test -S /var/run/docker.sock; then
  stat -Lc '%A %U %G %n' /var/run/docker.sock
fi
docker version
```

Для обычного rootful daemon с socket `root:docker` и существующей группой `docker` администратор добавляет **оператора этого хоста**:

```bash
sudo usermod -aG docker "$(id -un)"
```

Команду выполнять из сессии самого оператора. Затем полностью выйти из SSH/login и войти снова; локальный Codex также должен получить новую login-сессию. Перезагрузка Windows не нужна. Проверить `id -nG`, затем `docker version`/`docker info`. Группа даёт административные возможности на хосте — [официальная процедура Docker](https://docs.docker.com/engine/install/linux-postinstall/).

Если выбран существующий [rootless daemon](https://docs.docker.com/engine/security/rootless/), проверить его реальный context/endpoint, а не добавлять права на чужой rootful socket. Если права/группы уже корректны, проверить ACL и ограничения среды выполнения. Не менять socket на `chmod 666` и не открывать незащищённый TCP API. Исправление применимо только на доступном Linux-хосте; здесь оно **не выполнено**.

## 2. Получить точный код

Клонировать в новую папку. `RELEASE_SHA` заменить полным SHA выпуска; его сообщает главный. Проверенная точка интеграции — `469b2eb841de187d8e3429dc17514254777d3bdc`, **I ещё не принят**. Для первого инфраструктурного прогона можно закрепить эту точку; для приложения нужен последующий принятый I.

```bash
git clone https://github.com/AlmazCode/Fortress.git fortress-release
cd fortress-release
git fetch origin
RELEASE_SHA=469b2eb841de187d8e3429dc17514254777d3bdc
git checkout --detach "$RELEASE_SHA"
git rev-parse HEAD
```

Дальнейшие Bash-команды выполнять из корня этого checkout в одной сессии. Пакеты и образы скачиваются на этапе подготовки/build; анализ и offline worker не должны скачивать зависимости/веса.

## 3. Отдельный стенд и закрытые настройки

Первый прогон создаёт **новый** Compose project и свои volumes; он не использует данные рабочего сервиса. Сохранить значения `CHECK_PROJECT` и `PRIVATE_DIR` для повторного входа/остановки. Порт 8443 должен быть свободен.

```bash
umask 077
CHECK_PROJECT="fortress-check-$(date -u +%Y%m%d%H%M%S)"
PRIVATE_DIR="$(mktemp -d "$HOME/fortress-check.XXXXXXXX")"
export CHECK_PROJECT PRIVATE_DIR
mkdir "$PRIVATE_DIR/tls"
python3.11 - <<'PY'
import os, secrets
from pathlib import Path
root = Path(os.environ['PRIVATE_DIR'])
key, password = secrets.token_hex(32), secrets.token_hex(32)
with (root / 'operator-key.txt').open('x') as out:
    out.write(key + '\n')
with (root / 'fortress.env').open('x') as out:
    out.write(f'FORTRESS_API_KEY={key}\nPOSTGRES_PASSWORD={password}\n'
              f'DATABASE_URL=postgresql+psycopg://fortress:{password}@postgres:5432/fortress\n'
              f'FORTRESS_TLS_DIR={root / "tls"}\n'
              'FORTRESS_BIND_IP=127.0.0.1\nFORTRESS_HTTPS_PORT=8443\n')
PY
```

В private env/ключах нет публичных example credentials. Эти файлы, сертификатные ключи, видео и веса в Git не добавлять. `config --quiet` проверяет настройки без печати подставленных secrets.

Для **локального** инфраструктурного smoke создать одноразовый сертификат:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 2 \
  -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' \
  -keyout "$PRIVATE_DIR/tls/privkey.pem" \
  -out "$PRIVATE_DIR/tls/fullchain.pem"
```

Это private CA/loopback, **не доверенный внешний HTTPS**. Для внешнего прогона нужен отдельный private каталог с настоящими `fullchain.pem`/`privkey.pem`, читаемыми Nginx, и соответствующий `FORTRESS_TLS_DIR`.

## 4. До I: собрать и запустить инфраструктурный стенд

```bash
dc() {
  docker compose -p "$CHECK_PROJECT" --env-file "$PRIVATE_DIR/fortress.env" \
    -f infra/compose.yaml -f infra/compose.test.yaml "$@"
}
dc config --quiet
dc build
dc up -d --wait
dc ps
dc exec -T worker python /opt/fortress-smoke.py probe-worker
docker network inspect "${CHECK_PROJECT}_backend" --format '{{.Internal}}'
docker inspect "$(dc ps -q worker)" --format '{{json .NetworkSettings.Networks}}'
sh infra/scripts/network-smoke.sh --url https://localhost:8443 \
  --key-file "$PRIVATE_DIR/operator-key.txt" \
  --ca-file "$PRIVATE_DIR/tls/fullchain.pem"
```

Ожидается: build/start exit 0; worker видит TCP PostgreSQL/Redis, обе исходящие TCP-пробы заблокированы; backend network `Internal=true`, worker присоединён только к ней. HTTP smoke: 401 без ключа, tiny synthetic upload 202, status 200. Любая ошибка — остановить текущий этап, сохранить exit code и причину. Отказ двух адресов/портов не доказывает блокировку всех протоколов: отдельно сверить network attachments и политику хоста.

Overlay запускает настоящий PostgreSQL/Redis и **явный infrastructure harness**, снимает GPU reservation. Он не запускает Celery/ML, его jobs в памяти API, поэтому их исчезновение при restart ожидаемо. Успех не закрывает full-stack I/B или CUDA.

## 5. Проверить volumes после restart

Только для нового стенда из раздела 3: создать свои markers в PostgreSQL/Redis/media/models. Не выполнять создание таблицы/файлов на пользовательском runtime. У API/worker models остаётся read-only; одноразовый helper записывает только отдельный synthetic marker нового test volume.

```bash
dc exec -T postgres psql -U fortress -d fortress -v ON_ERROR_STOP=1 -c \
  "CREATE TABLE infra_persistence_probe (value text NOT NULL); INSERT INTO infra_persistence_probe VALUES ('preserved');"
test "$(dc exec -T redis redis-cli --raw SET fortress:infra-persistence-probe preserved NX)" = OK
CHECK_IMAGE="$(dc images -q worker)"
docker run --rm --network none \
  --mount "type=volume,src=${CHECK_PROJECT}_media,dst=/probe-media" \
  --mount "type=volume,src=${CHECK_PROJECT}_models,dst=/probe-models" \
  --entrypoint python "$CHECK_IMAGE" -c \
  'from pathlib import Path; [p.open("xb").write(b"fortress-synthetic-volume-probe\n") for p in (Path("/probe-media/.infra-persistence-probe"), Path("/probe-models/.infra-persistence-probe"))]'
dc restart
dc up -d --wait
test "$(dc exec -T postgres psql -U fortress -d fortress -At -v ON_ERROR_STOP=1 -c 'SELECT value FROM infra_persistence_probe')" = preserved
test "$(dc exec -T redis redis-cli --raw GET fortress:infra-persistence-probe)" = preserved
docker run --rm --network none \
  --mount "type=volume,src=${CHECK_PROJECT}_media,dst=/probe-media,readonly" \
  --mount "type=volume,src=${CHECK_PROJECT}_models,dst=/probe-models,readonly" \
  --entrypoint python "$CHECK_IMAGE" -c \
  'from pathlib import Path; import hashlib; paths=(Path("/probe-media/.infra-persistence-probe"),Path("/probe-models/.infra-persistence-probe")); expected=hashlib.sha256(b"fortress-synthetic-volume-probe\n").hexdigest(); assert all(hashlib.sha256(p.read_bytes()).hexdigest()==expected for p in paths); print("media/models hashes preserved")'
dc exec -T worker python /opt/fortress-smoke.py probe-worker
```

Каждое сравнение должно вернуть exit 0. Это проверка сохранности отдельных synthetic markers, **не recovery jobs/outbox/fencing**. Реальные принятые jobs/results/media/release SHA и crash recovery проверяются в B после I; порядок — [RECOVERY.md](RECOVERY.md).

## 6. Настоящее приложение и GPU — после принятого I

Получить у главного точный принятый I SHA и согласованный GPU lock, обновить отдельный checkout на этот SHA. Остановить harness: `dc stop`. Использовать **другой** Compose project и отдельный private env/volumes/доверенный TLS; не смешивать synthetic harness и рабочие данные. `APP_PROJECT`/`APP_ENV` ниже заменить своими значениями. Уберите test overlay.

```bash
APP_PROJECT=fortress-app
APP_ENV=/PRIVATE/fortress-app.env
pc() {
  docker compose -p "$APP_PROJECT" --env-file "$APP_ENV" -f infra/compose.yaml "$@"
}
pc config --quiet
pc build
pc up -d --wait postgres redis
pc run --rm --no-deps api python -m backend.app.main migrate
pc run --rm --no-deps worker python -c \
  'import torch; assert torch.version.cuda is not None and torch.cuda.is_available(), "CUDA unavailable"; x=torch.ones((32,32),device="cuda"); y=x@x; torch.cuda.synchronize(); assert y[0,0].item()==32; print(torch.__version__,torch.version.cuda,torch.cuda.get_device_name(0))'
pc up -d --wait
pc ps
```

CUDA-команда должна реально выполниться в worker image с GPU reservation. На текущем CPU lock она не должна считаться успешной; наличие GPU, container start или `nvidia-smi` без CUDA tensor operation недостаточно. Обучение эта проверка не запускает.

Для настоящего worker отдельно проверить SQL/Redis и исходящие подключения:

```bash
pc exec -T worker python - <<'PY'
import json, os, socket
from sqlalchemy import create_engine, text
from redis import Redis
engine = create_engine(os.environ['DATABASE_URL'], connect_args={'connect_timeout': 3})
with engine.connect() as conn:
    assert conn.execute(text('SELECT 1')).scalar_one() == 1
assert Redis.from_url(os.environ['REDIS_URL'], socket_connect_timeout=3, socket_timeout=3).ping()
blocked = []
for host in ('1.1.1.1', '8.8.8.8'):
    try:
        with socket.create_connection((host, 443), timeout=3):
            blocked.append(False)
    except OSError:
        blocked.append(True)
assert all(blocked), 'Worker has outbound TCP access'
print(json.dumps({'postgres_select_1': True, 'redis_ping': True, 'tested_tcp_egress_blocked': blocked}))
PY
```

Также сверить `docker network inspect "${APP_PROJECT}_backend"` и список сетей worker: только internal backend. PostgreSQL/Redis не должны иметь published ports. Не подключать worker к edge для обхода ошибки.

## 7. Внешний HTTPS и upload/status

Отсутствующий URL/hostname — состояние **не настроено**, а не наблюдённая ошибка сертификата. В текущем отчёте внешняя TLS-проверка не запускалась. `127.0.0.1:8443` в env предназначен только для локального доступа.

Владелец сети подготавливает DNS/маршрут/firewall к Nginx и настоящий доверенный сертификат; это не выполняется автоматически данным файлом. Для нужного стенда задать в его private env разрешённый `FORTRESS_BIND_IP`, порт и `FORTRESS_TLS_DIR`, затем повторить `up -d --wait`. Снаружи публикуется только Nginx. Не использовать произвольный облачный туннель.

Порядок исправления на разрешённом хосте:

1. Получить настоящий hostname под контролем владельца, проверить A/AAAA и маршрут клиента к серверу. Настроить разрешённый входящий TCP 443 до HTTPS-порта Nginx; при NAT сверить port forwarding. Наличие CGNAT сначала установить, а не предполагать по отсутствию URL.
2. Выдать сертификат для этого hostname. Для существующего домена возможен ACME DNS-01: подтверждается TXT-запись, входящий port 80 для выдачи не нужен. HTTP-01 требует port 80, который текущий Compose не публикует; его нельзя считать настроенным. DNS-01 **не создаёт** входящий маршрут к сервису. Основание — [Let's Encrypt challenge types](https://letsencrypt.org/docs/challenge-types/).
3. Установить full chain и соответствующий private key в private TLS directory. Проверить hostname/SAN, срок, совпадение публичных ключей и читаемость файлов Nginx. Затем выполнить `nginx -t` в нужном работающем стенде (`dc exec -T nginx nginx -t` или `pc exec -T nginx nginx -t`).
4. Проверить TLS и upload/status с независимого внешнего клиента командами ниже. Автоматическое продление сертификата согласовать с владельцем DNS и повторной проверкой Nginx перед reload.

Для проверки пары сертификат/ключ, подставив реальный private каталог:

```bash
TLS_DIR=/PRIVATE/tls
openssl x509 -in "$TLS_DIR/fullchain.pem" -noout -dates -ext subjectAltName
openssl x509 -in "$TLS_DIR/fullchain.pem" -pubkey -noout \
  | openssl pkey -pubin -outform DER | openssl dgst -sha256
openssl pkey -in "$TLS_DIR/privkey.pem" -pubout -outform DER \
  | openssl dgst -sha256
```

Два SHA-256 должны совпасть; здесь выводится hash публичного ключа, не содержимое private key. Это не проверка доверенной цепочки извне.

| Наблюдение внешнего клиента | Что исправлять |
| --- | --- |
| DNS name не разрешается | A/AAAA и фактический hostname |
| Timeout / connection refused | Bind IP, listening port, firewall, NAT/маршрут |
| Certificate verify / hostname / expiry error | Full chain, SAN имени, срок и соответствие ключа |
| TLS проходит, HTTP 502/503 proxy failure | API container/health/upstream, не отключать TLS |
| Production `503 model_not_ready` по контракту | Ожидаемый отказ без trained release; не ошибка HTTPS |

На клиенте **вне сети сервиса**, с настоящим hostname, выполнить:

```bash
PUBLIC_URL=https://HOSTNAME
sh infra/scripts/tls-check.sh --external-url "$PUBLIC_URL"
# Только для явно запущенного infrastructure harness, до I:
sh infra/scripts/network-smoke.sh --url "$PUBLIC_URL" --key-file /PRIVATE/operator-key.txt
```

Ожидаются доверенная цепочка, корректные hostname/expiry и 401 -> 202 -> 200. Здесь не передавать `--ca-file` локального сертификата и не отключать TLS verification. Сохранить точные client/service SHA, расположение независимого клиента, UTC, команды и exit codes. Поле `external_access_verified=false` у клиента само по себе не меняется на true: главный принимает внешний путь по реальному внешнему наблюдению и проверенному маршруту.

После I — настоящий API. При отсутствии обученного release проверить ожидаемый production `503 model_not_ready`:

```bash
python3.11 tests/performance/benchmark.py --url "$PUBLIC_URL" \
  --key-file /PRIVATE/operator-key.txt --output /PRIVATE/production-gate.json \
  --mode production-gate --service-commit FULL_I_SHA
```

Этот probe проверяет отказ до обработки; он **не выполняет успешный upload/status анализ**. Для него главный в I предоставляет фактическую команду запуска отдельного synthetic test profile. На этом профиле с известным synthetic MP4/MOV:

```bash
python3.11 tests/performance/benchmark.py --url "$PUBLIC_URL" \
  --key-file /PRIVATE/operator-key.txt --output /PRIVATE/synthetic-external.json \
  --mode synthetic-analysis --video /PRIVATE/synthetic.mp4 --service-commit FULL_I_SHA
```

Нужны readiness `test_only=true`, synthetic provenance, auth, upload 202, terminal status, original SHA и preview/evidence checks. До принятого I нет готового CLI для такого bootstrap: не придумывать `--test` или test env. На production этот режим не запускать. Подготовить клиент Python 3.11 с shared deps (`uv sync --locked`) заранее; на Windows можно выполнить ту же команду через `.venv/Scripts/python.exe`, а интерфейс открыть в обычном браузере. Подробнее — [BENCHMARK.md](BENCHMARK.md).

## 8. Остановка, повторный старт и запись результата

`dc stop` останавливает test stack, `dc up -d --wait` возвращает его с теми же project/env/volumes. Для приложения аналогично `pc stop` / `pc up -d --wait`. После нового входа в shell восстановить значения переменных и определения функций из инструкции. Не выполнять `down -v`, prune или удаление пользовательских volumes. Перед обновлением рабочего сервиса нужен проверенный backup/restore по [RECOVERY.md](RECOVERY.md).

В [ACCEPTANCE.json](ACCEPTANCE.json) и журнал №4 внести **наблюдённые** SHA, image IDs, команды/exit codes, сеть worker, DB/Redis, hashes markers до/после restart, GPU/CUDA output и внешний smoke. Secrets/private media не публиковать. Пока этих результатов нет: O2/O3/O blocked, B ждёт принятого I. Software acceptance R не подтверждает нормативные источники: они остаются unknown/unsupported.

## Текст для описания будущего GitHub Release

> Запуск сервера: Linux x86_64 с доступным Docker engine; клиент — браузер на Windows. Пошаговая инструкция: `docs/operations/RELEASE.md`. До использования проверить отмеченные runtime/GPU/HTTPS условия и актуальный `docs/operations/ACCEPTANCE.json`. Без обученного release ожидается `503 model_not_ready`. Приведённые команды не являются результатами выполненной приёмки.

При публикации главный указывает точный release/I SHA, прикладывает эту инструкцию и актуальные фактические результаты. Наличие инструкции не означает, что выпуск принят или внешний сервис уже доступен.
