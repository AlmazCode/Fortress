# Разработчик №4 — Правила / Инфраструктура

> **С 17 октября 2026 года проект перешёл с Aster на обычный Git/GitHub. Aster MCP, регистрации, claims, leases, heartbeat и сигнал запуска для координации больше не используются.** Источник задач — `plan.json`, исходников и результатов — Git. Слова lease/fencing в backend-коде относятся к надёжности заданий и сохраняют технический смысл.

Твои задачи: **O1, R1, R2, R3, R, O2, O3, O, B**. Только они и их точные файлы ниже; не выполняй чужие зависимости. Прочитай [общую инструкцию](WORKFLOW.md), [продуктовое ТЗ](REQUIREMENTS.md) и корневой AGENTS.md. Старые личные ТЗ с aster_join_team/aster_claim_task/aster_submit_result больше не задают рабочий процесс.

## Порядок работы

Начни с O1 без ожидания K: фактический preflight и ранний сетевой инвентарь. После K доступны R1/R2 и O2. R3 ждёт R1/R2; O3 ждёт O1/O2. Собери R/O, а B выполняй после I. Нет источника/видимости — unknown, нет Docker/внешнего маршрута — конкретный blocker, не фиктивный pass.

Веди только [свой журнал](status/DEV-4.md).

Работай в своей изолированной ветке/worktree. Перед следующей задачей проверь точные принятые SHA её depends и текущий контракт. После тестов передай commit, diff, команды/exit codes, покрытие acceptance, ограничения и следующее действие. Обычный push своей ветки выполняется при действующем разрешении человека; push не равен приёмке и не разрешает запись в main. Если одна задача blocked, продолжи другую свою готовую. Не запрашивай рутинное подтверждение перехода и не жди MCP-сигнала.

| ID | Задача | Разработчик | После |
| --- | --- | --- | --- |
| O1 | Среда и внешний маршрут | №4 | — |
| R1 | Кейсы и нормативные источники | №4 | K |
| R2 | Память ролика и связей | №4 | K |
| R3 | Правила и сложные примеры | №4 | R1, R2 |
| R | Правила и источники | №4 | R3 |
| O2 | Compose и offline worker | №4 | K |
| O3 | TLS и внешний smoke | №4 | O1, O2 |
| O | Compose и доступ по HTTPS | №4 | O3 |
| B | Восстановление и benchmark | №4 | I |

## O1 — Среда и внешний маршрут

Разработчик №4. Фаза: implementation. Зависимости: нет.

Проверяемый результат: ранний аппаратный/сетевой инвентарь и воспроизводимые preflight команды; может идти параллельно контракту K.
Исходы: success: Известны реальные возможности/пробелы и путь проверки инфраструктуры. | missingTool: Нет Docker/FFmpeg/Python3.11 — список необходимых условий, не фиктивный pass. | gpu: CUDA/GPU не подтверждены — gpu_ready=false, CPU tooling можно готовить. | cgnat: Нет входящего пути/CGNAT — external_access_blocked до реального разрешённого маршрута. | externalPC: Другой training PC недоступен — handoff instructions готовы, hardware not verified.

### Разрешённые файлы

