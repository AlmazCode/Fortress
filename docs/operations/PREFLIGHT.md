# O1 — инвентарь среды без установки и развёртывания

Рабочий процесс — Git/GitHub, без Aster. Запускать из Git-корня своего checkout, `rootPath=''`. Preflight сначала проверяет origin, доступность общей базы и её присутствие в HEAD; при несовпадении возвращает `repository_mismatch` и не запускает runtime/network probes.

## Команды

Windows, PowerShell 7:

```powershell
pwsh -NoProfile -File infra/scripts/preflight.ps1 -OutputPath ../preflight.local.json
pwsh -NoProfile -File infra/scripts/preflight.ps1 -Strict -OutputPath ../preflight.strict.local.json
pwsh -NoProfile -File infra/scripts/preflight.ps1 -NetworkOnly -OutputPath ../network.local.json
```

Ubuntu/WSL2, POSIX shell:

```sh
sh infra/scripts/preflight.sh --output ../preflight.local.json
sh infra/scripts/preflight.sh --strict --output ../preflight.strict.local.json
sh infra/scripts/network-check.sh --output ../network.local.json
```

Обе точки входа используют один Python recorder, встроенный в `preflight.sh`; PowerShell читает этот блок напрямую и не требует Bash/WSL. Recorder может работать на Python ≥3.9, но это не означает готовность требуемого Python 3.11 приложения. Shell проверяет работоспособность Python до выбора; `FORTRESS_PYTHON=/полный/путь/python` позволяет явно выбрать recorder. Windows App Execution Alias не принимается PowerShell-обёрткой за установленный Python.

Каждая команда ограничена `--timeout 8` / `-TimeoutSeconds 8` секунд; допустим диапазон 1–60. Отсутствие исполняемого файла — `missing`, ошибочный exit — `failed`, зависание — `timeout`; это разные исходы. Пробы не используют shell-интерполяцию, не скачивают образы/пакеты/веса и не запускают обучение.

Exit codes:

| Код | Значение |
| --- | --- |
| 0 | Отчёт собран; это не успешная готовность сервиса |
| 2 | Bootstrap не нашёл работающий Python либо `--strict` не получил доказанной service readiness |
| 3 | Не прошла привязка origin/root/base |

`service_ready=false` сохраняется намеренно: инвентарь не проверяет приложение, общие lock-файлы в рабочем runtime, модели, offline topology и восстановление. `toolchain_ready` требует Ubuntu/Linux, Python 3.11, работающий Linux Docker daemon + Compose v2 и FFmpeg/ffprobe. `gpu_ready` требует успешную пробу реального локального GPU-контейнера, а не только `nvidia-smi` на хосте. Запуск из Windows не объявляет выбранный WSL2 runtime готовым: повторите shell-команду внутри нужного Ubuntu/WSL2 окружения.

## Что измеряется

- Git origin/root/branch/base/HEAD и локальная ссылка origin/main. Preflight не выполняет fetch и не меняет ветку.
- ОС, release, CPU, физическая доступная RAM в байтах. На Windows используются read-only CIM-команды.
- Python 3.11: реальный запуск и числовая версия; на Windows дополнительно читается инвентарь Python launcher.
- FFmpeg и ffprobe: реальный `-version`.
- Docker CLI, JSON от `docker info`, Linux engine и Compose v2. Один `docker --version` недостаточен.
- GPU name/driver/VRAM MiB из `nvidia-smi`; driver CUDA ceiling отдельно от `nvcc`. Число CUDA в заголовке драйвера не доказывает установленный toolkit или совместимость PyTorch wheels.
- NVIDIA Container Toolkit CLI и отдельная фактическая container-проба, если она явно запрошена. Матрица совместимости приложения/драйвера/wheels остаётся отдельной проверкой с согласованными locks K.

Опциональная GPU-проба допустима только с заранее подготовленным доверенным локальным образом:

```sh
sh infra/scripts/preflight.sh --container-smoke --gpu-image LOCAL_IMAGE_REFERENCE
```

