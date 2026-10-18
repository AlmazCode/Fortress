# Журнал разработчика №2 — Frontend

Актуально: 17 октября 2026. Ветка `codex/dev2-frontend`, GitHub-процесс без Aster. По прямому указанию пользователя №2 работает в этом чате; другой frontend-чат остановлен. Пользователь отдельно разрешил продолжить F2–F4 в собственной ветке на проверенном F1, оставив общую приёмку и интеграцию главному. Теперь F1 также принят главным в опубликованной integration.

| Task | State | Точный результат |
| --- | --- | --- |
| F1 | accepted главным | `bab9998bb094605ceadbfb42412080fa1e0f3b3f`, merge `f4ae1b5` в codex/integration |
| F2 | accepted главным | `4b2e99c6dc97f1711c87b14083d5064346174b04`, включён в финальный кандидат F |
| F3 | accepted главным | `f320802d13f5bd134ed679c18b9c15b97543f0b8`, уточнения/дополнительный тест в F |
| F4 | accepted главным | `e61ce4581900af711395befddf7ad378a5f1fadd`, wiring readiness в F |
| F | accepted software главным | `6d9075878cc6b0375ea3e338f93d3ac5ea88dd5e` + финальный код `c9317918fad3e3cb8bfccf0d76b6dc4de695ccfc` |
| U | blocked | Прямой depends I ещё blocked в опубликованном STATUS.md; настоящий test-profile API и browser journey после I не запускались |

F2/F3/F4/F приняты главным после его собственных 110 tests, typecheck и production build; подтверждение — STATUS.md на integration 6b16272 и merge c6d15d5. Независимая человеческая приёмка не заявляется. SHA отчёта определяется Git-историей после финального кода.

## Проверенный checkout и зависимости

Origin `https://github.com/AlmazCode/Fortress`, rootPath пустой. Изолированный worktree `${WORKSPACE}/.worktrees/dev2-frontend`; абсолютный путь и резервная копия исходных черновиков хранятся в локальном `dev2-github-root.json` вне Git. Исходная база `46b7bc941e64fec5649242b8290607c8f7339819`, ancestry проверена.

K `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f` прочитан, проверен собственными 55 schema tests на Python 3.11.17 и объединён обычным merge. Base F1 `307c3da68798e5468ac009fe64aba148ddd7a324`. Проверены origin/fetch/точные Git refs.

В свою ветку объединены принятые K/A1–A3 на integration `14e322a` (merge `d22a8bccc8ed384cdc74bb14a2c0a1a97a58c26f`), затем A/F1 на `c22a4a6bca4068e606989ed7a4ac70111f68fec4` (merge `2a8cf75be7d115ed542658421d7e5ae07ae2283c`). Последний merge не менял frontend или contracts; финальные frontend tests выполнены после него. Последующая integration развивается независимо; перед U требуется свежая проверка принятого I. Общие main, contracts, Python manifest/lock и чужие исходники №2 не редактировал.

## Реализовано

- F1: React/Vite/TypeScript/Tailwind/Query/Dropzone, точный npm lock. Типы и runtime validation напрямую по offline JSON-схемам K. Header-only key в памяти, safe errors, session query/fetch cancellation, GET retry максимум два повтора, один POST, bounded protected media stream до 200 МиБ. Unknown/unsupported/null versions сохраняются.
- F2: выбор MP4/MOV, ограничения перед отправкой, native input действительно disabled при недоступности. Indeterminate transfer отдельно от server processing. 202 сохраняет UUID в памяти; polling terminal stop/cleanup, явный auth resume и GET retry. Network/400/401/404/413/415/429/503 и failed не подменяются clean verdict.
- F3: authenticated Blob playback с revoke при смене job/client/unmount, игнорированием позднего Blob и видимыми ошибками. Seek использует точные elapsed source seconds по K/A3; нет frame_index/fps. 1–3 исходных JPEG, ошибки base64/browser decode, source/revision/limitations и отдельные unknown/unsupported/versions. Контракт не связывает violation с finding ID, поэтому source не приписывается событию по позиции в массиве.
- F4: readiness по status/trained/validated/test_only, локальная инструкция импорта без выдуманной команды train. Различимые безопасные ошибки, labels/status/focus/keyboard и адаптивные стили.
- F: App/main связывают model, upload, 202, polling, diagnostics, video, events и key reset. 401 очищает сеанс для повторного ввода. После network outage можно повторить GET; POST не повторяется. Производственный not_ready запрещает upload, 503 после устаревшей readiness снова блокирует его.
- Fixture mode включает только explicit frontend transport с видимым synthetic provenance. Выбранный файл не анализируется, preview отсутствует явно, JPEG — искусственный K 16×16. Network failure не включает fixtures.
- Для I/U добавлен отдельный `dev:api-test`: настоящий fetch, видимая метка, тестовый upload только при server test_only=true и trained/validated=false. Обычный production not_ready не обходится. Production runtime игнорирует test/demo flags; сборки fixture/api-test запрещены.

