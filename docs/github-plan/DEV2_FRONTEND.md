# Разработчик №2 — Frontend

Свои задачи: F1, F2, F3, F4, F, U.

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

### F1 — Клиент API и ключ

Разработчик: №2. Тип: code. Фаза: implementation.
Зависимости: K. Состояние: не сверено с Git.

Файлы:

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ApiKeyForm.tsx`
- `frontend/src/fixtures/contract-fixtures.ts`
- `frontend/src/api/client.test.ts`

Критерии приёмки:

- Выбранный React/Vite/TypeScript/Tailwind/Query/Dropzone стек зафиксирован package-lock; typecheck/component test commands работают.
- Ключ только в памяти вкладки, запросы через X-API-Key; нет секрета в URL/storage/bundle/logs. Reset отменяет query/fetch.
- Public types соответствуют K; protected diagnostics отдельны, unknown не теряется при преобразовании.
- Fixtures включаются только explicit test/demo config с видимым provenance. Сетевая ошибка production не включает fixtures.
- Abort до принятия не выдаёт done; разрыв после202 не отменяет server job. Retry polling не повторяет POST автоматически.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: TypeScript/Vite scaffold, typed Query client и lifecycle ключа с отдельным test transport.
Исполнитель №2. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Общий client/types готовы для F2/F3/F4. | unauthorized: 401→повторный ввод ключа без storage. | network: Network failure→видимая ошибка/retry GET, без fixtures. | reset: Отмена запросов и освобождение media; принятый backend job продолжает свой lifecycle.

</details>

### F2 — Загрузка и статусы

Разработчик: №2. Тип: code. Фаза: implementation.
Зависимости: F1. Состояние: не сверено с Git.

Файлы:

- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`

Критерии приёмки:

- MP4/MOV,200МиБ и серверные медиаограничения показаны до отправки; client checks не заменяют decode validation.
- Upload progress отличим от processing. queued/running остаются публичным processing.
- 202 сохраняет job_id в памяти UI; polling имеет bounded retry/cleanup/terminal stop. Повторный GET не создаёт job.
- 400/401/404/413/415/429/503, network outage и failed с причиной покрыты компонентными тестами.
- Отмена upload/закрытие вкладки не называется отменой принятого job. Возврат по job_id требует auth.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Dropzone/upload и polling processing/done/failed с корректными ошибками и busy состоянием.
Исполнитель №2. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: 202→processing→done с результатом или failed с причиной. | invalid: 400/413/415→исправить файл без job. | busy: 429→повторить позже без POST спама. | modelMissing: 503 model_not_ready→инструкция release. | network: Состояние неизвестно до повторного GET; не подставлять done/failed.

</details>

### F3 — Видео и доказательства

Разработчик: №2. Тип: code. Фаза: implementation.
Зависимости: F1. Состояние: не сверено с Git.

Файлы:

- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`

Критерии приёмки:

- Protected fetch→Blob≤200МиБ; Object URLs освобождаются при смене job/key/unmount, ключа в URL нет.
- Click события/кадра использует исходный timecode и preview mapping; VFR/rotation/nonzeroPTS не заменяются frame_index/fps.
- Карточка показывает1–3 JPEG, интервал, timestamp, source/version/limitations из API. Кадр другого ролика не подставляется.
- Unknown/unsupported и неподтверждённый источник различимы; пустой список нарушений не обещает абсолютную безопасность.
- Битый base64/preview/кадр даёт видимую локальную ошибку. UI не скрывает неработающее evidence.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: HTML video/seek и события с исходными кадрами, source time mapping и ограничениями.
Исполнитель №2. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Оператор проверяет тот же ролик, timecode и исходный кадр. | mediaFailure: Нет видео/кадра — явная ошибка, не выдуманное доказательство. | unknown: Неизвестные условия/источники показаны с ограничениями. | resourceLimit: Blob сверх лимита — контролируемый отказ, не падение вкладки.

</details>

### F4 — Ошибки и доступность UI

Разработчик: №2. Тип: code. Фаза: implementation.
Зависимости: F1. Состояние: не сверено с Git.

Файлы:

- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/styles.css`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`

Критерии приёмки:

- Missing/invalid/incompatible/test-only release отображается как model_not_ready с инструкцией локального импорта.
- Auth/busy/media/network/failed различимы и дают следующее действие без секретов и внутренних paths.
- Семантические labels, focus/keyboard и сообщения статуса проверены; component harness работает при360/768/1440px.
- Fixture/demo provenance виден; production показывает фактическую readiness и ограничения.
- Полный browser journey/адаптивность после F/I проверяются в U; component harness не считается полной приёмкой.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: Model/error panels и адаптивные стили с доступностью для последующей сборки UI.
Исполнитель №2. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Понятные ошибки и доступный адаптивный UI. | missing: Нет модели — инструкция пакета без запуска train из UI. | a11yFailure: Focus/keyboard/читаемость не проходят — исправить F4/F и проверить. | partial: Нет preview/источника — видимое ограничение, не замена фактами.

</details>

### F — Интерфейс анализа

Разработчик: №2. Тип: code. Фаза: integration.
Зависимости: F2, F3, F4. Состояние: не сверено с Git.

Файлы:

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ApiKeyForm.tsx`
- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/fixtures/contract-fixtures.ts`
- `frontend/src/App.test.tsx`
- `frontend/README.md`
- `frontend/src/api/client.test.ts`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`

Критерии приёмки:

- UI принимает MP4/MOV и до отправки показывает ограничения 200 МиБ/180 с/размер/fps; progress upload и processing/polling разделены, queued/running не раскрываются как новые публичные статусы.
- Есть состояния processing/done/failed и обработка 400/401/404/413/415/429/503, отмены fetch/ошибки сети и повторной проверки; отсутствие модели показывает model_not_ready и инструкцию локального импорта release, без выдуманного результата.
- Ключ вводится пользователем, хранится только в памяти вкладки и передаётся X-API-Key через fetch; отсутствует в bundle/URL/localStorage/sessionStorage/logs, сброс ключа отменяет polling и освобождает медиа.
- HTML video получает защищённый Blob в согласованном лимите до 200 МиБ; Object URLs освобождаются. Нажатие события/кадра устанавливает исходный timecode с учётом preview mapping; ошибки preview честно показаны.
- Карточка события показывает 1–3 кадра, интервалы и исходные таймкоды, provenance/source/редакцию/ограничения из diagnostics; public jury response не расширяется, unknown/unsupported не маскируются зелёным успешным ML-вердиктом.
- Contract fixtures имеют видимую метку synthetic test/demo, отдельную конфигурацию и не подключаются при production build. Синтетическое видео используется лишь для UI/seek проверки.
- Компонентные проверки реального поведения покрывают upload/poll/error/seek; интерфейс проверен при 360,768,1440 px, с клавиатурой, читаемыми состояниями и без горизонтального переполнения.
- npm lock, typecheck и production build воспроизводимы; frontend/README содержит фактические команды и различает fixture mode и production. Интеграция реального API и браузерная приёмка выполняются в I/U.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: собранный React UI из F1–F4: App/main, полный upload/poll/video/evidence/model-readiness путь на contract fixtures и production API client. Проверить typecheck/build и компонентную интеграцию. Полный браузер с настоящим backend после I проверяется в U.
Исполнитель №2. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: UI собран, typed client/fixtures изолированы; готов к I. | noModel: Показана инструкция release, нет выдуманного результата. | failure: Build/contract/a11y/fixture leakage — исправить F1–F4 или F, не подменять API.

</details>

### U — Браузерная приёмка

Разработчик: №2. Тип: test. Фаза: verification.
Зависимости: I. Состояние: не сверено с Git.
Исходный helperFor: Z. Это существующая задача №2; новый чат не обязателен, если пользователь не разрешил дочерние чаты.

Файлы:

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ApiKeyForm.tsx`
- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/fixtures/contract-fixtures.ts`
- `frontend/src/App.test.tsx`
- `frontend/README.md`
- `tests/e2e/playwright.config.ts`
- `tests/e2e/upload.spec.ts`
- `tests/e2e/video-evidence.spec.ts`
- `tests/e2e/errors-model.spec.ts`
- `tests/e2e/responsive-auth.spec.ts`
- `tests/e2e/report.json`
- `frontend/ACCEPTANCE.md`
- `frontend/src/api/client.test.ts`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`

Критерии приёмки:

- Браузерные тесты на работающем API проходят upload/poll/done/failed,event click/seek,1–3 JPEG evidence frames и отображение источника/версий/ограничений; synthetic provenance видна.
- Production без release показывает503 model_not_ready/инструкцию локального импорта и не показывает fixture result. Проверены401,400/413/415,429,network failure,retry и отмена polling.
- Для synthetic clip timestamp→HTML video seek и исходный evidence frame сопоставлены с допуском не больше одного исходного кадра при известном PTS. Доступные настоящие кадры проверяются только если реально предоставлены; иначе отсутствие документируется.
- При360/768/1440px нет горизонтального переполнения,контролы доступны с клавиатуры,upload/status/video/result читаемы; фактические screenshot/vision наблюдения записаны.
- Проверено отсутствие API ключа в bundle,URL,browser storage и логах,auth защищает media,Blob ограничен200МиБ и освобождается при смене задания/ключа.
- Отчёт содержит браузер/версию,точный commit,команды/exitCode,покрытие acceptance и реальные дефекты/ограничения; авторские проверки не называются независимым approval.
- Проверены разрыв сети после202, возврат к job_id, reset ключа, отмена fetch и освобождение Blob. Принятый серверомjob не объявляется отменённым из-за закрытия вкладки.

<details>
<summary>Исходное описание карточки — включая историю планирования</summary>

Проверяемый результат: браузерная приёмка интегрированного UI с настоящим API: production503 и отдельно synthetic test-mode полный путь. Проверить клавиатуру, адаптивность, auth/reset, tab/network interruption, video/seek/evidence/source/unknown. Исправления только frontend/e2e после I; backend дефекты возвращать в существующую профильную карточку.
Исполнитель №2. Общая база46b7bc941e64fec5649242b8290607c8f7339819, origin https://github.com/AlmazCode/Fortress,main,rootPath=''. Сейчас только план; код/claims/чаты/train/deploy/push/PR/merge не запускать. Исполнение позже в собственной проверенной ветке; manual — другой участник или явная приёмка человека.
Исходы: success: Реальный browser journey/seek/auth/адаптивность проверены. | missingFrames: Нет реальных исходников — это limitation, synthetic frame provenance проверяется фактически. | failure: Browser/API/evidence mismatch — вернуть в F/I/A по месту, не прятать ошибку. | noRelease: 503 UI ожидаем и проверен, не чистый вердикт.

</details>