`LOCAL_IMAGE_REFERENCE` заменяется реальной проверенной ссылкой. Скрипт сначала делает `docker image inspect`, затем запускает только локальный image ID с `--pull never`, `--network none`, `--read-only`, `--cap-drop ALL`, без host mounts, с entrypoint `nvidia-smi`. Сам скрипт образ не получает. Образ и его runtime должны соответствовать совместимости K/O2; этот opt-in на текущем ПК **не запускался**, поскольку Docker отсутствует.

## Сеть и TLS

По умолчанию нет внешних запросов, определения публичного IP через сторонний сервис, порт-сканирования, изменения firewall или создания туннеля. Без предоставленного домена, сертификата и входящего маршрута отчёт сохраняет конкретный blocker и `external_access_verified=false`.

Владелец может указать разрешённый hostname и отдельно включить TLS-наблюдение:

```sh
sh infra/scripts/network-check.sh --external-url https://HOSTNAME --probe-external
# Дополнительная read-only оценка по фактически предоставленным адресам:
sh infra/scripts/network-check.sh --wan-ip ROUTER_WAN_IP --public-ip OBSERVED_PUBLIC_IP
```

Замените placeholders реальными данными. URL с credentials/query/fragment и HTTP отклоняются. TLS использует системный trust store и hostname verification, фиксирует сроки сертификата; проверка происходит с текущего хоста и не подтверждает внешний клиент → upload → status. Даже успешный TLS не устанавливает `external_access_verified=true`. O3 обязана получить отдельное наблюдение с внешнего клиента на tiny synthetic media; после I/B путь повторяется на реальном API.

`100.64.0.0/10`, private WAN или несовпадение WAN/public — признаки возможного upstream NAT; отсутствие этих признаков не доказывает доступность извне. Без реальных WAN/public данных CGNAT остаётся `unknown`, а не выдуманным подтверждённым диагнозом.

## Фактическая проверка этой реализации

17 октября 2026 года, checkout разработчика №4, Windows 11 Pro 10.0.26300:

- PowerShell entry point: exit 0, валидный JSON; strict: exit 2; Git Bash entry point: exit 0; shell network inventory: exit 0.
- Recorder Python 3.13.0; требуемый Python 3.11 не найден. WSL не установлен: `wsl --status` exit 50, `wsl --list --verbose` exit 1.
- Ryzen 7 7435HS; RAM `16989736960` байт (15.82 GiB); RTX 4060 Laptop, driver `595.79`, VRAM `8188` MiB. Это текущий ноутбук, а не подтверждение заявленных RTX 5060/Ryzen 5 целевого или training ПК.
- Docker/Compose, FFmpeg/ffprobe, nvcc, nvidia-ctk отсутствуют в PATH. GPU container, приложение и TLS upload/status — not_run.
- `python -m unittest discover -s tests/performance -p test_preflight_report.py -v` проверяет synthetic outcomes recorder; эти тесты не подтверждают реальное оборудование, ML или внешний HTTPS.

Полные машинные отчёты содержат локальные пути и хранятся вне Git. В репозиторий включается только обезличенный сводный инвентарь. После изменения среды прогон повторяется; старые результаты не считаются действующими доказательствами.

## Открытые первоисточники

Прочитаны при реализации 17 октября 2026 года:

- [Docker post-installation](https://docs.docker.com/engine/install/linux-postinstall/) — CLI и реальный Docker workload различаются; образ hello-world может скачиваться, поэтому recorder его автоматически не запускает.
- [NVIDIA sample workload](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html) — проверка toolkit через настоящий GPU-контейнер. Здесь добавлены запрет pull/egress и требование заранее подготовленного локального образа.
- [WSL basic commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands) — инвентарь status/distributions; наличие wsl.exe само по себе недостаточно.
- [RFC 6598](https://www.rfc-editor.org/rfc/rfc6598.html) — shared IPv4 space и пределы выводов о достижимости. Оценка признаков NAT в recorder — вывод по адресам, не измерение входящего пути.