Изменения каждого этапа ограничены его разрешёнными файлами и этим журналом. Файлы App/main из прежних черновиков реализованы и включены в F; их первоначальная резервная копия сохранена. Старый локальный frontend/.gitignore вне точных files задачи сохранён, в candidate не добавлялся.

## Проверки и фактические исходы

Node 22.22.2 / npm 11.1.0. Все команды frontend из frontend/ (эквивалент `npm --prefix frontend ...` из Git root).

| Проверка | Exit | Результат |
| --- | --- | --- |
| `uv run --locked --group test python -X utf8 -m pytest tests/contracts/test_schemas.py -q` | 0 | 55 passed, Python 3.11.17, внешний env; shared lock не менялся |
| `npm ci --ignore-scripts --no-fund --no-audit --registry=https://registry.npmjs.org` | 0 | Чистая установка 122 пакетов; версии зависимостей после этого не менялись |
| F1 client tests | 0 | 42 passed |
| F2 component tests | 0 | 19 passed, включая native disabled regression, polling stop/abort и errors |
| F3 component tests | 0 | 14 passed на этапе F3; дополнительный missing-media seek test в F, итого 15 |
| F4 component tests | 0 | 19 passed, включая keyboard retry и details |
| `npm test` на финальном коде | 0 | **110 passed, 8 files**; App — 15 сценариев |
| `npm run typecheck` (также внутри build) | 0 | Все frontend src, не только F1 |
| `npm run build` | 0 | Production Vite build, JS около 468 кБ, CSS около 18 кБ |
| Проверка production JS по canonical JPEG/source_id/test-key/transport markers | 0 | Fixture payload/transport и тестовые ключи отсутствуют |
| `npm exec vite build -- --mode fixture` | 1, ожидаемый | Отказ test-only production build |
| `npm exec vite build -- --mode api-test` | 1, ожидаемый | Отказ test-only production build |
| `git diff --cached --check` | 0 | Перед каждым опубликованным commit |

Strict tsc отдельных F2/F3/F4 файлов запускался с `--ignoreConfig` (TypeScript 7). Первоначальный запуск без флага дал TS5112, затем выявлены и исправлены типы query options/JSX; окончательная проверка прошла. После финальных тестов менялось только оформление EOF и отчёт.

App-тесты: one POST→202→processing→done, failed/insufficient_evidence, 400/401/413/415/429/503, production missing release, outage после202 с bounded retry и восстановлением GET, reset во время неподтверждённого POST и поздний202, Blob revoke, key header/no storage, explicit synthetic mode, API test gate и запрет bypass в production.

## Наблюдение в браузере (F, авторское)

Запущен локальный Vite fixture mode на 127.0.0.1:5173. Проверены начальный экран, подключение тестового сеанса, resume synthetic job_id, processing→done, один декодируемый artificial JPEG, видимые provenance/unknown/unsupported/versions и явное отсутствие видео. Переход без видео даёт видимую ошибку, не фиктивный seek.