- `infra/scripts/preflight.sh`
- `infra/scripts/preflight.ps1`
- `infra/scripts/network-check.sh`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`

### Критерии приёмки

1. До чтения исходников проверены origin/main/base/rootPath своей копии. Команды только собирают факты, не меняют ключ/проект/репозиторий.
2. Ubuntu/WSL2, Python3.11, Docker/Compose, FFmpeg/ffprobe, NVIDIA toolkit, драйвер/CUDA/GPU/RAM/VRAM указаны фактическим output; наличие команды не считается работающим runtime.
3. В первые два часа проверяются входящий маршрут/домен/сертификат/CGNAT и допустимый транспорт, без настоящих видео и без скрытого облачного переноса.
4. Отсутствующее оборудование/другой ПК/программа имеет конкретную причину и readiness=false. Сам preflight CLI должен корректно работать и при отсутствии зависимостей.
5. Preflight не запускает training/deploy и не объявляет внешнийHTTPS успешным; фактический внешний smoke после настройки в O3.

### Исходы и блокировки

- **success**: Известны реальные возможности/пробелы и путь проверки инфраструктуры.
- **missingTool**: Нет Docker/FFmpeg/Python3.11 — список необходимых условий, не фиктивный pass.
- **gpu**: CUDA/GPU не подтверждены — gpu_ready=false, CPU tooling можно готовить.
- **cgnat**: Нет входящего пути/CGNAT — external_access_blocked до реального разрешённого маршрута.
- **externalPC**: Другой training PC недоступен — handoff instructions готовы, hardware not verified.

## R1 — Кейсы и нормативные источники

Разработчик №4. Фаза: implementation. Зависимости: K.

Проверяемый результат: матрица C01–C15: необходимые наблюдения, границы доказуемости, подтверждённые источники и точные пробелы.
Исходы: success: Для подтверждённого подмножества есть применимый source-backed mapping. | missingSource: Нет нормы/редакции/исходного кейса — unsupported/unknown; юридическая приёмка соответствующего кейса не пройдена. | notObservable: Сумма/подделка/проводка/полномочия/закрытая сумка недоказуемы — не делать вывод. | changedRule: Новая редакция источника требует новой rules version и повторной проверки затронутых кейсов.

### Разрешённые файлы

- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/sources/snapshots.jsonl`
- `docs/operations/SOURCES.md`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`

### Критерии приёмки

1. Все C01–C15 сохранены; у каждого prerequisites, объекты/состояния/интервалы, исключения и supported/unsupported/unknown. Кейс не превращается автоматически в action class.
2. Источник реально открыт: редакция, применимость, исключения, дата, source_kind, URL, локальный текст и SHA-256. Отсутствующий исходный кейс/юрисдикция не заменяется похожей нормой.
3. Неподтверждённый источник не создаёт юридически названное нарушение; форма объяснения факт→возможное несоответствие→источник→ограничение.
4. Для отсутствия действия требуются полный существенный интервал, видимость, проверенный recognizer, определённый конец этапа и альтернативы; недоказуемое остаётся unknown.
5. Исследование ограничено вопросами поддержки C01–C15: после двух бесплодных заходов сохранить URL/вывод/неизвестное и конкретный недостающий материал, продолжить независимый код.

### Исходы и блокировки

- **success**: Для подтверждённого подмножества есть применимый source-backed mapping.
- **missingSource**: Нет нормы/редакции/исходного кейса — unsupported/unknown; юридическая приёмка соответствующего кейса не пройдена.
- **notObservable**: Сумма/подделка/проводка/полномочия/закрытая сумка недоказуемы — не делать вывод.
- **changedRule**: Новая редакция источника требует новой rules version и повторной проверки затронутых кейсов.

## R2 — Память ролика и связей

Разработчик №4. Фаза: implementation. Зависимости: K.

Проверяемый результат: память существенных интервалов обслуживания/партий на весь ролик с неизвестными actors/relations и reset по сцене.
Исходы: success: Последовательные наблюдения образуют воспроизводимое состояние ролика. | scene: Новая сцена — reset и границы unknown, без переноса участников/денег. | missingActor: Нет проверенного actor/party link — unknown, не подстановка наиболее вероятного. | truncated: Начало/конец этапа отсутствует — недостаточная наблюдаемость для absence rule.

### Разрешённые файлы

- `rules/__init__.py`
- `rules/types.py`
- `rules/session_memory.py`
- `tests/rules/test_scene_reset.py`
- `tests/rules/test_session_memory.py`

### Критерии приёмки

1. Состояния и переходы session/party references определены контрактом K; неизвестная роль/связь явно nullable/unknown.
2. Память не теряется между overlapping windows того же ролика, но не переносится через смену сцены/новое видео.
3. Глобальный action score не считается actor ID; нет незаявленного face/person detector или выдуманного назначения роли.
4. Тесты проверяют cross-session, unresolved state, поздние события, неполный интервал, окклюзию и два независимых job.
5. Невидимость не закрывает unresolved state как resolved; отсутствие проверяемой связи не превращается в уверенный trigger.

### Исходы и блокировки

- **success**: Последовательные наблюдения образуют воспроизводимое состояние ролика.
- **scene**: Новая сцена — reset и границы unknown, без переноса участников/денег.
- **missingActor**: Нет проверенного actor/party link — unknown, не подстановка наиболее вероятного.
- **truncated**: Начало/конец этапа отсутствует — недостаточная наблюдаемость для absence rule.

## R3 — Правила и сложные примеры

Разработчик №4. Фаза: implementation. Зависимости: R1, R2.

Проверяемый результат: engine пяти шаблонов с трёхзначной логикой и покрытием всех кейсов без ложной юридической уверенности.
Исходы: success: Поддержанное правило объяснимо и покрыто сценарными тестами. | unknown: Нет видимости/полного этапа/recognizer/источника — unknown, не not_triggered. | exception: Подтверждённое исключение снимает trigger по явной логике, а не эвристической догадке. | failure: Ложный trigger на hard-negative — blocked до исправления, критерии не ослабляются.

### Разрешённые файлы

- `rules/engine.py`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`

