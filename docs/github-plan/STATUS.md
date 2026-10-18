> Историческая запись предыдущих веток. Актуальные запуск и состояние: [README](../../README.md) и [PROJECT_STATUS](../PROJECT_STATUS.md). Старые административные инструкции не являются новым поручением.

# Сводка проекта — ведёт только главный

Интеграционная ветка: `codex/integration`. Последние проверенные интеграции: исправление A `c46a2c0`, F merge `c6d15d5`, D1/D2, D3–D/M1–M3 до merge `30c9df6`, M4/M с исправлением `c68ae81` и отчётом `21de016` включены merge `894e869`; код инфраструктуры №4 `1137423` + отчёт `8aee9d1` включены merge `3e19b04`, TLS diagnostic fix `d5eb6ef` + отчёт `1a7cbd9` включены merge `6d45879`; O2/O3/O остаются blocked по runtime/HTTPS (K, все A1–A5 и F1–F4 входят по ancestry). Общая main не изменяется. Приёмка ниже — фактическая проверка главным №1, не независимая человеческая приёмка. Приёмка этапов относится только к указанному объёму; legal/ML/GPU/external HTTPS gates описаны отдельно ниже.

Принятые commits: K — `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`; A1 — `a84cce5e19c8b5a96286473aa9283c2c6b3a1194`. Команды, покрытие и ограничения — [журнал №1](status/DEV-1.md).

- [x] O1 — Среда и внешний маршрут · №4 · accepted (инвентарь; среда не ready)
- [x] K — Контракт API и данных · №1 · accepted
- [x] A1 — БД и состояние заданий · №1 · accepted
- [x] A2 — Приём и проверка видео · №1 · accepted
- [x] A3 — Авторизация и медиа · №1 · accepted
- [x] A4 — Outbox и один worker · №1 · accepted
- [x] A5 — Дедлайны и сбои backend · №1 · accepted
- [x] A — API и надёжная очередь · №1 · accepted
- [x] F1 — Клиент API и ключ · №2 · accepted (bab9998, merge f4ae1b5)
- [x] F2 — Загрузка и статусы · №2 · accepted (4b2e99c, итоговый код c931791)
- [x] F3 — Видео и доказательства · №2 · accepted (f320802, итоговый код c931791)
- [x] F4 — Ошибки и доступность UI · №2 · accepted (e61ce45, итоговый код c931791)
- [x] F — Интерфейс анализа · №2 · accepted software (c931791, merge c6d15d5); настоящий API/browser journey — I/U
- [x] D1 — Аудит данных и среды · №3 · accepted (536fe7a, merge 8dd2da1)
- [x] D2 — Классы и инструкция разметки · №3 · accepted draft (b496127, merge 47787cb); human review/final taxonomy не заявлены
- [x] D3 — Импорт и split без утечки · №3 · accepted (54493fc, merge d74e06a); прежний holdout defect закрыт
- [x] D4 — Кадры и клипы по PTS · №3 · accepted software (8b263be, merge 6434cf8)
- [x] D5 — Разметка объектов и событий · №3 · accepted software (4ad53e3, merge 1c53619)
- [x] D — Данные и preflight · №3 · accepted tools (97bb8cd, merge f99e501); real data_ready=false
- [x] M1 — Preprocessing и кэш · №3 · accepted software (145e33e, merge 6133bd1)
- [x] M2 — GRU и CPU train/resume · №3 · accepted software (e30bfb6 + follow-up 6c9f4c2, merges 3537909/30c9df6)
- [x] M3 — Оценка и экспорт пакета · №3 · accepted software (a23f946 + e7db22f, merge 30c9df6)
- [x] M4 — Loader и inference adapter · №3 · accepted software (67ec1de + c68ae81, merge 894e869); .video defect закрыт
- [x] M — ML CLI и загрузка release · №3 · accepted software (85e5b21 + c68ae81, report 21de016, merge 894e869); tiny CPU, production not_ready
- [x] R1 — Кейсы и нормативные источники · №4 · accepted software / missingSource; legal gate unknown
- [x] R2 — Память ролика и связей · №4 · accepted
- [x] R3 — Правила и сложные примеры · №4 · accepted software; все production cases unsupported
- [x] R — Правила и источники · №4 · accepted software (9569729); legal gate unknown
- [ ] O2 — Compose и offline worker · №4 · code integrated (1137423, merge 3e19b04); blocked runtime/offline/volumes/GPU, COPY contracts исправлен
- [ ] O3 — TLS и внешний smoke · №4 · blocked (нет подтверждённого внешнего HTTPS)
- [ ] O — Compose и доступ по HTTPS · №4 · blocked (O2/O3)
- [ ] I — Интеграция без весов · №1 · blocked (O runtime/external HTTPS; A/F/M/R software приняты)
- [ ] U — Браузерная приёмка · №2 · unverified
- [ ] E — Передача ML-инструментов · №3 · материалы 8d8a476 рассмотрены; blocked до принятого I
- [ ] B — Восстановление и benchmark · №4 · tooling integrated (1137423); actual full-stack acceptance blocked до I
- [ ] Z — Финальная сдача · №1 · blocked (I → U/E/B)

