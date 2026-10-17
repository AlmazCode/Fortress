# Разработчик №4 — Правила / Инфраструктура

Свои задачи: O1, R1, R2, R3, R, O2, O3, O, B.

## Как исполнять этот план через GitHub

Это перенос существующего плана, а не новый граф. ID, исполнители, files, acceptance и зависимости сохранены.
Последняя свежая сверка Aster недоступна из-за ошибки связи. Состояние задач здесь НЕ считается подтверждённым: сначала проверить имеющиеся ветки, коммиты и PR. Не повторять уже доказанную работу и не объявлять её готовой по старому снимку.

1. Каждый разработчик работает только в своей ветке и отдельном checkout/worktree. Номер направления постоянный; другие разработчики того же аккаунта могут работать параллельно. GitHub не запускает и не пробуждает чаты.
2. №1 владеет контрактом K, backend, общей интеграцией и финальной сдачей. №2 — frontend, №3 — ML/data, №4 — rules/infra. Общие файлы изменяет один заранее назначенный владелец.
3. K и O1 не имеют зависимостей. После проверенного K открываются соответствующие ветки; O1 может идти параллельно K. Затем выполнять только собственные задачи с закрытыми depends, а при блокере брать другую собственную готовую задачу.
4. Принятый prerequisite здесь означает проверенный результат в согласованной интеграционной ветке/PR с точным SHA. Открытый PR или локальный commit сами по себе не означают принятие. После интеграции брать актуальный контракт из Git, а не продолжать навечно от исходного initial commit.
5. Результаты передавать через обычные Git-коммиты и PR при действующем разрешении пользователя. Главный проверяет точные коммиты, объединяет совместимые изменения и выполняет финальные сквозные проверки. Защиту веток и требуемые проверки GitHub соблюдать.
6. Каждый редактирует только свой status/DEV-N.md: task ID, состояние, branch, commit/PR, реально запущенные проверки, блокер и следующее действие. Главный ведёт STATUS.md. Не давать четырём разработчикам одновременно менять один общий журнал.
7. Продолжать последовательно по своему направлению без вопроса на каждую задачу в пределах разрешённого запуска. Если ждёшь чужую работу, проверять Git/PR ограниченными интервалами в активном ходе; не изображать фоновое выполнение после остановки чата.
8. Ресёрч только для текущего обязательного пробела, с контрольной точкой после двух бесплодных заходов. Не добавлять карточки, не ослаблять acceptance и не заменять проверки формальным отчётом. Конфликты разрешать по контракту и фактическому коду, сохраняя чужие изменения.
9. Обучение модели остаётся на другом локальном ПК. Сейчас нужны CLI, tiny CPU smoke, инструкции и честный model_not_ready без весов. Не запускать полное обучение и не объявлять качество/производительность подтверждёнными без реальных данных.

### Что меняется относительно Aster

MCP-claim заменяется закреплённым разработчиком, веткой и собственным журналом. Aster accepted заменяется проверенной интеграцией точного Git-коммита. Heartbeat не нужен для разрешения работать через GitHub. Не вызывать Aster MCP ради регистрации, ожидания, смены статуса или сдачи в этом режиме.

Исходные описания ниже дословные и содержат исторические указания «сейчас только план», manual, MCP и запрет push/PR/merge. Экспорт сам по себе не даёт разрешения исполнять код или публиковать что-либо. После явного нового запуска пользователем административный порядок задаётся его текущей инструкцией и этим GitHub-процессом; продуктовые требования и acceptance сохраняются. Новая инструкция не отменяет ограничения на обучение, секреты, данные и внешнюю публикацию.

### O1 — Среда и внешний маршрут

Разработчик: №4. Тип: code. Фаза: implementation.
Зависимости: нет. Состояние: не сверено с Git.

Файлы:

- `infra/scripts/preflight.sh`
- `infra/scripts/preflight.ps1`
- `infra/scripts/network-check.sh`
- `docs/operations/PREFLIGHT.md`
- `docs/operations/NETWORK_INVENTORY.md`
- `tests/performance/test_preflight_report.py`

Критерии приёмки:

- До чтения исходников проверены origin/main/base/rootPath своей копии. Команды только собирают факты, не меняют ключ/проект/репозиторий.
- Ubuntu/WSL2, Python3.11, Docker/Compose, FFmpeg/ffprobe, NVIDIA toolkit, драйвер/CUDA/GPU/RAM/VRAM указаны фактическим output; наличие команды не считается работающим runtime.
- В первые два часа проверяются входящий маршрут/домен/сертификат/CGNAT и допустимый транспорт, без настоящих видео и без скрытого облачного переноса.
- Отсутствующее оборудование/другой ПК/программа имеет конкретную причину и readiness=false. Сам preflight CLI должен корректно работать и при отсутствии зависимостей.
- Preflight не запускает training/deploy и не объявляет внешнийHTTPS успешным; фактический внешний smoke после настройки в O3.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: ранний аппаратный/сетевой инвентарь и воспроизводимые preflight команды; может идти параллельно контракту K.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Известны реальные возможности/пробелы и путь проверки инфраструктуры. | missingTool: Нет Docker/FFmpeg/Python3.11 — список необходимых условий, не фиктивный pass. | gpu: CUDA/GPU не подтверждены — gpu_ready=false, CPU tooling можно готовить. | cgnat: Нет входящего пути/CGNAT — external_access_blocked до реального разрешённого маршрута. | externalPC: Другой training PC недоступен — handoff instructions готовы, hardware not verified.

</details>

### R1 — Кейсы и нормативные источники

Разработчик: №4. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `rules/packs/cases.v1.json`
- `rules/sources/index.json`
- `rules/sources/snapshots.jsonl`
- `docs/operations/SOURCES.md`
- `docs/operations/CASE_SUPPORT.md`
- `tests/rules/test_case_mapping.py`

Критерии приёмки:

- Все C01–C15 сохранены; у каждого prerequisites, объекты/состояния/интервалы, исключения и supported/unsupported/unknown. Кейс не превращается автоматически в action class.
- Источник реально открыт: редакция, применимость, исключения, дата, source_kind, URL, локальный текст и SHA-256. Отсутствующий исходный кейс/юрисдикция не заменяется похожей нормой.
- Неподтверждённый источник не создаёт юридически названное нарушение; форма объяснения факт→возможное несоответствие→источник→ограничение.
- Для отсутствия действия требуются полный существенный интервал, видимость, проверенный recognizer, определённый конец этапа и альтернативы; недоказуемое остаётся unknown.
- Исследование ограничено вопросами поддержки C01–C15: после двух бесплодных заходов сохранить URL/вывод/неизвестное и конкретный недостающий материал, продолжить независимый код.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: матрица C01–C15: необходимые наблюдения, границы доказуемости, подтверждённые источники и точные пробелы.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Для подтверждённого подмножества есть применимый source-backed mapping. | missingSource: Нет нормы/редакции/исходного кейса — unsupported/unknown; юридическая приёмка соответствующего кейса не пройдена. | notObservable: Сумма/подделка/проводка/полномочия/закрытая сумка недоказуемы — не делать вывод. | changedRule: Новая редакция источника требует новой rules version и повторной проверки затронутых кейсов.

</details>

### R2 — Память ролика и связей

Разработчик: №4. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `rules/__init__.py`
- `rules/types.py`
- `rules/session_memory.py`
- `tests/rules/test_scene_reset.py`
- `tests/rules/test_session_memory.py`

Критерии приёмки:

- Состояния и переходы session/party references определены контрактом K; неизвестная роль/связь явно nullable/unknown.
- Память не теряется между overlapping windows того же ролика, но не переносится через смену сцены/новое видео.
- Глобальный action score не считается actor ID; нет незаявленного face/person detector или выдуманного назначения роли.
- Тесты проверяют cross-session, unresolved state, поздние события, неполный интервал, окклюзию и два независимых job.
- Невидимость не закрывает unresolved state как resolved; отсутствие проверяемой связи не превращается в уверенный trigger.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: память существенных интервалов обслуживания/партий на весь ролик с неизвестными actors/relations и reset по сцене.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Последовательные наблюдения образуют воспроизводимое состояние ролика. | scene: Новая сцена — reset и границы unknown, без переноса участников/денег. | missingActor: Нет проверенного actor/party link — unknown, не подстановка наиболее вероятного. | truncated: Начало/конец этапа отсутствует — недостаточная наблюдаемость для absence rule.

</details>

### R3 — Правила и сложные примеры

Разработчик: №4. Тип: code. Фаза: implementation.
Зависимости: R1, R2. Состояние: не сверено с Git.

