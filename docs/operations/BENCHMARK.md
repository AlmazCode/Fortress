# Измерения и клиент программной проверки

`tests/performance/benchmark.py` — рабочий Python 3.11 HTTP-клиент и отдельный native resource sampler. Виртуализация/WSL/Docker для самого клиента не нужны. Он не запускает сервисы, не подменяет backend и не обучает модель. Shared dependencies берутся из K lock. Реальная приёмка B остаётся после I; подготовка этого инструмента не закрывает зависимость.

## Проверка production без весов

```powershell
.venv/Scripts/python.exe tests/performance/benchmark.py --url https://HOSTNAME --key-file /PRIVATE/operator-key.txt --output /PRIVATE/production-gate.json --mode production-gate
```

HOSTNAME и `/PRIVATE/...` — заменяемые placeholders. Ключ читается из bounded файла, не передаётся аргументом/URL и не попадает в отчёт. Требуются 401 без ключа на model/job/media, защищённый unknown job 404, production model `not_ready`, upload `503 model_not_ready` без job ID. Этот probe намеренно не является декодируемым видео: проверяется ранний readiness gate, а не FFmpeg/очередь/анализ. При неожиданном ready upload не выполняется. Exit 0 означает, что ожидаемый запрет сработал, не готовность модели.

Историческое несоответствие A `043eeb6` (`not_found` вместо K `job_not_found`/`media_not_found`) исправлено владельцем backend в принятом `c46a2c005e2882c0c794bc44cecb7ff3cc393d13` и входит в integration `69f2a3835a3b9964f8fc03922ea7da5ff03e9aa5`. №4 на свежем коде проверил шесть настоящих serializer bodies — exit 0. Клиент/K не ослаблены: regression отказа на старый `not_found` сохраняется. Это не новый запуск настоящего backend на Windows и не приёмка I; внешний production probe выполняется на фактически запущенном исправленном сервисе.

## Synthetic pipeline после I

На настоящем API с **явно отдельным test profile/injection** и известным синтетическим MP4/MOV:

```powershell
.venv/Scripts/python.exe tests/performance/benchmark.py --url https://HOSTNAME --key-file /PRIVATE/operator-key.txt --output /PRIVATE/synthetic-warm.json --mode synthetic-analysis --video /PRIVATE/synthetic.mp4 --runs 10 --warmup 1 --cache-state warm --preflight /PRIVATE/service-preflight.json --dataset-manifest /PRIVATE/dataset.json --release-manifest /PRIVATE/release.json --service-commit FULL_SERVICE_SHA
```

FULL_SERVICE_SHA — фактически проверенный 40-символьный SHA развёрнутого сервиса, не SHA клиента по предположению. До I документированного CLI для test injection нет: A CLI допускает только production, поэтому нельзя подставить выдуманный `--test`/`FORTRESS_PROFILE=test`. Fixture bootstrap обеспечивает №1 в I. Клиент требует model `test_only=true` до upload и provenance `synthetic` у принятого задания. Production endpoint он таким режимом не нагружает.

Путь: header auth → multipart streaming upload → 202 UUID → public/UI polling → terminal → original SHA/size → preview → все source-frame URLs с проверкой hash против JPEG из public result. Media URLs жёстко привязаны к тому же job; redirect не выполняется. JSON/media/input/тайм-ауты ограничены, после неоднозначного acceptance/transport failure новые upload не повторяются. Для ожидаемого failure есть `--expect-terminal failed --expect-reason insufficient_evidence` (также deadline и остальные K reasons). Failed sample не попадает в статистику успешного анализа; fully unknown не становится clean verdict.

Plain HTTP допускается только для loopback и только с `--allow-local-http`. HTTPS всегда проверяет сертификат/имя; `--ca-file` явно задаёт private CA, не отключает verification. Report `tls_verified` становится true только после настоящего успешного TLS response. Loopback остаётся local_only. `external_access_verified=false` сохраняется: независимый внешний наблюдатель и сверка маршрута — отдельный обязательный gate.

## Что измеряется

Все длительности — **seconds**, monotonic clock клиента. `upload_accept_elapsed_sec` включает отправку multipart и получение 202; `accept_to_terminal_elapsed_sec` — ожидание terminal; `client_upload_to_terminal_sec` — весь этот путь; `media_fetch_elapsed_sec` — последующее получение original/preview/JPEG. Polling даёт дискретную верхнюю границу обнаружения terminal, не серверный timestamp. Auth/model prechecks выполняются до начала измеряемого upload.

