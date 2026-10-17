# Журнал разработчика №4 — Правила / Инфраструктура

Git/GitHub, без Aster. Своя ветка: `codex/dev4-rules-infra`. База инструкций: `c70a6d366c9b48b090368b92ca1bb60b692f6c26`, исходная база проекта: `46b7bc941e64fec5649242b8290607c8f7339819`.

| Task | State | Branch | Commit / PR | Проверки / блокер |
| --- | --- | --- | --- | --- |
| O1 | review | codex/dev4-rules-infra | См. Git-историю ветки | CLI и инвентарь проверены; outcome missingTool, service/gpu/external readiness=false |
| R1 | review | codex/dev4-rules-infra | См. Git-историю | C01–C15 сохранены; original case/jurisdiction/normative sources missing, legal unknown |
| R2 | review | codex/dev4-rules-infra | См. Git-историю | Память whole-video, late events, scene/job isolation проверены synthetic observations |
| R3 | review | codex/dev4-rules-infra | См. Git-историю | 5 технических шаблонов проверены; все production cases честно unknown/unsupported |
| R | review | codex/dev4-rules-infra | См. Git-историю | Код R1–R3 собран; нормативная/ML приёмка не пройдена |
| O2 | blocked | codex/dev4-rules-infra | См. Git-историю | Config/Dockerfiles/static tests готовы; реальный Compose/build/offline/volumes not_run без Docker; CPU lock не подтверждает CUDA |
| O3 | blocked | codex/dev4-rules-infra | См. Git-историю | Nginx/scripts/local synthetic harness проверены; нет trusted внешнего hostname/TLS/маршрута |
| O | blocked | codex/dev4-rules-infra | — | Требует O3 |
| B | blocked | codex/dev4-rules-infra | — | Требует интеграции I и реальных сервисов |

## O1: реально выполнено

17.10.2026: origin/rootPath/base/origin-main/HEAD ancestry проверены до исходников. Реализованы POSIX и PowerShell точки входа с одним recorder, структурированными missing/failed/timeout и Git guard до runtime/network действий. Без Python обе обёртки возвращают blocker JSON и exit 2.

- `python -m unittest discover -s tests/performance -p test_preflight_report.py -v` — exit 0, 15 тестов. Synthetic probes проверяют логику отчёта, не оборудование/ML.
- `pwsh -NoProfile -File infra/scripts/preflight.ps1 -OutputPath ../dev4-preflight-local.json -TimeoutSeconds 5` — exit 0, JSON collected, все readiness false.
- Та же команда с `-Strict` — ожидаемый exit 2.
- Git Bash `-n` для обоих shell scripts — exit 0; реальный shell preflight и network inventory — exit 0. Нерабочий MSYS Python3 не принимается за recorder; выбирается работающий Python.
- Факты хоста: Windows 11 Pro 10.0.26300; Ryzen 7 7435HS; RAM 16989736960 байт; RTX 4060 Laptop, driver 595.79, VRAM 8188 MiB. Python recorder 3.13.0. Это не целевой RTX 5060/Ryzen 5 и не другой training ПК.
- WSL не установлен, Python 3.11/Docker/Compose/FFmpeg/ffprobe/nvcc/nvidia-ctk не подтверждены. GPU container, compatibility, приложение, внешний HTTPS upload/status — not_run. Host nvidia-smi не считается CUDA/PyTorch/container readiness.
- Нет предоставленного hostname, сертификата, WAN/public данных и разрешённого incoming transport: CGNAT unknown, внешний обязательный критерий blocked. Не подключались туннели/облачная обработка и не использовались настоящие видео.

Критерии O1 1–5 покрыты Git guard, реальными command results, честным network inventory, missing-dependency tests и отсутствием train/deploy. Известные программные инструменты готовы к проверке, среда не объявлена готовой. Полные JSON с локальными путями сохранены вне Git. Подробности и первоисточники — docs/operations/PREFLIGHT.md и NETWORK_INVENTORY.md.

## K / R1–R3: собственные проверки