## Актуальное review 18 октября 2026: новые SHA №3/№4

Результаты ниже заменяют старые возвраты D3/M4 .video/COPY contracts. История дальше относится к прежним SHA. Проверки выполнены главным в собственном checkout; это не человеческая/ML/production приёмка.

### №4: новый TLS diagnostic fix принят, runtime не закрыт

Fresh fetch: code **d5eb6eff26ffd8039939270b99c8ec6dec12a7e1**, report/head **1a7cbd985c631a9d491bde64a9307393f683b2e5**; включены merge **6d45879ffb1826ada886429ba9cb9caf8ce2eb3d** после проверки. `preflight --network-only`/`tls-check.sh` теперь прекращает работу после repository guard и network/TLS probes, не запускает OS/WSL/Docker/GPU inventory и не смешивает её blockers с TLS. Full preflight, строгая проверка chain/hostname и `external_access_verified=false` сохранены. Дельта6 путей относится только к tooling/tests/operations/DEV-4; backend/ML/contracts/locks неизменны.

Главный: `FORTRESS_TEST_OPENSSL=/usr/bin/openssl .venv/bin/python -m pytest tests/performance/test_preflight_report.py tests/performance/test_https.py tests/performance/test_network_smoke.py -q --tb=short` → **exit0, 44 passed, 1 skipped, 7 subtests passed, 12.15s**. Skip — нет PowerShell7 на Linux. Отдельный настоящий CLI с временным loopback TLS: нет URL→exit2/not_run; process-local trusted CA→exit0/ok; untrusted chain и wrong hostname→exit2/failed. Все reports содержат только network blockers и не заявляют external access. Проверены14 Bash blocks RELEASE.md (`bash -n`), JSON, реальные OpenSSL public-key/SHA pipelines: одинаковая пара совпадает, другой ключ отличается; secrets/CA не устанавливались и не публиковались.

Docker на Linux главного по-прежнему **exit1 permission denied**. Теперь read-only уточнено: default context→unix:///var/run/docker.sock, socket `root:docker`/0660, текущий процесс не состоит в `docker`. Это отличается от отсутствующего engine pipe на Windows №4. Permissions/groups/системные настройки не менялись. Внешний hostname/route/trusted TLS и внешний observer не предоставлены, поэтому внешняя certificate failure не утверждается.

**O2/O3/O остаются blocked**: до I нужны настоящий отдельный synthetic Compose harness build/start, DB/Redis при запрещённом worker egress, persistent volumes/restart, target GPU/CUDA evidence и trusted HTTPS/upload/status извне. Build/start собранного приложения и его HTTP/browser повтор относятся к I/B после принятия prerequisites. Новый фикс улучшает диагностику; Docker runtime и внешний доступ им не подтверждены. M4/M приняты, I всё ещё ждёт O.