### Критерии приёмки

1. prerequisite/unresolved-state/cross-session/presence/response возвращают triggered/not_triggered/unknown по явным входам; нет invisible=false.
2. У каждого поддержанного правила есть positive, hard-negative, truncated interval, occlusion и exception tests; неподдержанные C01–C15 отдельно проверяют unknown/unsupported.
3. Стол с деньгами, касание ПК, светлый кадр или уход сами по себе не trigger; сумма/подделка/проводка/OS lock/полномочия не выводятся по отсутствующим признакам.
4. Только source-backed applicable rule получает нормативное имя; source/версии/limitations доступны diagnostics, внешний jury contract не расширяется.
5. Синтетические observations проверяют rule logic, не являются доказательством ML accuracy или реальной видимости.

### Исходы и блокировки

- **success**: Поддержанное правило объяснимо и покрыто сценарными тестами.
- **unknown**: Нет видимости/полного этапа/recognizer/источника — unknown, не not_triggered.
- **exception**: Подтверждённое исключение снимает trigger по явной логике, а не эвристической догадке.
- **failure**: Ложный trigger на hard-negative — blocked до исправления, критерии не ослабляются.

## R — Правила и источники

Разработчик №4. Фаза: integration. Зависимости: R3.

Проверяемый результат: собранные R1–R3: versioned case/source mapping, session memory и tri-state rules с положительными, сложными отрицательными, неполными/закрытыми интервалами и исключениями. Проверить source provenance и объяснение на всём rule output. Отсутствие источника/наблюдаемости не выдавать за отсутствие нарушения.
Исходы: success: Поддержанное подмножество engine/source mappings проверено. | unknown: Нет применимой нормы/видимости/actors — unknown/unsupported; юридический gate не пройден. | failure: Ложный trigger/ложное not_triggered — исправить R1–R3, критерии не ослаблять.

### Разрешённые файлы

- `rules/__init__.py`
- `rules/engine.py`
- `rules/session_memory.py`
- `rules/types.py`
- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`
- `tests/rules/test_scene_reset.py`
- `docs/operations/RULES.md`
- `docs/operations/SOURCES.md`
- `rules/sources/snapshots.jsonl`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`
- `tests/rules/test_session_memory.py`

### Критерии приёмки

1. cases.v1.json содержит все маршруты C01–C15: пачка,документ,смешение/остаток партий,оставленные ценности,хранилище,ключ,документы/печати,экран после ухода,дверь/вход,пересчёт до хранения,без клиента,повторная обработка купюр,личные вещи,сосуд/питьё,приборы после смены; для каждого условия,данные,ограничения,тесты и support status.
2. Engine выдаёт triggered/not_triggered/unknown; невидимое не false. Для отсутствия действия требуются полный существенный интервал,visibility,проверенный recognizer,конец этапа и альтернативы; неполный/невалидированный recognizer возвращает unknown.
3. Пять шаблонов prerequisite,unresolved-state,cross-session,presence,response имеют явные входы,выходы и positive/hard-negative/truncated/occlusion/exception тесты для каждого поддержанного правила; unsupported маршруты отдельно тестируют честный unknown.
4. Session memory ведётся весь ролик для интервалов обслуживания/денежных партий/неизвестных связей. Scene reset разделяет сессии, score действия не actor ID; неизвестные actors/roles/связи не выдумываются.
5. Нормативно именованное нарушение допускается лишь при открытом первоисточнике с редакцией/применимостью/исключениями,локальной копией/хэшем,датой,source_kind и provenance. Если первоисточник/исходный кейс недоступен, юридическая приёмка соответствующего правила остаётся unknown/blocked, нормативные названия не фабрикуются.
6. Проверки не выводят сумму/подделку/системную проводку/блокировку ОС/полномочия/содержимое непрозрачной сумки из отсутствующих признаков; стол с деньгами,касание ПК,светлый кадр или уход сами по себе не trigger.
7. Объяснение строго факт → признак возможного несоответствия → источник → ограничение; подлинные кадры/таймкоды приходят из pipeline, а не из шаблона rule pack. rules version и source provenance доступны diagnostics.
8. Тесты engine/session memory выполняются на явных synthetic observations, не выдаются за ML validation; docs/operations/RULES.md и SOURCES.md фиксируют критерии достаточности,фактически открытые URL,неизвестное и конкретные внешние пробелы без бесконечного поиска.

