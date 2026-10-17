# Разработчик №2 — Frontend

> **С 17 октября 2026 года проект перешёл с Aster на обычный Git/GitHub. Aster MCP, регистрации, claims, leases, heartbeat и сигнал запуска для координации больше не используются.** Источник задач — `plan.json`, исходников и результатов — Git. Слова lease/fencing в backend-коде относятся к надёжности заданий и сохраняют технический смысл.

Твои задачи: **F1, F2, F3, F4, F, U**. Только они и их точные файлы ниже; не выполняй чужие зависимости. Прочитай [общую инструкцию](WORKFLOW.md), [продуктовое ТЗ](REQUIREMENTS.md) и корневой AGENTS.md. Старые личные ТЗ с aster_join_team/aster_claim_task/aster_submit_result больше не задают рабочий процесс.

## Порядок работы

До принятого K проверь checkout и прочитай контракт, не выдумывая public types. После K — F1; затем собственные F2/F3/F4 и F. Браузерная приёмка U начинается только после I и проверяет настоящий UI с настоящим API. Fixtures должны быть явными; ключ хранится только в памяти вкладки.

Веди только [свой журнал](status/DEV-2.md).

Работай в своей изолированной ветке/worktree. Перед следующей задачей проверь точные принятые SHA её depends и текущий контракт. После тестов передай commit, diff, команды/exit codes, покрытие acceptance, ограничения и следующее действие. Обычный push своей ветки выполняется при действующем разрешении человека; push не равен приёмке и не разрешает запись в main. Если одна задача blocked, продолжи другую свою готовую. Не запрашивай рутинное подтверждение перехода и не жди MCP-сигнала.

| ID | Задача | Разработчик | После |
| --- | --- | --- | --- |
| F1 | Клиент API и ключ | №2 | K |
| F2 | Загрузка и статусы | №2 | F1 |
| F3 | Видео и доказательства | №2 | F1 |
| F4 | Ошибки и доступность UI | №2 | F1 |
| F | Интерфейс анализа | №2 | F2, F3, F4 |
| U | Браузерная приёмка | №2 | I |

## F1 — Клиент API и ключ

Разработчик №2. Фаза: implementation. Зависимости: K.

Проверяемый результат: TypeScript/Vite scaffold, typed Query client и lifecycle ключа с отдельным test transport.
Исходы: success: Общий client/types готовы для F2/F3/F4. | unauthorized: 401→повторный ввод ключа без storage. | network: Network failure→видимая ошибка/retry GET, без fixtures. | reset: Отмена запросов и освобождение media; принятый backend job продолжает свой lifecycle.

### Разрешённые файлы

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

### Критерии приёмки

1. Выбранный React/Vite/TypeScript/Tailwind/Query/Dropzone стек зафиксирован package-lock; typecheck/component test commands работают.
2. Ключ только в памяти вкладки, запросы через X-API-Key; нет секрета в URL/storage/bundle/logs. Reset отменяет query/fetch.
3. Public types соответствуют K; protected diagnostics отдельны, unknown не теряется при преобразовании.
4. Fixtures включаются только explicit test/demo config с видимым provenance. Сетевая ошибка production не включает fixtures.
5. Abort до принятия не выдаёт done; разрыв после202 не отменяет server job. Retry polling не повторяет POST автоматически.

### Исходы и блокировки

- **success**: Общий client/types готовы для F2/F3/F4.
- **unauthorized**: 401→повторный ввод ключа без storage.
- **network**: Network failure→видимая ошибка/retry GET, без fixtures.
- **reset**: Отмена запросов и освобождение media; принятый backend job продолжает свой lifecycle.

## F2 — Загрузка и статусы

Разработчик №2. Фаза: implementation. Зависимости: F1.

Проверяемый результат: Dropzone/upload и polling processing/done/failed с корректными ошибками и busy состоянием.
Исходы: success: 202→processing→done с результатом или failed с причиной. | invalid: 400/413/415→исправить файл без job. | busy: 429→повторить позже без POST спама. | modelMissing: 503 model_not_ready→инструкция release. | network: Состояние неизвестно до повторного GET; не подставлять done/failed.

### Разрешённые файлы

- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatus.tsx`
- `frontend/src/components/UploadPanel.test.tsx`
- `frontend/src/components/JobStatus.test.tsx`

### Критерии приёмки

1. MP4/MOV,200МиБ и серверные медиаограничения показаны до отправки; client checks не заменяют decode validation.
2. Upload progress отличим от processing. queued/running остаются публичным processing.
3. 202 сохраняет job_id в памяти UI; polling имеет bounded retry/cleanup/terminal stop. Повторный GET не создаёт job.
4. 400/401/404/413/415/429/503, network outage и failed с причиной покрыты компонентными тестами.
5. Отмена upload/закрытие вкладки не называется отменой принятого job. Возврат по job_id требует auth.

### Исходы и блокировки

- **success**: 202→processing→done с результатом или failed с причиной.
- **invalid**: 400/413/415→исправить файл без job.
- **busy**: 429→повторить позже без POST спама.
- **modelMissing**: 503 model_not_ready→инструкция release.
- **network**: Состояние неизвестно до повторного GET; не подставлять done/failed.

## F3 — Видео и доказательства

Разработчик №2. Фаза: implementation. Зависимости: F1.

Проверяемый результат: HTML video/seek и события с исходными кадрами, source time mapping и ограничениями.
Исходы: success: Оператор проверяет тот же ролик, timecode и исходный кадр. | mediaFailure: Нет видео/кадра — явная ошибка, не выдуманное доказательство. | unknown: Неизвестные условия/источники показаны с ограничениями. | resourceLimit: Blob сверх лимита — контролируемый отказ, не падение вкладки.

### Разрешённые файлы

- `frontend/src/components/VideoPlayer.tsx`
- `frontend/src/components/EventList.tsx`
- `frontend/src/components/EvidenceCard.tsx`
- `frontend/src/components/VideoPlayer.test.tsx`
- `frontend/src/components/EvidenceCard.test.tsx`

### Критерии приёмки

1. Protected fetch→Blob≤200МиБ; Object URLs освобождаются при смене job/key/unmount, ключа в URL нет.
2. Click события/кадра использует исходный timecode и preview mapping; VFR/rotation/nonzeroPTS не заменяются frame_index/fps.
3. Карточка показывает1–3 JPEG, интервал, timestamp, source/version/limitations из API. Кадр другого ролика не подставляется.
4. Unknown/unsupported и неподтверждённый источник различимы; пустой список нарушений не обещает абсолютную безопасность.
5. Битый base64/preview/кадр даёт видимую локальную ошибку. UI не скрывает неработающее evidence.

### Исходы и блокировки

- **success**: Оператор проверяет тот же ролик, timecode и исходный кадр.
- **mediaFailure**: Нет видео/кадра — явная ошибка, не выдуманное доказательство.
- **unknown**: Неизвестные условия/источники показаны с ограничениями.
- **resourceLimit**: Blob сверх лимита — контролируемый отказ, не падение вкладки.

## F4 — Ошибки и доступность UI

Разработчик №2. Фаза: implementation. Зависимости: F1.

Проверяемый результат: Model/error panels и адаптивные стили с доступностью для последующей сборки UI.
Исходы: success: Понятные ошибки и доступный адаптивный UI. | missing: Нет модели — инструкция пакета без запуска train из UI. | a11yFailure: Focus/keyboard/читаемость не проходят — исправить F4/F и проверить. | partial: Нет preview/источника — видимое ограничение, не замена фактами.

### Разрешённые файлы

- `frontend/src/components/ModelStatus.tsx`
- `frontend/src/components/ErrorPanel.tsx`
- `frontend/src/styles.css`
- `frontend/src/components/ModelStatus.test.tsx`
- `frontend/src/components/ErrorPanel.test.tsx`

### Критерии приёмки

1. Missing/invalid/incompatible/test-only release отображается как model_not_ready с инструкцией локального импорта.
2. Auth/busy/media/network/failed различимы и дают следующее действие без секретов и внутренних paths.
3. Семантические labels, focus/keyboard и сообщения статуса проверены; component harness работает при360/768/1440px.
4. Fixture/demo provenance виден; production показывает фактическую readiness и ограничения.
5. Полный browser journey/адаптивность после F/I проверяются в U; component harness не считается полной приёмкой.

### Исходы и блокировки

- **success**: Понятные ошибки и доступный адаптивный UI.
- **missing**: Нет модели — инструкция пакета без запуска train из UI.
- **a11yFailure**: Focus/keyboard/читаемость не проходят — исправить F4/F и проверить.
- **partial**: Нет preview/источника — видимое ограничение, не замена фактами.

## F — Интерфейс анализа

Разработчик №2. Фаза: integration. Зависимости: F2, F3, F4.

Проверяемый результат: собранный React UI из F1–F4: App/main, полный upload/poll/video/evidence/model-readiness путь на contract fixtures и production API client. Проверить typecheck/build и компонентную интеграцию. Полный браузер с настоящим backend после I проверяется в U.
Исходы: success: UI собран, typed client/fixtures изолированы; готов к I. | noModel: Показана инструкция release, нет выдуманного результата. | failure: Build/contract/a11y/fixture leakage — исправить F1–F4 или F, не подменять API.

### Разрешённые файлы

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

### Критерии приёмки

1. UI принимает MP4/MOV и до отправки показывает ограничения 200 МиБ/180 с/размер/fps; progress upload и processing/polling разделены, queued/running не раскрываются как новые публичные статусы.
2. Есть состояния processing/done/failed и обработка 400/401/404/413/415/429/503, отмены fetch/ошибки сети и повторной проверки; отсутствие модели показывает model_not_ready и инструкцию локального импорта release, без выдуманного результата.
3. Ключ вводится пользователем, хранится только в памяти вкладки и передаётся X-API-Key через fetch; отсутствует в bundle/URL/localStorage/sessionStorage/logs, сброс ключа отменяет polling и освобождает медиа.
4. HTML video получает защищённый Blob в согласованном лимите до 200 МиБ; Object URLs освобождаются. Нажатие события/кадра устанавливает исходный timecode с учётом preview mapping; ошибки preview честно показаны.
5. Карточка события показывает 1–3 кадра, интервалы и исходные таймкоды, provenance/source/редакцию/ограничения из diagnostics; public jury response не расширяется, unknown/unsupported не маскируются зелёным успешным ML-вердиктом.
6. Contract fixtures имеют видимую метку synthetic test/demo, отдельную конфигурацию и не подключаются при production build. Синтетическое видео используется лишь для UI/seek проверки.
7. Компонентные проверки реального поведения покрывают upload/poll/error/seek; интерфейс проверен при 360,768,1440 px, с клавиатурой, читаемыми состояниями и без горизонтального переполнения.
8. npm lock, typecheck и production build воспроизводимы; frontend/README содержит фактические команды и различает fixture mode и production. Интеграция реального API и браузерная приёмка выполняются в I/U.

### Исходы и блокировки

- **success**: UI собран, typed client/fixtures изолированы; готов к I.
- **noModel**: Показана инструкция release, нет выдуманного результата.
- **failure**: Build/contract/a11y/fixture leakage — исправить F1–F4 или F, не подменять API.

## U — Браузерная приёмка

Разработчик №2. Фаза: verification. Зависимости: I.

Проверяемый результат: браузерная приёмка интегрированного UI с настоящим API: production503 и отдельно synthetic test-mode полный путь. Проверить клавиатуру, адаптивность, auth/reset, tab/network interruption, video/seek/evidence/source/unknown. Исправления только frontend/e2e после I; backend дефекты возвращать в существующую профильную карточку.
Исходы: success: Реальный browser journey/seek/auth/адаптивность проверены. | missingFrames: Нет реальных исходников — это limitation, synthetic frame provenance проверяется фактически. | failure: Browser/API/evidence mismatch — вернуть в F/I/A по месту, не прятать ошибку. | noRelease: 503 UI ожидаем и проверен, не чистый вердикт.

### Разрешённые файлы

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

### Критерии приёмки

1. Браузерные тесты на работающем API проходят upload/poll/done/failed,event click/seek,1–3 JPEG evidence frames и отображение источника/версий/ограничений; synthetic provenance видна.
2. Production без release показывает503 model_not_ready/инструкцию локального импорта и не показывает fixture result. Проверены401,400/413/415,429,network failure,retry и отмена polling.
3. Для synthetic clip timestamp→HTML video seek и исходный evidence frame сопоставлены с допуском не больше одного исходного кадра при известном PTS. Доступные настоящие кадры проверяются только если реально предоставлены; иначе отсутствие документируется.
4. При360/768/1440px нет горизонтального переполнения,контролы доступны с клавиатуры,upload/status/video/result читаемы; фактические screenshot/vision наблюдения записаны.
5. Проверено отсутствие API ключа в bundle,URL,browser storage и логах,auth защищает media,Blob ограничен200МиБ и освобождается при смене задания/ключа.
6. Отчёт содержит браузер/версию,точный commit,команды/exitCode,покрытие acceptance и реальные дефекты/ограничения; авторские проверки не называются независимым approval.
7. Проверены разрыв сети после202, возврат к job_id, reset ключа, отмена fetch и освобождение Blob. Принятый серверомjob не объявляется отменённым из-за закрытия вкладки.

### Исходы и блокировки

- **success**: Реальный browser journey/seek/auth/адаптивность проверены.
- **missingFrames**: Нет реальных исходников — это limitation, synthetic frame provenance проверяется фактически.
- **failure**: Browser/API/evidence mismatch — вернуть в F/I/A по месту, не прятать ошибку.
- **noRelease**: 503 UI ожидаем и проверен, не чистый вердикт.