| Заданный viewport | Document client / scroll width | Переполнение main |
| --- | --- | --- |
| 360×800 | 345 / 345 (15px scrollbar) | 0 элементов за правой границей |
| 768×1000 | 753 / 753 | 0 |
| 1440×1000 | 1425 / 1425 | 0 |

Скриншоты каждого размера сохранены вне Git в локальном frontend-review checkpoint. Осмотрены desktop/mobile/tablet, состояние результата и focus outline. В браузере Tab перевёл focus с reset на summary, Enter раскрыл локальную инструкцию; Enter на evidence дал ожидаемое сообщение об отсутствии видео. Временный viewport override сброшен.

Браузер обнаружил одинаковые React keys у соседних UploadPanel/JobStatus: добавлены отдельные префиксы, console-error assertion в App test; чистая перезагрузка и повторный путь к результату — **0 новых error/warn logs**. HMR-история до исправления не выдаётся за чистую проверку.

Это проверка frontend на канонических artificial fixtures, не U/independent approval. Настоящий HTML video seek с VFR/rotation/nonzeroPTS, реальная авторизация/сеть/медиа с работающим backend, внешний HTTPS и ML quality здесь не сертифицируются. Реальный test-profile API в браузере пока not_run.

## Передача и запуск

Проверяемый финальный код — `c9317918fad3e3cb8bfccf0d76b6dc4de695ccfc`, ветка codex/dev2-frontend. Главный уже проверил F2/F3/F4/F и интегрировал merge c6d15d5; ожидается принятие I после M/O. После I №2 выполняет U по реальному API, не по frontend fixtures.

Команды подготовки, dev, fixture mode, API test mode, build/preview и остановки находятся в frontend/README.md. Для dev API proxy ожидает локальный backend :8000; секреты вводятся вручную и не публикуются. Остановка собственного Vite — Ctrl+C в терминале запуска. Общая main, deploy, полное обучение и реальные данные не запускались. До U полное ТЗ №2 не объявляется завершённым.

Техническая заметка завершения: после автоматического restart Vite встроенная вкладка потеряла соединение (ERR_CONNECTION_RESET); Browser Use URL policy заблокировала встроенную data: error page и последующее управление вкладкой. Локальный HTTP endpoint отдельно вернул 200. Предыдущие реальные screenshot/viewport/keyboard observations сохранены и не заменены ошибочной страницей. Последний API-test режим подтверждён компонентными тестами, а не новым browser run. Собственный временный Vite остановлен после проверки; live preview в сдаче не обещается. Команды повторного запуска — frontend/README.md.

## Свежая сверка готовности U

По указанию пользователя выполнен новый fetch. Проверена integration `6b16272fded945668b8997498faa0b2d83a541a0`: F1–F4/F уже приняты главным; I остаётся blocked по M/O, U не открыта. Все принятые результаты объединены в свою ветку merge `2d58265b0af7df9a73ff4b1307d0b58bfdd82b22`. Сравнение frontend/ и contracts/ до/после merge — пустое, исходники клиента и схемы не менялись; повторный запуск тех же frontend tests без изменения кода не выполнялся.

U не запускалась и не объявляется принятой. Следующая последовательность: закрыть M и O → главный завершает I → №2 проверяет точный SHA I и выполняет U на настоящем API. Чужие задачи, общая main и глобальный STATUS.md №2 не изменялись. Локальный frontend/.gitignore сохранён без добавления в commit.

## U: предварительная A/F проверка и целевая Windows, 18 октября

Человек разрешил предварительные A/F браузерные проверки до I, оставив финальную U blocked, затем прямо уточнил Windows как платформу сервиса и будущего обучения. Запрос Linux endpoint отозван: это был обход несовместимости текущего backend, а не требование продукта.