### Исходы и блокировки

- **success**: Поддержанное подмножество engine/source mappings проверено.
- **unknown**: Нет применимой нормы/видимости/actors — unknown/unsupported; юридический gate не пройден.
- **failure**: Ложный trigger/ложное not_triggered — исправить R1–R3, критерии не ослаблять.

## O2 — Compose и offline worker

Разработчик №4. Фаза: implementation. Зависимости: K.

Проверяемый результат: конфигурация nginx/api/worker/redis/postgres с локальными volumes и изоляцией GPU/сети.
Исходы: success: Воспроизводимые контейнеры/volumes/изоляция готовы для I. | noDocker: Config может быть подготовлен, но реальный container/offline test остаётся blocked/not_run. | noGPU: Нет подтверждённого GPU runtime — gpu_ready=false, CPU test profile отдельно. | egress: Интернет доступен worker — isolation failure, устранить до финала. | volume: Данные пропали после restart — blocked, пользовательские volumes не удалять для исправления.

### Разрешённые файлы

- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/redis.conf`
- `infra/env.example`
- `tests/performance/test_compose_isolation.py`

### Критерии приёмки

1. Compose config валиден; production GPU только worker, concurrency=1/prefetch/CPU threads ограничены; Redis/PostgreSQL без внешних published ports.
2. DB/media/model volumes постоянны; readiness приложения/модели разделена с container health, restart не стирает данные.
3. Worker не имеет интернет-egress, но доступ к локальным DB/queue остаётся; packages/weights готовятся отдельно, runtime downloads отсутствуют.
4. Образы используют общие согласованные locks K и frontend lock; secrets передаются вне Git, примеры только placeholders.
5. До I инфраструктура проверяется config и явно synthetic harness; build/start всего готового приложения проверяется только после принятой интеграции, не объявляется выполненным по YAML.

### Исходы и блокировки

- **success**: Воспроизводимые контейнеры/volumes/изоляция готовы для I.
- **noDocker**: Config может быть подготовлен, но реальный container/offline test остаётся blocked/not_run.
- **noGPU**: Нет подтверждённого GPU runtime — gpu_ready=false, CPU test profile отдельно.
- **egress**: Интернет доступен worker — isolation failure, устранить до финала.
- **volume**: Данные пропали после restart — blocked, пользовательские volumes не удалять для исправления.

## O3 — TLS и внешний smoke

Разработчик №4. Фаза: implementation. Зависимости: O1, O2.

Проверяемый результат: настроенный Nginx/HTTPS и наблюдённый внешний upload/status smoke на явном synthetic harness.
Исходы: success: Trusted внешний HTTPS маршрут наблюдён на synthetic data. | localOnly: Доступен только localhost — local_only, обязательный внешний критерий не пройден. | certificate: Нет валидной цепочки/имени/срока — TLS failure до исправления. | network: CGNAT/firewall/маршрут не разрешены — external_access_blocked, без самовольного туннеля. | leak: Сервис БД/Redis/media стал публичен безauth — blocked до исправления.

### Разрешённые файлы

- `infra/nginx.conf`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

### Критерии приёмки

1. TLS завершает Nginx; сертификат/hostname/expiry/chain и разрешённый внешний маршрут проверены, ключи/сертификатные секреты вне Git.
2. Proxy limits соответствуют200МиБ и полному deadline; auth headers сохраняются, media/diagnostics не становятся публичными.
3. Через внешний клиент проверены tiny synthetic upload→status и ошибки; до I это только обозначенный test harness, а не проверка модели/всего продукта.
4. CGNAT/нет домена/сертификата/разрешённого транспорта — точный blocker; local self-signed smoke не объявляется внешним trustedHTTPS.
5. Не подключать облачный transport/AI и не раскрывать видео ради smoke. Реальный API/browser повтор внешнего пути выполняется в I/B.

### Исходы и блокировки

- **success**: Trusted внешний HTTPS маршрут наблюдён на synthetic data.
- **localOnly**: Доступен только localhost — local_only, обязательный внешний критерий не пройден.
- **certificate**: Нет валидной цепочки/имени/срока — TLS failure до исправления.
- **network**: CGNAT/firewall/маршрут не разрешены — external_access_blocked, без самовольного туннеля.
- **leak**: Сервис БД/Redis/media стал публичен безauth — blocked до исправления.

## O — Compose и доступ по HTTPS

Разработчик №4. Фаза: integration. Зависимости: O3.

Проверяемый результат: собранные O1–O3: preflight, Compose isolation/volumes, Nginx/TLS и фактически наблюдённый внешний synthetic smoke. Начать O1 в первые два часа; №4 выполняет свои готовые R/O карточки последовательно без искусственных связей. До I проверка на infra harness не считается запуском всего приложения; после I внешний real-API повтор в B.
Исходы: success: Среда/изоляция/volumes/внешний HTTPS подтверждены реальными checks. | localOnly: Только localhost — local_only; внешний обязательный критерий blocked. | missing: Нет Docker/GPU/FFmpeg/сертификата/маршрута — конкретный blocker, остальные ветки продолжаются. | failure: Public DB/Redis,worker egress,потеря volumes или TLS error — blocked до исправления.

### Разрешённые файлы

- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/nginx.conf`
- `infra/redis.conf`
- `infra/env.example`
- `infra/scripts/preflight.sh`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-check.sh`
- `infra/scripts/smoke.sh`
- `docs/operations/SETUP.md`
- `docs/operations/NETWORK.md`
- `infra/scripts/preflight.ps1`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`
- `tests/performance/test_compose_isolation.py`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