### №3: M4/M приняты после исправления штатного .video

Свежий fetch получил code **c68ae819d38cd14b97921c9c76ed1a4b92d89cc8**, report/head **21de016d801a6b5d8116106a02ab34b848047e94**. После проверки включены обычным merge **894e869b7b02deceb0a3978e086750d828c380e0**. Исправление выбирает фактический контейнер по содержимому во всех трёх проходах probe/index/decode; demuxer whitelist устанавливается до чтения заголовков, file-only protocols, hash/PTS и decode budgets сохранены. Backend/contracts/locks не менялись.

Собственная проверка главного на Linux: `.venv/bin/python -m pytest tests/contracts/test_schemas.py tests/ml -q --tb=short` → **exit0, 273 passed, no skips, 87.46s**. Набор включает реальные LocalStorage.spool/VideoValidator/promote, MP4 и MOV rotation90/VFR/nonzeroPTS, CLI на .video, запрет ffconcat, corrupt/hash/budget regressions, tiny CPU CLI train/resume/export/import/rollback и holdout protection. Windows-адаптеры в Linux не активируются.

Отдельно повторён прежний собственный сценарий: новый FFmpeg H.264 MP4 → штатный LocalStorage.promote → VideoValidator → TimelineAdapter и subprocess `ml.cli infer`. Оба расширения теперь проходят, CLI exit0; intervals/scores/masks совпадают (path-derived video/scene IDs нормализованы только для сравнения), source SHA и stored bytes/mtime сохраняются. Coverage=none, findings=[], test-only package отвергается production adapter, manager readiness=not_ready. Старый P1 закрыт, новых воспроизводимых дефектов в проверенном изменении не найдено.

M4/M приняты в software объёме. E-документы включены как подготовка; **E blocked до принятого I SHA**. I ещё ждёт O: фактический runtime/offline/volumes/GPU и внешний HTTPS. Полное обучение/реальное ML качество не проверялись и остаются отложенными; отсутствие production release сохраняет model_not_ready.

### Принятые D3–D и M1–M3

D3 **54493fcd10b1824356f82df3f6bbbfadc1ea5ffc**: 55 targeted tests passed. Собственный CLI import четырёх новых FFV1/MKV → split seed17 с final → re-split без final flag при (seed,dev_fraction)=(17,.2),(99,.7),(321,0) сохранил один final во всех трёх случаях. Training/calibration selectors его не возвращают; попытка выбрать другой final → exit2, output отсутствует, originals/hash/mtime сохранены. Старый P1 d0b9704 **закрыт**.

Далее последовательно проверены и объединены D4 (14 tests), D5 (40), D/data CLI с затронутыми regressions (51), M1 (28), M2 (15), M3 вместе с M2 lineage fix (38). Точные SHA и commands — DEV-1. Это tools ready и tiny CPU software evidence; реальные labels/weights/ML validation не заявляются.

### №4: код исправлен и интегрирован, runtime ещё blocked

Код **1137423fc1de54b3d6cc5b77c2c14010e72d2ecf**, отчёт **8aee9d1**, merge **3e19b04256d193321c243f8d3fafaf70efd7a88c**. Свежий report **6d7e6789f70df4445be19e758a209d9b95013ce0** рассмотрен и объединён отдельным documentation merge **f950594e7b1b4cdcf77eb19817289b30103a4e81**: только DEV-4/ACCEPTANCE, исполняемый код идентичен 1137423. Повторять неизменённые tests не требовалось. Проверена дельта 27 путей: вся в объединённой области №4. CLI/env/migration/PID config и COPY contracts замечания закрыты. Воспроизведён точный frontend COPY layout с sibling contracts и существующим locked node_modules: `npm run build` → exit0, typecheck + 173 modules. Это build inputs, не Docker image build.