Свежий `git fetch origin` → exit0; integration `469b2eb841de187d8e3429dc17514254777d3bdc`, STATUS и журнал №1 подтверждают: M4/M теперь accepted, I blocked только по O runtime/external HTTPS. Принятого I SHA нет, его ancestry не подменялась проверкой A/F. Все принятые входящие commits объединены merge `d0d3ca5bda0b7e92feb0cd4945962508b4e7d6c2`. `git merge-base --is-ancestor 46b7bc941e64fec5649242b8290607c8f7339819 HEAD` →0; diff frontend/contracts относительно `45c35eb` пустой, принятые F1–F4/F не переделывались.

Настоящий Python 3.11.17 на Windows: `python -c "from backend.app.main import create_app"` → **exit1**, `ModuleNotFoundError: No module named 'fcntl'`; цепочка main.py:18 → deadlines.py:13 → tasks.py:9. Статически также обнаружены `fcntl.flock`, `SIGALRM`/`setitimer` и prefork. Это конкретная передача владельцам №1/№4: native Windows runtime должен сохранить exclusive GPU admission, deadline, durable queue и crash recovery. Подмена worker/DB/Redis или fixture API вместо исправления не выполнялась. Обучение и его Windows/CUDA готовность не проверялись №2.

Состояние U **blocked**; настоящий API и семь browser acceptance групп **not_run**, версия браузера не заявляется. Подробный sanitized отчёт — `tests/e2e/report.json`, пояснения — `frontend/ACCEPTANCE.md`. Local checkpoint и backup временных npm изменений сохранены вне Git; добавление Playwright отменено как пока неиспользуемое. Чужой untracked frontend/.gitignore сохранён. Следующий шаг: №1/№4 предоставляют проверенный запуск на Windows → №2 выполняет реальные предварительные A/F проверки; полная U после принятого I. Backend/infra/ML, общие документы и STATUS №2 не менял.

## Упрощение интерфейса по запросу пользователя — 18 октября 2026

Запрос: убрать лишнюю информацию и нелогичные тексты. Отдельная ветка `codex/frontend-copy-cleanup`, checkout `C:\Users\dajra\.codex\worktrees\frontend-review\Fortress`, base `0c8cb9f3a24c3636ea881bd58933fe846b692d65`. Проверенный commit исходников: `3c6d77dedc13f55a997fe78a4522964496ae31dc`; diff: `git diff 0c8cb9f 3c6d77d -- frontend/src`.

Удалены рекламный заголовок, повторные подписи, декоративные шаги, хлебные крошки, лишний footer и 304 строки неиспользуемых стилей. Ошибки и этапы обработки сформулированы по-русски; сведения о модели, версиях и правилах доступны в details. Ограничения файла, неполное покрытие, неподтверждённые источники, маркировка искусственных данных и предупреждение о принятом задании сохранены. Сетевой сбой не описывается как отсутствие модели; завершённое задание не называется продолжающим обработку. Производственный gate, wire contracts, polling, auth и медиа-потоки не ослаблялись.

Проверки на этом коде: `npm test` — exit 0, 109 passed / 8 files; `npm run build` (включая `tsc --noEmit`) — exit 0; `git diff --cached --check` — exit 0. Удалён один устаревший тест повторного demo-предупреждения внутри ApiKeyForm; проверка явного demo-режима остаётся в App tests.

Браузер: обычный начальный экран и fixture connect/resume/processing/done, доступность details с источниками и версиями, ноль error/warn logs. На 360/768/1440 px горизонтального переполнения нет; начало upload на 360 px — около 488 px вместо прежних 882 px. Скриншоты сохранены вне Git. Временный viewport сброшен. Предпросмотр обычного UI: http://127.0.0.1:5198, команда `npm run dev -- --host 127.0.0.1 --port 5198 --strictPort`; остановка — Ctrl+C. Это проверка интерфейса, статус U и готовность настоящего API не изменены. Публикация и изменения main не выполнялись.
## Палитра Forte.kz — 18 октября 2026