`observed_stages` — время, когда stage увидел клиент, не длительность стадии. Принятый K не возвращает timing telemetry: receipt/queue/decode/inference/rules/preview-evidence/response и server receipt→response остаются null с причиной. Для закрытия B №1/I должен предоставить отдельную локальную, проверяемую server trace с единым monotonic origin, исходным video SHA и job ID. Не вычислять эти значения по разнице poll-снимков и не менять публичную jury-схему ради benchmark.

Warmup исключается из latency summary. p95 — nearest rank `sorted[ceil(.95*n)-1]`, дополнительно n/min/max; при отсутствии успешных samples значения null, не 0. Warm/cold — только operator label, `cache_state_verified=false`: cold требует фактически зарегистрированного restart/очистки только собственного разрешённого cache до прогона; warm требует документированного прогрева. Клиент не делает restart/удаление cache самостоятельно.

Report содержит SHA клиента и dirty flag, отдельно operator-supplied service SHA с verified=false, hashes uv.lock/rules/dataset/release, безопасный hardware subset из preflight и hash исходного hardware report. Missing manifests/hardware остаются unknown. URL заменён fingerprint SHA; private paths, ключи, видео и JPEG не сохраняются. Output create-only: существующий отчёт отвергается **до запросов**. Exit 2 означает failure/blocked; сырой текст transport/SQL/path exceptions не печатается.

## RAM/VRAM без контейнеров

В отдельном терминале во время конкретного прогона указать **все** PID сервисов и их children:

```powershell
.venv/Scripts/python.exe tests/performance/benchmark.py --collect-resources --pid api=111 --pid worker=222,223 --pid postgres=333,334 --pid redis=444 --pid nginx=555,556 --samples 60 --sample-interval 1 --output /PRIVATE/resources.json
```

Примерные PID заменить PID собственного тестового запуска. Нельзя получать «общий сервис» из одного worker PID или считать отсутствующий child нулевым потреблением. Дубли, неизвестные роли, отрицательные PID и чрезмерные budgets отвергаются. Процессы не завершаются/не изменяются. Windows: Get-Process WorkingSet64; Linux: `/proc/PID/statm` RSS × фактический page size. Единица RAM — bytes. Общая сумма появляется только при всех пяти ролях; это сумма RSS/working sets, может повторно учитывать shared pages и не является cgroup accounting.

VRAM берётся из `nvidia-smi --query-compute-apps=pid,used_gpu_memory`, только для явно указанных worker PID. Единица — MiB (1 MiB = 1048576 bytes). N/A, отсутствие нужного PID/команды или отказ query остаются null. Report содержит observed maximum по отсчётам, не гарантированный мгновенный пик; role/PID scope и соответствие sampling window конкретному job автоматически не подтверждаются. Если PID недоступен/бюджет исчерпан — failed с сохранением уже собранных samples. Для приёмки сопоставить UTC/elapsed window и job, команды запуска, все children, hardware/runtime/release provenance.

Native тесты действительно измеряют RSS собственного pytest процесса; это тест sampler, не RAM сервиса. Техническая агрегация, missing-process/partial-scope, единицы и null VRAM покрыты отдельно. Не выдавать эти цифры за GPU/model benchmark.

## Отложенные цели

До реального trained release все production latency/VRAM/RAM/ML quality **not measured**. Цели будущего прогона: service ≤240 s, внешний upload→ответ ≤300 s, для 145 s video warm p95 ≤60 s и каждый ≤120 s; inference VRAM ≤3 GB, train ≤6.5 GB; service RAM ≤5 GB, train ≤10 GB. GB в итоговом сопоставлении явно определить в bytes, MiB пересчитать; не смешивать Decimal GB и GiB. Этот sampler не проверяет training budget и не запускает обучение.

Фактические команды, SHA, exit codes и незакрытые gates — [ACCEPTANCE.json](ACCEPTANCE.json) и [журнал №4](../github-plan/status/DEV-4.md). Протокольный fixture не подтверждает DB/outbox/FFmpeg/PTS/offline/внешний TLS или качество ML.