`FORTRESS_COMPOSE_CLI=/usr/libexec/docker/cli-plugins/docker-compose FORTRESS_TEST_OPENSSL=/usr/bin/openssl .venv/bin/python -m pytest tests/performance tests/rules -q --tb=short` → **77 passed, 1 skipped, 50 subtests passed, 12.36s**. Skip — PowerShell7 на Linux. Настоящий Compose config/loopback TLS/RSS process checks пройдены; это не runtime acceptance. Shell syntax и smoke.sh --help → exit0.

Дополнительно новый client №4 проверен против настоящих uvicorn/FastAPI + временных PostgreSQL/Redis: production auth401/unknown-job404/model503; explicit synthetic upload→outbox→Celery test worker→done→original SHA/preview/JPEG. **2 passed, 4.97s**. Это native local A/software checks с FixtureRunner, не integrated ML или Compose/внешний HTTPS.

**Оставшиеся O gates:** `docker version` → exit1 `permission denied /var/run/docker.sock`; image build/start, worker DB/Redis connectivity при запрещённом egress, persistence media/models/DB после restart ещё not_run. GPU/CUDA на target hardware не проверены, текущий lock CPU-only. Не заданы/не подтверждены доверенные external hostname/cert chain/route и независимый внешний upload/status observer. Требуется фактическое evidence этих проверок №4; WSL/VM setup, permissions и deploy этим review не изменялись. Код O/B включён для проверки, но **O2/O3/O/B не accepted** и prerequisites I не открыты.

### Исправление A/K 404 и оставшийся I

Собственный commit **c46a2c0** заменяет `not_found` на `job_not_found` для отсутствующего задания и generic API404, на `media_not_found` для отсутствующего original/evidence существующего задания. Новые regressions сначала дали **2 failed** по реальному HTTP/body, после исправления весь contracts/API набор → **118 passed, no skips, 35.70s**. Проверены random/malformed ID, public/UI/media/preview/frame, удалённый original, body schema, cache/private headers и отсутствие утечки key/path. Production без release по-прежнему **503 model_not_ready**, без создания job/outbox.

**I остаётся blocked:** M4/M теперь приняты; требуется фактически принятый O runtime/external HTTPS. Отсутствие будущего trained release само по себе I не блокирует; full training отложено. После закрытия O №1 выполняет I, затем №2/№3/№4 U/E/B и №1 Z. Общая main не изменяется, force-push/deploy/новые чаты/сабагенты/Aster не используются.

## Исторические результаты (актуальные статусы выше)

### История сверки до публикации c68ae81

Свежий `git fetch origin` → exit0. №3 остаётся **4513993fd8679d93e39424aa3d63178c84e15fb4**: нового M4/M исправления `.video` нет, прежнее воспроизведение относится к текущему коду. №4 опубликовал **f2e40c6750d4794ae6817c248a45e9b3380f9401** — только5 документов, executable code/тесты/locks не изменены. Подготовлен новый [RELEASE.md](../operations/RELEASE.md); исправление 404 отмечено закрытым. Авторский свежий runtime report: Windows engine pipe отсутствует, host NVIDIA query не подтверждает container CUDA; Docker/worker/volumes/GPU/external HTTPS всё ещё not_run. Доступ к другому ПК по журналу №4 отложен пользователем; новых подключений не предпринималось.

Главный прочитал runbook/DEV-4/ACCEPTANCE, проверил **11 Bash blocks (`bash -n`), 5 Python snippets (`ast.parse`)**, relative links, JSON и production/harness Compose config — exit0. Документация включена merge **2495a6d1114e913f8d36ae40cb6a3ac42f6f8fc0**; это подготовка инструкции, не приёмка O или публикация Release/deploy. Повторный Linux `docker version` → exit1 `permission denied /var/run/docker.sock`. Неизменённые application tests не повторялись. **M4/M, O и I остаются blocked** по тем же точно указанным ниже условиям.

### История M4: отказ до c68ae81 (дефект закрыт)

