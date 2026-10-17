# Журнал разработчика №4 — Правила / Инфраструктура

Git/GitHub, без Aster. Своя ветка: `codex/dev4-rules-infra`. База инструкций: `c70a6d366c9b48b090368b92ca1bb60b692f6c26`, исходная база проекта: `46b7bc941e64fec5649242b8290607c8f7339819`.

| Task | State | Branch | Commit / PR | Проверки / блокер |
| --- | --- | --- | --- | --- |
| O1 | review | codex/dev4-rules-infra | См. Git-историю ветки | CLI и инвентарь проверены; outcome missingTool, service/gpu/external readiness=false |
| R1 | blocked | codex/dev4-rules-infra | — | Опубликован кандидат K 2e44bf5; проверка точного commit ещё не завершена |
| R2 | blocked | codex/dev4-rules-infra | — | Требует проверенного K |
| R3 | blocked | codex/dev4-rules-infra | — | Требует R1/R2 |
| R | blocked | codex/dev4-rules-infra | — | Требует R3 |
| O2 | blocked | codex/dev4-rules-infra | — | Требует проверенного K; Docker runtime сейчас отсутствует |
| O3 | blocked | codex/dev4-rules-infra | — | Требует O1/O2 и разрешённого внешнего hostname/TLS/маршрута |
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

Далее: проверить опубликованный commit K собственными schema tests, интегрировать в свою ветку; затем собственные R1/R2/O2 по готовности. Критерии и scopes не меняются. Главный подтверждает приёмку и интеграцию; текущая запись не является независимым human approval.