Файлы:

- `rules/engine.py`
- `rules/fixtures/cases.json`
- `tests/rules/test_cases.py`
- `tests/rules/test_templates.py`
- `tests/rules/test_unknown.py`

Критерии приёмки:

- prerequisite/unresolved-state/cross-session/presence/response возвращают triggered/not_triggered/unknown по явным входам; нет invisible=false.
- У каждого поддержанного правила есть positive, hard-negative, truncated interval, occlusion и exception tests; неподдержанные C01–C15 отдельно проверяют unknown/unsupported.
- Стол с деньгами, касание ПК, светлый кадр или уход сами по себе не trigger; сумма/подделка/проводка/OS lock/полномочия не выводятся по отсутствующим признакам.
- Только source-backed applicable rule получает нормативное имя; source/версии/limitations доступны diagnostics, внешний jury contract не расширяется.
- Синтетические observations проверяют rule logic, не являются доказательством ML accuracy или реальной видимости.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: engine пяти шаблонов с трёхзначной логикой и покрытием всех кейсов без ложной юридической уверенности.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Поддержанное правило объяснимо и покрыто сценарными тестами. | unknown: Нет видимости/полного этапа/recognizer/источника — unknown, не not_triggered. | exception: Подтверждённое исключение снимает trigger по явной логике, а не эвристической догадке. | failure: Ложный trigger на hard-negative — blocked до исправления, критерии не ослабляются.

</details>

### R — Правила и источники

Разработчик: №4. Тип: code. Фаза: integration.
Зависимости: R3. Состояние: не сверено с Git.

Файлы:

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

Критерии приёмки:

- cases.v1.json содержит все маршруты C01–C15: пачка,документ,смешение/остаток партий,оставленные ценности,хранилище,ключ,документы/печати,экран после ухода,дверь/вход,пересчёт до хранения,без клиента,повторная обработка купюр,личные вещи,сосуд/питьё,приборы после смены; для каждого условия,данные,ограничения,тесты и support status.
- Engine выдаёт triggered/not_triggered/unknown; невидимое не false. Для отсутствия действия требуются полный существенный интервал,visibility,проверенный recognizer,конец этапа и альтернативы; неполный/невалидированный recognizer возвращает unknown.
- Пять шаблонов prerequisite,unresolved-state,cross-session,presence,response имеют явные входы,выходы и positive/hard-negative/truncated/occlusion/exception тесты для каждого поддержанного правила; unsupported маршруты отдельно тестируют честный unknown.
- Session memory ведётся весь ролик для интервалов обслуживания/денежных партий/неизвестных связей. Scene reset разделяет сессии, score действия не actor ID; неизвестные actors/roles/связи не выдумываются.
- Нормативно именованное нарушение допускается лишь при открытом первоисточнике с редакцией/применимостью/исключениями,локальной копией/хэшем,датой,source_kind и provenance. Если первоисточник/исходный кейс недоступен, юридическая приёмка соответствующего правила остаётся unknown/blocked, нормативные названия не фабрикуются.
- Проверки не выводят сумму/подделку/системную проводку/блокировку ОС/полномочия/содержимое непрозрачной сумки из отсутствующих признаков; стол с деньгами,касание ПК,светлый кадр или уход сами по себе не trigger.
- Объяснение строго факт → признак возможного несоответствия → источник → ограничение; подлинные кадры/таймкоды приходят из pipeline, а не из шаблона rule pack. rules version и source provenance доступны diagnostics.
- Тесты engine/session memory выполняются на явных synthetic observations, не выдаются за ML validation; docs/operations/RULES.md и SOURCES.md фиксируют критерии достаточности,фактически открытые URL,неизвестное и конкретные внешние пробелы без бесконечного поиска.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: собранные R1–R3: versioned case/source mapping, session memory и tri-state rules с положительными, сложными отрицательными, неполными/закрытыми интервалами и исключениями. Проверить source provenance и объяснение на всём rule output. Отсутствие источника/наблюдаемости не выдавать за отсутствие нарушения.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Поддержанное подмножество engine/source mappings проверено. | unknown: Нет применимой нормы/видимости/actors — unknown/unsupported; юридический gate не пройден. | failure: Ложный trigger/ложное not_triggered — исправить R1–R3, критерии не ослаблять.

</details>

### O2 — Compose и offline worker