Проверены M4 **67ec1deb592fbfd8b80437ae5ffeda465aba6adf** и итоговый M **85e5b2162d86e95d831ce9fb7ef2c7578b9ee92d** на опубликованном head **7aab330**. Повторный fetch получил **4513993fd8679d93e39424aa3d63178c84e15fb4**: только DEV-3/HANDOFF, код M и holdout не изменён; свежая передача прочитана. Все **269 tests passed, no skips, 83.43s** воспроизведены главным. Отдельный `ml.cli smoke` → exit0: три synthetic источника, 2 optimizer steps с resume, dev calibration/final evaluation, FP32 model.pt=6,385,243 bytes, data/trained/validated/production=false. Actual CLI train на final и thresholds на final → exit1 без output. Holdout исправлен также на границах trainer/calibration.

**Дефект прежних SHA, исправлен в c68ae81:** `backend/app/storage.py:87` штатно сохраняет upload как `<32hex>.video`. `TimelineAdapter.infer` (`ml/inference.py:51–55`) передаёт этот путь data importer; `ml/data/manifest.py:87–91` определяет контейнер только по suffix и отвергает `.video` до decode. В `ml/data/pts_index.py` также есть suffix→format lookup; исправить только первый whitelist недостаточно.

Главный создал настоящий H.264 MP4 64×48/10fps/1s, сохранил через **LocalStorage.promote**, проверил **VideoValidator** и неизменность байтов/SHA. Inference того же файла под `.mp4` → exit0/coverage=none; под штатным `.video` → `InferenceFailed: decode_unsupported_or_corrupt`. На финальном M это повторено именно через CLI → exit1, timeline output не создан. Проблема затронет обычные accepted uploads при подключении K TimelineProvider; это не плохое видео и не отсутствие trained release.

Минимальный повтор на прежнем коде №3 (до c68ae81) (новая временная папка, только synthetic):

```sh
review_dir=$(mktemp -d)
python -m ml.cli smoke --output-dir "$review_dir/smoke"
ffmpeg -v error -nostdin -f lavfi -i testsrc2=size=64x48:rate=10:duration=1 -c:v libx264 -threads 1 -pix_fmt yuv420p "$review_dir/synthetic.mp4"
cp "$review_dir/synthetic.mp4" "$review_dir/0123456789abcdef0123456789abcdef.video"
python -m ml.cli infer --package "$review_dir/smoke/imported" --allow-test --video "$review_dir/synthetic.mp4" --output "$review_dir/normal.json"
python -m ml.cli infer --package "$review_dir/smoke/imported" --allow-test --video "$review_dir/0123456789abcdef0123456789abcdef.video" --output "$review_dir/stored.json"
```

Последние exit codes: **0 и 1**. Ожидается успешный decode обоих одинаковых файлов с сохранением исходных PTS/hash и unknown coverage. №3: согласовать безопасное определение фактического контейнера для backend-owned paths на всём probe/index/decode пути; сохранить local-only protocols/limits/hash checks, добавить regression с настоящим LocalStorage/VideoValidator и новым SHA. Backend storage/контракты для обхода не ослаблять. На момент этого старого review M4/M **не были приняты и интегрированы**: временные review merges отменены, все авторские commits сохранены. Материалы E `8d8a476` рассмотрены как подготовка; E ждёт I.

A2 принят и включён в `codex/integration`: `df5dae07b4683afff88bdd06bfbf5b34bd7cc382` (19 проверок).

A3 принят в `codex/integration`: `6f7f5bf689440640bdc205642aefe7bf07a4d283` (8 проверок).

A4 принят в `codex/integration`: `61a69ce8edc254b4d62ab0652eb8f89df146e434` (7 проверок).

A5 и исправленный A1 приняты в `codex/integration`: `4e5d9b09b292af03f27991b32cadf9aae2af64d6`. Ветка frontend `551454a` содержит только прежний отчёт о блокировке по K; код frontend отсутствует, K теперь доступен.