### Критерии приёмки

1. Compose содержит nginx/api/worker/redis/postgres; GPU устройства доступны только worker, GPU concurrency=1/prefetch/CPU threads и memory limits согласованы с 16 ГБ RAM. postgres/redis не публикуют внешние порты.
2. Локальные media/model/DB volumes переживают restart; restart/healthcheck и startup ordering не принимают readiness модели за readiness контейнера. Runtime analysis не скачивает пакеты/веса.
3. Preflight проверяет реальную ОС/WSL2,Docker Compose,NVIDIA Container Toolkit,GPU/CUDA/Python3.11/FFmpeg и совместимость версий; отсутствующее или непроверенное фиксируется, никаких заявлений о целевом железе по названию.
4. Nginx завершает TLS,проксирует защищённые API/media и frontend,согласует upload200 МиБ/timeouts. Сертификат/секреты не входят в Git, нет API ключа в bundle/URL/logs.
5. network-check/tls-check наблюдают внешний HTTPS upload→status на synthetic media без настоящих видео. CGNAT/нет домена/сертификата/разрешённого транспорта — конкретный blocker внешнего доступа; local-only smoke не объявляется внешним.
6. Worker не имеет доступа к интернету в runtime,но видит только необходимые локальные сервисы; firewall/network topology и offline smoke подтверждают отсутствие egress без блокировки PostgreSQL/Redis.
7. infra/env.example и SETUP/NETWORK описывают реальные команды подготовки/запуска/остановки,порты,paths,healthcheck,сертификат,резервирование volumes и ограничения; контейнеры и зависимости зафиксированы совместимыми lock/digest в реализации, не проверены заранее в плане.

### Исходы и блокировки

- **success**: Среда/изоляция/volumes/внешний HTTPS подтверждены реальными checks.
- **localOnly**: Только localhost — local_only; внешний обязательный критерий blocked.
- **missing**: Нет Docker/GPU/FFmpeg/сертификата/маршрута — конкретный blocker, остальные ветки продолжаются.
- **failure**: Public DB/Redis,worker egress,потеря volumes или TLS error — blocked до исправления.

## B — Восстановление и benchmark

Разработчик №4. Фаза: verification. Зависимости: I.