Разработчик: №4. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `infra/compose.yaml`
- `infra/compose.test.yaml`
- `infra/api.Dockerfile`
- `infra/worker.Dockerfile`
- `infra/frontend.Dockerfile`
- `infra/redis.conf`
- `infra/env.example`
- `tests/performance/test_compose_isolation.py`

Критерии приёмки:

- Compose config валиден; production GPU только worker, concurrency=1/prefetch/CPU threads ограничены; Redis/PostgreSQL без внешних published ports.
- DB/media/model volumes постоянны; readiness приложения/модели разделена с container health, restart не стирает данные.
- Worker не имеет интернет-egress, но доступ к локальным DB/queue остаётся; packages/weights готовятся отдельно, runtime downloads отсутствуют.
- Образы используют общие согласованные locks K и frontend lock; secrets передаются вне Git, примеры только placeholders.
- До I инфраструктура проверяется config и явно synthetic harness; build/start всего готового приложения проверяется только после принятой интеграции, не объявляется выполненным по YAML.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: конфигурация nginx/api/worker/redis/postgres с локальными volumes и изоляцией GPU/сети.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Воспроизводимые контейнеры/volumes/изоляция готовы для I. | noDocker: Config может быть подготовлен, но реальный container/offline test остаётся blocked/not_run. | noGPU: Нет подтверждённого GPU runtime — gpu_ready=false, CPU test profile отдельно. | egress: Интернет доступен worker — isolation failure, устранить до финала. | volume: Данные пропали после restart — blocked, пользовательские volumes не удалять для исправления.

</details>

### O3 — TLS и внешний smoke

Разработчик: №4. Тип: code. Фаза: implementation.
Зависимости: O1, O2. Состояние: не сверено с Git.

Файлы:

- `infra/nginx.conf`
- `infra/scripts/tls-check.sh`
- `infra/scripts/network-smoke.sh`
- `infra/smoke_server.py`
- `tests/performance/test_network_smoke.py`

Критерии приёмки:

- TLS завершает Nginx; сертификат/hostname/expiry/chain и разрешённый внешний маршрут проверены, ключи/сертификатные секреты вне Git.
- Proxy limits соответствуют200МиБ и полному deadline; auth headers сохраняются, media/diagnostics не становятся публичными.
- Через внешний клиент проверены tiny synthetic upload→status и ошибки; до I это только обозначенный test harness, а не проверка модели/всего продукта.
- CGNAT/нет домена/сертификата/разрешённого транспорта — точный blocker; local self-signed smoke не объявляется внешним trustedHTTPS.
- Не подключать облачный transport/AI и не раскрывать видео ради smoke. Реальный API/browser повтор внешнего пути выполняется в I/B.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: настроенный Nginx/HTTPS и наблюдённый внешний upload/status smoke на явном synthetic harness.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Trusted внешний HTTPS маршрут наблюдён на synthetic data. | localOnly: Доступен только localhost — local_only, обязательный внешний критерий не пройден. | certificate: Нет валидной цепочки/имени/срока — TLS failure до исправления. | network: CGNAT/firewall/маршрут не разрешены — external_access_blocked, без самовольного туннеля. | leak: Сервис БД/Redis/media стал публичен безauth — blocked до исправления.

</details>

### O — Compose и доступ по HTTPS

Разработчик: №4. Тип: code. Фаза: integration.
Зависимости: O3. Состояние: не сверено с Git.

Файлы:

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

Критерии приёмки:

