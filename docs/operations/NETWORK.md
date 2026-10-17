# Сеть, TLS и synthetic smoke

`nginx` — единственный сервис с published port, по умолчанию `127.0.0.1:8443`. Изменение bind на разрешённый внешний интерфейс выполняется только при готовом согласованном маршруте; оно само не подтверждает доступ извне. PostgreSQL/Redis не публикуют порты. API соединяет edge/backend, IP forwarding выключен; worker присоединён только к `backend`, который имеет `internal: true`.

Redis сознательно использует доверенный закрытый service network без multi-tenant auth; `protected-mode no` допустим здесь только при отсутствии host ports и внешних network attachments. Если топология меняется, конфигурация должна быть пересмотрена. Worker/API — доверенные локальные участники. Реальная изоляция, firewall и отсутствие egress ещё не измерены: Docker на текущем хосте отсутствует.

Nginx завершает TLS 1.2/1.3, хранит certificate/key в private bind mount read-only, передаёт X-API-Key в backend и не пишет access logs. В конфигурации нет прямого alias к media/models. Ограничение proxy 201 MiB оставляет multipart envelope; backend обязан ограничить именно file до 200 MiB. Upload/proxy timeouts 300 s — настройки, не подтверждение внешнего deadline 300 s или service deadline 240 s.

## CLI

```sh
sh infra/scripts/tls-check.sh --external-url https://HOSTNAME
sh infra/scripts/network-smoke.sh --url https://HOSTNAME --key-file /PRIVATE/smoke-key.txt
```

Заменить HOSTNAME и private path. TLS использует обычную проверку цепочки/имени/срока; `tls-check` возвращает exit 2, если trusted TLS probe не наблюдён. Самоподписанный/недоверенный сертификат не обходится. `network-smoke` допускает явный `--ca-file` для предоставленного private CA, не отключает hostname verification и отказывает в redirects. API-ключ читается из локального bounded файла; в URL/command arguments он не передаётся.

`network-smoke` предназначен **только для infra harness** из compose.test.yaml, отправляет небольшой синтетический маркер, не видео. Harness требует специальный synthetic header/body, отказывает реальным файлам, ограничен 4 KiB/128 in-memory records, проверяет auth и возвращает `smoke_complete`, а не публичный ML verdict. Вывод всегда содержит synthetic/infrastructure_only и не является API/ML acceptance.

Для loopback HTTP unit smoke есть явный `--allow-local-http`, разрешённый только для localhost/loopback. Его результат `local_only=true`, `tls_verified=false`, `external_access_verified=false`. Даже trusted HTTPS с текущего хоста не заявляется независимым внешним наблюдением. Внешний клиент должен реально выполнить проверку по разрешённому маршруту; главный сохраняет и проверяет его фактический отчёт в O3, а после I/B — на настоящем API. В текущей среде такой маршрут/hostname/сертификат не предоставлены, gate остаётся blocked.

## Фактически проверено сейчас

`tests/performance/test_network_smoke.py` запускает настоящий ThreadingHTTPServer на loopback со случайным портом и проверяет auth → tiny synthetic upload → status, неверный ключ, отказ неподдержанного/oversized тела и невозможность неявного запуска harness. Это real local HTTP test; trusted TLS, внешний путь, Nginx, контейнеры, БД и worker он не проверяет.

`test_compose_isolation.py` читает YAML, проверяет networks, volumes, limits, pins, GPU ownership, отсутствие published DB/Redis и no alias/log leakage. Это static check; `docker compose config`, build, restart/volumes и runtime egress **not_run**. Обязательные runtime/network критерии не объявлены passed.

Первичные документы, реально открытые при реализации: [Compose networks](https://docs.docker.com/reference/compose-file/networks/), [GPU reservations](https://docs.docker.com/compose/how-tos/gpu-support/), [Compose merge/reset](https://docs.docker.com/reference/compose-file/merge/). Из них взяты topology/GPU/override механизмы; фактическая работоспособность данной конфигурации требует отдельного запуска в целевом runtime.