A принят в `codex/integration`: `043eeb6d125f3b77d71b74de3b56c6a1cee91e70`. **116 tests passed, no skips**. Общая программная сдача пока blocked по недостающим F/M/R/O и внешней инфраструктуре; обученная модель также отсутствует по плану.

F1 `bab9998bb094605ceadbfb42412080fa1e0f3b3f` принят главным после review и собственных checks, merge `f4ae1b5` в integration. F2/F3/F4 открыты.

## Результаты приёмки D1/O1/R и открытые вопросы

- D1 `536fe7af06cadb4ff9513da1bf8dcafb6e6198e6`, отчёт `9aa9dda`, интегрированы merge `8dd2da1`. Главный: 9 тестов + настоящий CPU weights=None feature smoke `[1,576]`. training_ready=false; частный inventory автора из 42 видео/2621 изображения не пересканировался на этом хосте.
- O1 `12acfed` с исправлениями в `9569729` и R1–R3/R `9569729` интегрированы merge `df1f398d14367fddc5621f613280115f8df19ff3`. Главный: 32 passed, 29 subtests, 1 skipped (нет PowerShell 7); фактический Linux preflight выполнен. Это подтверждение инвентаря/программной логики, не работоспособности Docker/GPU/HTTPS.
- R принят по разрешённым outcomes missingSource/unknown: C01–C15 сохраняются, все production cases unsupported, verified normative sources нет. Юридическая приёмка не пройдена. №3 сообщает доступность исходного case локально; №4 нужен разрешённый доступ к нему/применимым источникам для последующей предметной проверки.

### История замечаний O2/O3 для кандидата 5834064

Кандидат `5834064393dc16de066254c5d10b97826ebadf6a` **не интегрирован и не принят**. Следующие замечания проверены по его точному коду и принятому A:

1. `infra/api.Dockerfile:31` ссылается на отсутствующий `backend.app.main:app`. Поддерживается `python -m backend.app.main api --host 0.0.0.0 --port 8000` либо uvicorn `backend.app.main:create_app --factory --no-access-log`.
2. `infra/compose.yaml:67,99` и `infra/worker.Dockerfile:34` ссылаются на отсутствующий `backend.app.celery_app:celery_app`. Поддерживается `python -m backend.app.main worker`; он запускает принятый prefork, concurrency=1. `--pool=solo` не соответствует проверенному production hard-timeout механизму.
3. `inspect ping` healthcheck несовместим с `worker_enable_remote_control=False`; указанное destination также не совпадает с явным worker hostname. Нужен проверяемый health mechanism без ложного unhealthy.
4. Общая Settings сейчас требует `FORTRESS_API_KEY`, `DATABASE_URL`, `REDIS_URL` для CLI; worker environment не передаёт ключ. Согласовать worker-only settings с №1 либо полный контракт env до runtime test. Запуск миграций тоже должен быть явным до API/worker.
5. `infra/.gitattributes` отсутствует в files всех задач №4; требуется убрать внеплановый путь либо отдельное указание человека о scope. Правки ранее выполненных O1/R в том же commit допустимо описать как их исправления, но не считать весь O2 принятым по ним.
6. Docker daemon, build/start, volume restart и worker egress здесь не подтверждены. Внешний hostname/certificate/incoming route не заданы; trusted внешний HTTPS upload/status не выполнен. CPU torch lock не подтверждает target CUDA.

### Проверка новых кандидатов 17 октября 2026

- F2/F3/F4/F: код `c9317918fad3e3cb8bfccf0d76b6dc4de695ccfc`, отчёт `96f037c`, обычный merge `c6d15d5feade48abfcde81207c818510344445a9`. Главный проверил фактическую дельту 24 файлов, выполнил **110 tests passed**, typecheck и production build. Оба test-mode build ожидаемо отвергнуты; canonical JPEG и тестовые ключи/fixture transport отсутствуют в production bundle. Авторское наблюдение 360/768/1440 px и клавиатуры рассмотрено по отчёту; главным браузер повторно не запускался. Реальный API/video seek остаётся I/U, обучение и качество модели не подтверждаются.
- D2: код `b4961272723cefec463d45ccb49d041afd52150b`, отчёт `c485788`, merge `47787cbf295a8b0302cba32c35dab11aa49f28c8`. Главный проверил 7 файлов и получил **72 passed** (17 taxonomy + 55 contracts), обе taxonomy CLI прошли. Приняты определения draft: 9 объектов, 14 действий, 6 состояний; официальные 25 ID и человеческая приёмка отсутствуют. D3 готова по принятому K; D4 ждёт принятого D3, D5 — D2/D4.