По запросу пользователя применены цвета действующего официального сайта https://forte.kz/; значения прочитаны из computed styles в браузере: основной #A31551, тёмный #4A0221, коралловый #FC9385, светлый фон #F7F6F6, текст #1D1D1D и вторичный #6C6C6C. Добавлены CSS-переменные; заменены цвета навигации, кнопок, ссылок, focus, загрузки, панелей и медиа. Различимые success/warning/error состояния сохранены. Менялся только frontend/src/styles.css.

Ветка codex/frontend-copy-cleanup, base 9190789, проверенный commit 01aa21ffe39440bbd84a6e8971ca5ec4449acf98; diff: git diff 9190789 01aa21f -- frontend/src/styles.css. npm run build (включая tsc --noEmit) — exit 0; git diff --cached --check — exit 0. Новые tests для изменения цветов не добавлялись. Проверка в браузере подтвердила точные primary/sidebar/page/text цвета и 0 error/warn logs. Контраст primary/white 7.54, muted/white 5.25, coral/sidebar 7.30. Скриншот fortress-forte-palette.jpg сохранён вне Git; предпросмотр на http://127.0.0.1:5198 обновлён. Layout, тексты, API и поведение не менялись; main и публикация не затронуты.
## Очередь видео и обратная связь — 18 октября 2026

По прямому запросу пользователя добавлены локальная очередь до 20 файлов, выбор нескольких MP4/MOV, drag/drop и вставка из буфера. Ветка codex/frontend-copy-cleanup, checkout C:\Users\dajra\.codex\worktrees\frontend-review\Fortress; base e636e2f96d14ba372c359c084d5991bd4961020e, проверенный commit кода aa4750d7fcb44632a34c4e480350ff34c821b048. Diff: git diff e636e2f96d14ba372c359c084d5991bd4961020e aa4750d -- frontend.

Один активный POST/job; следующий файл отправляется после терминального ответа. Пауза удерживает новые отправки и не отменяет принятое задание. Удаление ожидающих, сохранение очереди при первоначальном вводе ключа, очистка/abort при reset/unmount, защита от позднего 202 и повторного POST, удержание очереди при 429/503/потере связи/неизвестном приёме проверены. При просмотре результата другого файла обработка очереди продолжается; возврат к внешнему job_id сериализован с загрузками. Готовность модели можно обновить без потери ожидающих файлов.

UI: общий объём, счётчики файлов/waiting/active/done/errors, нативные индикаторы передачи и анализа, измеримый processed_sec только для текущего job_id, время обработки, список файлов и отдельные результаты. Палитра Forte сохранена, progress тоже бордовый. Компактное добавление после первого выбора освобождает место для очереди. Ключ, форматы public API и backend admission не менялись; файлы не сохраняются в browser storage. Границы локальной очереди и команды запуска описаны в frontend/README.md.

Проверки неизменённого кода: npm test — exit 0, 123 passed / 10 files; npm run build (включая tsc --noEmit) — exit 0; production bundle scan по fixture/source_id/test-key/transport markers — exit 0, markers=[]; git diff --cached --check — exit 0. Новые тесты включают StrictMode, последовательность done/failed, pause/continue, uncertain POST, 429/manual retry, потерю GET, abort, reset/late 202, лимит и удаление, открытие принятого задания, выбор до ключа, независимые результаты, readiness refresh и отсутствие выдуманного процента.

Браузер: три искусственные файловые заглушки 2/4/8 МиБ добавлены до ввода ключа; после подключения они сохранены. Проверены start/pause/continue, три разных job_id и завершение 3/3, затем открытие второго результата. В fixture mode эти байты не декодируются и не анализируются: это только проверка интерфейса. Production API, настоящее видео и ML validation здесь не запускались; U не переопределяется. На 360/768/1440 px clientWidth=scrollWidth (345/753/1425), клавиатурный focus видим, error/warn logs=0. Скриншоты fortress-video-queue-desktop.jpg и fortress-video-queue-mobile.jpg сохранены вне Git; временный viewport сброшен. Предпросмотр обычного UI http://127.0.0.1:5198, явного demo http://127.0.0.1:5197; остановка Vite — Ctrl+C в соответствующем терминале. Main/push/deploy не выполнялись.