Проверяемый результат: сквозные fault/offline/capacity/deadline/HTTPS проверки после I плюс готовая benchmark-команда для будущего trained release. Реальные сервисные failure/recovery тесты обязательны сейчас; latency/VRAM/RAM модели остаются не измерены до weights. Не удалять пользовательские volumes и не открывать worker internet ради прохождения проверки.
Исходы: success: Fault/offline/queue/HTTPS проверки прошли; benchmark инструменты готовы. | noWeights: Настоящие latency/VRAM/RAM не измерены, synthetic цифры отдельно. | networkBlocked: Нет trusted external route — обязательный network gate blocked. | failure: Crash/retry/stale job/security regression — исправить A/O/I, затем повторить затронутые проверки.

### Разрешённые файлы

- `rules/__init__.py`
- `rules/engine.py`
- `rules/session_memory.py`
- `rules/types.py`
- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`
- `tests/rules/test_scene_reset.py`
- `docs/operations/RULES.md`
- `docs/operations/SOURCES.md`
- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/nginx.conf`
- `infra/redis.conf`
- `infra/env.example`
- `infra/scripts/preflight.sh`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-check.sh`
- `infra/scripts/smoke.sh`
- `docs/operations/SETUP.md`
- `docs/operations/NETWORK.md`
- `tests/performance/benchmark.py`
- `tests/performance/test_offline.py`
- `tests/performance/test_crash_retry.py`
- `tests/performance/test_capacity_deadline.py`
- `tests/performance/test_https.py`
- `tests/performance/test_service_resources.py`
- `docs/operations/RECOVERY.md`
- `docs/operations/BENCHMARK.md`
- `docs/operations/ACCEPTANCE.json`
- `rules/sources/snapshots.jsonl`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`
- `tests/rules/test_session_memory.py`
- `infra/scripts/preflight.ps1`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`
- `tests/performance/test_compose_isolation.py`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

### Критерии приёмки

1. Fault injection подтверждает durable PostgreSQL/outbox recovery при падении API/worker/Redis,повторной доставке и истёкшем lease: одно выполнение/один итог,без потерянного задания или ошибочного no_violation.
2. Capacity race допускает одно незавершённое задание до benchmark,остальным429; deadline≤240с от приёма приводит к failed при превышении,late result не затирает failure. Не более одного waiting job разрешается только после реальной оценки общего≤240с.
3. Worker offline smoke не делает интернет-запросов и сохраняет необходимые DB/queue связи; restart volumes восстанавливает jobs/media/models. Runtime downloads и облачная обработка отсутствуют.
4. Внешний HTTPS smoke на synthetic media реально проверяет сертификат,маршрут,auth,upload/poll/media и ошибки. CGNAT/сертификат/маршрут без подтверждения остаются blocked; конфигурация сама по себе не считается прохождением.
5. Benchmark CLI измеряет receipt→queue→decode→inference→rules→preview/evidence→response,elapsed от приёма и внешний upload→ответ; описаны warm/cold,p95,число прогонов,hardware/runtime/commit/dataset/release hashes и единицы памяти.
6. Для последующего trained release заложены цели service≤240с,внешний путь≤300с,145с video warm p95≤60с и каждый≤120с,VRAM train≤6,5ГБ/inference≤3ГБ,RAM train≤10ГБ/всего сервиса≤5ГБ. Сейчас реальные latency/память/ML performance остаются not measured,synthetic timings явно отдельно.
7. RECOVERY/BENCHMARK/ACCEPTANCE содержат фактические команды/exitCode/commit и blockers; отсутствие Docker/FFmpeg/CUDA/внешнего доступа не отмечается passed и не ослабляет обязательную программную/сетевую приёмку.
8. Проверены fencing stale worker и capacity race; safe checkpoint/volumes recovery не требует удаления пользовательских данных или повторной публикации проекта.

### Исходы и блокировки

- **success**: Fault/offline/queue/HTTPS проверки прошли; benchmark инструменты готовы.
- **noWeights**: Настоящие latency/VRAM/RAM не измерены, synthetic цифры отдельно.
- **networkBlocked**: Нет trusted external route — обязательный network gate blocked.
- **failure**: Crash/retry/stale job/security regression — исправить A/O/I, затем повторить затронутые проверки.