### История замечаний O2/O3 для 2e368f6

Код `1a1b091f091611ff56ff523daf1aebf137e343ee`, отчёт `2e368f6` просмотрены, но **не интегрированы и не приняты**. Prefork и отказ от remote-control ping исправлены. Настоящие Compose config/private-CA loopback TLS описаны автором; это не внешний HTTPS и не запуск приложения, главный их повторно не выполнял.

1. `infra/compose.yaml:35,69` и CMD обоих Dockerfiles требуют exports через `FORTRESS_API_APP/FORTRESS_WORKER_APP`, которых принятый A не предоставляет. A `043eeb6` уже опубликован: использовать `python -m backend.app.main api --host 0.0.0.0 --port 8000` и `python -m backend.app.main worker`. Для прямого uvicorn есть `backend.app.main:create_app --factory`; Celery instance export отсутствует. Произвольная строка env и успешный config с `test_only.*` этого не проверяют. После выбора worker CLI согласовать healthcheck с фактическим PID: текущий CLI не создаёт `/tmp/fortress-worker.pid`.
2. `infra/compose.yaml:70–82` по-прежнему не передаёт worker `FORTRESS_API_KEY`, обязательный для текущей `Settings.from_env`. Передавать действующий контракт env либо согласовать изменение Settings с №1. До API/worker нужен явный `python -m backend.app.main migrate` с тем же env; в инструкции и startup sequence его нет.
3. `infra/frontend.Dockerfile:3–8` копирует только frontend, хотя `src/api/types.ts` и fixture module импортируют `../../../contracts/*.json`. Главный воспроизвёл набор COPY-файлов во временной папке с уже установленными dependencies: `npm run build` → **exit 1, TS2307** для job/diagnostics/events/fixtures. Это реальная проверка build inputs, не Docker build. В build stage нужны контракты в разрешаемом относительном пути (при `/frontend` — `/contracts`) и повторный build.
4. `infra/.gitattributes` всё ещё вне files задач №4. Убрать этот внеплановый путь либо получить актуальное указание человека об области.
5. Docker build/start, worker DB/Redis + egress, persistence restart, GPU/CUDA и доверенный внешний HTTPS всё ещё не подтверждены. Закрывать O2/O3/O по config или synthetic harness нельзя.

### История проверки O2/O3: 3cee753 / b679dc7 (заменена review 18 октября выше)

Код `3cee7531746927cd035b4c4e51e522f150990dbd`, отчёт `b679dc7` проверены главным поверх принятой integration через временный merge без commit. Вся дельта 19 файлов входит в область №4. Кандидат **пока не интегрирован и не принят**: после проверки временный merge отменён, исходный candidate сохранён в Git.