- Compose содержит nginx/api/worker/redis/postgres; GPU устройства доступны только worker, GPU concurrency=1/prefetch/CPU threads и memory limits согласованы с 16 ГБ RAM. postgres/redis не публикуют внешние порты.
- Локальные media/model/DB volumes переживают restart; restart/healthcheck и startup ordering не принимают readiness модели за readiness контейнера. Runtime analysis не скачивает пакеты/веса.
- Preflight проверяет реальную ОС/WSL2,Docker Compose,NVIDIA Container Toolkit,GPU/CUDA/Python3.11/FFmpeg и совместимость версий; отсутствующее или непроверенное фиксируется, никаких заявлений о целевом железе по названию.
- Nginx завершает TLS,проксирует защищённые API/media и frontend,согласует upload200 МиБ/timeouts. Сертификат/секреты не входят в Git, нет API ключа в bundle/URL/logs.
- network-check/tls-check наблюдают внешний HTTPS upload→status на synthetic media без настоящих видео. CGNAT/нет домена/сертификата/разрешённого транспорта — конкретный blocker внешнего доступа; local-only smoke не объявляется внешним.
- Worker не имеет доступа к интернету в runtime,но видит только необходимые локальные сервисы; firewall/network topology и offline smoke подтверждают отсутствие egress без блокировки PostgreSQL/Redis.
- infra/env.example и SETUP/NETWORK описывают реальные команды подготовки/запуска/остановки,порты,paths,healthcheck,сертификат,резервирование volumes и ограничения; контейнеры и зависимости зафиксированы совместимыми lock/digest в реализации, не проверены заранее в плане.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: собранные O1–O3: preflight, Compose isolation/volumes, Nginx/TLS и фактически наблюдённый внешний synthetic smoke. Начать O1 в первые два часа; №4 выполняет свои готовые R/O карточки последовательно без искусственных связей. До I проверка на infra harness не считается запуском всего приложения; после I внешний real-API повтор в B.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Среда/изоляция/volumes/внешний HTTPS подтверждены реальными checks. | localOnly: Только localhost — local_only; внешний обязательный критерий blocked. | missing: Нет Docker/GPU/FFmpeg/сертификата/маршрута — конкретный blocker, остальные ветки продолжаются. | failure: Public DB/Redis,worker egress,потеря volumes или TLS error — blocked до исправления.

</details>

### B — Восстановление и benchmark

Разработчик: №4. Тип: test. Фаза: verification.
Зависимости: I. Состояние: не сверено с Git.
Исходный helperFor: Z. Это существующая задача №4; новый чат не обязателен, если пользователь не разрешил дочерние чаты.

Файлы:

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

Критерии приёмки:

- Fault injection подтверждает durable PostgreSQL/outbox recovery при падении API/worker/Redis,повторной доставке и истёкшем lease: одно выполнение/один итог,без потерянного задания или ошибочного no_violation.
- Capacity race допускает одно незавершённое задание до benchmark,остальным429; deadline≤240с от приёма приводит к failed при превышении,late result не затирает failure. Не более одного waiting job разрешается только после реальной оценки общего≤240с.
- Worker offline smoke не делает интернет-запросов и сохраняет необходимые DB/queue связи; restart volumes восстанавливает jobs/media/models. Runtime downloads и облачная обработка отсутствуют.
- Внешний HTTPS smoke на synthetic media реально проверяет сертификат,маршрут,auth,upload/poll/media и ошибки. CGNAT/сертификат/маршрут без подтверждения остаются blocked; конфигурация сама по себе не считается прохождением.
- Benchmark CLI измеряет receipt→queue→decode→inference→rules→preview/evidence→response,elapsed от приёма и внешний upload→ответ; описаны warm/cold,p95,число прогонов,hardware/runtime/commit/dataset/release hashes и единицы памяти.
- Для последующего trained release заложены цели service≤240с,внешний путь≤300с,145с video warm p95≤60с и каждый≤120с,VRAM train≤6,5ГБ/inference≤3ГБ,RAM train≤10ГБ/всего сервиса≤5ГБ. Сейчас реальные latency/память/ML performance остаются not measured,synthetic timings явно отдельно.
- RECOVERY/BENCHMARK/ACCEPTANCE содержат фактические команды/exitCode/commit и blockers; отсутствие Docker/FFmpeg/CUDA/внешнего доступа не отмечается passed и не ослабляет обязательную программную/сетевую приёмку.
- Проверены fencing stale worker и capacity race; safe checkpoint/volumes recovery не требует удаления пользовательских данных или повторной публикации проекта.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: сквозные fault/offline/capacity/deadline/HTTPS проверки после I плюс готовая benchmark-команда для будущего trained release. Реальные сервисные failure/recovery тесты обязательны сейчас; latency/VRAM/RAM модели остаются не измерены до weights. Не удалять пользовательские volumes и не открывать worker internet ради прохождения проверки.
Исполнитель №4. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Fault/offline/queue/HTTPS проверки прошли; benchmark инструменты готовы. | noWeights: Настоящие latency/VRAM/RAM не измерены, synthetic цифры отдельно. | networkBlocked: Нет trusted external route — обязательный network gate blocked. | failure: Crash/retry/stale job/security regression — исправить A/O/I, затем повторить затронутые проверки.

</details>