K `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f` интегрирован локальным merge `e35778400985f6c9fee9c5f98a3ac6d11b00e6e2`. `uv sync --locked --group test --python 3.11` выполнен в собственном окружении; CPython 3.11.17. Первая попытка managed install в стандартном uv каталоге не завершилась; повтор в отдельном dev4-python каталоге успешен. Общие pyproject/uv.lock не изменены.

`python -m pytest tests/contracts/test_schemas.py tests/rules tests/performance/test_preflight_report.py -q` в этом venv — exit 0, **88 passed, 29 subtests passed**, из них 55 tests контракта K. Pure template tests используют explicit synthetic RuleInputs, остальные — synthetic K observations. Это не валидация ML/реальной видимости.

Все C01–C15 имеют prerequisites/data/exceptions/limitations/tests. Источник только unverified нормализованная сводка предоставленного ТЗ с проверяемым hash, не оригинальный кейс и не норма. Все production findings unknown/unsupported, никакие нормативные названия, суммы/подделки/OS lock/полномочия не выдумываются. Полная неинформативность не даёт clean verdict; это должно сохраняться в pipeline I.

Session memory хранит историю ролика, дедуплицирует overlapping observations, сортирует поздние события той же сцены, разделяет scenes/jobs и не превращает score в actor ID. Absence требует явных достаточных metadata; источник и exceptions проверяются отдельно. Source frames создаёт pipeline, не rule pack.

Далее: O2 config + synthetic harness и O3 scripts. Docker/GPU runtime, volumes restart, worker egress и trusted внешний HTTPS остаются not_run/blocked до реальной среды и маршрута. Главный подтверждает интеграцию; запись не является independent/human approval.

## O2 / O3: подготовлено и проверено

Созданы Compose nginx/api/worker/redis/postgres, persistent named volumes, отдельная internal backend network, GPU reservation только worker, limits/concurrency/prefetch/threads. DB/Redis не имеют published ports; Nginx по умолчанию только 127.0.0.1:8443. Это static topology, реальная изоляция не доказана без запуска.

Образы закреплены реальными index digests из официального Docker Hub tag API; uv bootstrap — версия/hash Linux x86_64 wheel из PyPI. Python graph — исходный K lock, frontend — отдельный npm lock №2. K содержит CPU Torch wheels, поэтому production CUDA compatibility остаётся отдельным blocker до согласованного исправления №1/№3. Runtime не устанавливает пакеты/веса.

Для O3 подготовлены Nginx TLS proxy, bounded upload/timeouts, защищённые API/media proxy без direct media alias/access log; TLS/смoke scripts и отдельный explicit infra-only harness. Harness не импортирует модель/приложение, принимает только tiny synthetic marker и не выдаёт ML verdict. Local loopback HTTP tests реально проверяют 401 → upload 202 → synthetic status, wrong key, over-limit/неподдержанное тело, bound 128 records и явный запуск. Это не внешний HTTPS, Nginx/container или реальный API.

После последних изменений: `python -m pytest tests/performance tests/rules -q` в Python 3.11.17 — exit 0, **47 passed, 32 subtests passed**. Отдельно ранее 55 tests неизменённого K — exit 0. `bash -n` для shell scripts — exit 0; реальный tls-check без hostname — ожидаемый exit 2. Статические Compose тесты не объявляются `docker compose config`.

Оставшиеся обязательные проверки: Docker Compose config/build/start; настоящие GPU/CUDA/PyTorch checks; worker DB/Redis connectivity + egress; persistent volumes restart; доверенный внешний TLS upload/status; настоящий API/media путь после I; B fault/offline/capacity/deadline/benchmark после I. Сейчас они **not_run/blocked**, итог всего направления не объявлен готовым. Команды/ограничения/первичные источники — SETUP.md, NETWORK.md, PREFLIGHT.md; нормативные пробелы — SOURCES.md/CASE_SUPPORT.md.

Начатый по ошибочно указанному номеру frontend сохранён в отдельном dev2 worktree без дальнейших правок и не включён в результаты №4.