- Закрыты предыдущие замечания по CLI, worker env, миграциям, PID health и внеплановому `.gitattributes`. API/worker используют опубликованный `python -m backend.app.main`; документация задаёт DB/Redis → migrate → остальные сервисы. Health читает `/proc/1/cmdline` при `NOSETPS=1`; его работа в контейнере ещё не проверена.
- Главный запустил **настоящий Compose v5.5.1 config** и **настоящие loopback HTTP/TLS** через tests на неизменённом кандидате: **53 passed, 1 skipped, 34 subtests passed**. Включены rules/preflight regressions; skip — отсутствующий PowerShell 7. Local private CA и rejection неправильного hostname/недоверенной цепочки не подтверждают внешний маршрут.
- `infra/frontend.Dockerfile` не изменён: по-прежнему не копирует `contracts/`, предыдущий воспроизведённый TS2307 остаётся открытым. Нужен COPY contracts в `/contracts` при build workdir `/frontend`, затем проверка сборки с окончательным frontend F.
- На текущем Linux `docker compose version` → 0, но `docker version --format '{{json .Server.Version}}'` → **1, permission denied /var/run/docker.sock**. Проверки build/start/worker egress/volumes/GPU не выполнены. На Windows №4 installer также остановлен системным prerequisite; это отдельный хост и отдельное ограничение, не Linux-ошибка.
- Доверенный внешний HTTPS не подтверждён. O2/O3/O и I не закрываются по config/local TLS.

Frontend `45c35eb` содержит только синхронизацию журнала с уже принятой F; объединён merge `452800fbdec0bb8821ec6547fe118566c8c0b3de`. Исходники не меняются. На момент этой проверки ML-ветка оставалась `c485788`; более новый D3 рассмотрен ниже.

### История проверки D3: d0b9704 / отчёт 0e9bebc (дефект закрыт в 54493fc)

Получен точный код `d0b9704b005e85675191baf0c0737b5d6da8cc49`, опубликованный head `0e9bebc`. D1 и D2 уже приняты; D3 **пока не принят и не интегрирован**. Главный прочитал 10 файлов реализации/тестов и журнал №3, проверил scope через временный merge (11 разрешённых путей), выполнил `.venv/bin/python -m pytest tests/contracts/test_schemas.py tests/ml -q` → **0, 129 passed in 3.95s, no skips**. Это 55 K + 9 D1 + 17 D2 + 48 D3. Tests проверяют реальные tiny decode/PTS/rotation, ZIP rejection/rollback, dedup и grouped splits; реальные пользовательские данные не обрабатывались.

**[P1] Финальная выборка теряется при повторном split.** `ml/data/splits.py:66–95` берёт final только из нового аргумента, игнорирует предыдущие assignments и заново распределяет все группы. CLI `:133–142` принимает уже разделённый bundle, а пропущенный `--final-video-id` превращается в пустой список. Уже отмеченный `independent_test` после обычного повторного запуска становится train или dev; `records_for(..., purpose="training")` действительно возвращает прежний final. Это нарушает критерий D3 №4, хотя `training_ready=false` остаётся честным: этот флаг не препятствует выдаче записей через selector.

Воспроизведено главным через **реальные CLI** на четырёх новых tiny synthetic FFV1/MKV 32×24, без правок исходников:

```sh
python -m ml.data.manifest --config synthetic-config.yaml --output import.json
python -m ml.data.splits --input import.json --output first.json --seed 17 --final-video-id video-bab7f71334d5d9cea2d38557
python -m ml.data.splits --input first.json --output second.json --seed 17
```

Все три процесса → exit 0. До повторного split: train=2/dev=1/final=1. После: train=3/dev=1/final=0; указанный video ID перешёл `independent_test → train`, training selector включает его. SHA/mtime всех четырёх originals сохранены. Полный локальный report оставлен вне Git; это только software reproduction, обучение не запускалось.

Следующее действие №3: сохранить ранее зарезервированные final-группы при re-split либо явно отклонять вход с существующим split до записи output. Нельзя молча возвращать прежний final в train/dev; изменение final selection должно быть явно контролируемым. Добавить регрессионные API/CLI проверки повторного split без повторного флага, с другим seed/final selection и связанными duplicate/source groups; доказать, что прежний final не попадает ни в training, ни в threshold calibration. Затем опубликовать новый точный SHA для повторной проверки. Временный merge главного отменён, candidate сохранён в Git. D4 ещё не открыта.

M/O остаются незакрытыми prerequisites I. Z недоступна до I и U/E/B. Прямые сообщения другим чатам не отправлялись; эта сводка — передача замечаний через разрешённый GitHub-процесс.
