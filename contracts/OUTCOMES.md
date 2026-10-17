# Stage outcomes

The current target is implementation ready / training deferred. Production model quality, dataset readiness and trusted external access require their own observed evidence. Synthetic fixtures establish software behavior only.

## O1 — Среда и внешний маршрут

ранний аппаратный/сетевой инвентарь и воспроизводимые preflight команды; может идти параллельно контракту K.

- **success**: Известны реальные возможности/пробелы и путь проверки инфраструктуры.
- **missingTool**: Нет Docker/FFmpeg/Python3.11 — список необходимых условий, не фиктивный pass.
- **gpu**: CUDA/GPU не подтверждены — gpu_ready=false, CPU tooling можно готовить.
- **cgnat**: Нет входящего пути/CGNAT — external_access_blocked до реального разрешённого маршрута.
- **externalPC**: Другой training PC недоступен — handoff instructions готовы, hardware not verified.

## K — Контракт API и данных

единый public/UI/data/release контракт, модульные порты и ownership для36 этапов. Исходные требования и внешняя jury схема сохранены; taxonomy пока draft. Прочитать объединённое ТЗ, фактические приложения и официальные API. Достаточность исследования: каждое независимое направление знает inputs/outputs/errors/versions/files и способы проверки. Отсутствующие25 классов/исходный кейс не выдумывать. Baseline и запрет training/cloud/face/audio сохраняются.

- **success**: Контракты/schema fixtures/ownership проходят проверки, можно принять K и открыть leaves.
- **missing**: Неизвестная taxonomy/норма/данные — draft/unknown с точным пробелом; UI/API остаются определимыми.
- **failure**: Противоречивый public/schema/module контракт — blocked до исправления K.

## A1 — БД и состояние заданий

PostgreSQL repository и миграции jobs/results/outbox с явными состояниями и уникальными ключами.

- **success**: Durable repository готов для A4/A.
- **missing**: Нет PostgreSQL/credentials — persistence acceptance blocked, code tests отдельно.
- **failure**: Rollback/миграция/двойной claim — исправить A1; пользовательскую БД не сбрасывать.

## A2 — Приём и проверка видео

Ограниченный upload/ffprobe/decode и подготовка media для durable job port с исходным временем.

- **success**: Валидный оригинал и time mapping переданы в durable port.
- **invalid**: Медиа не проходит лимиты/декодирование —4xx без job.
- **failure**: Диск/декодер/сохранение недоступны — service failure, без вердикта.
- **clientLost**: До durable accept — cleanup; после accept job продолжает выполнение.

## A3 — Авторизация и медиа

Авторизация всех endpoints данных и protected media/preview с проверяемым временем.

- **success**: Авторизованный оператор видит свой выбранный job и его исходные media.
- **denied**: Нет/неверный ключ→401; нет job→404 без выдачи путей.
- **partial**: Нет preview/кадра — media error, без выдуманного доказательства.
- **scope**: Shared key не означает персональную изоляцию пользователей.

## A4 — Outbox и один worker

Durable outbox PostgreSQL→Celery/Redis и один активный GPU job с fencing/idempotency.

- **success**: Одно принятое задание даёт один устойчивый итог.
- **brokerDown**: Outbox сохраняет job и восстанавливает доставку в пределах deadline.
- **duplicate**: Повторная доставка не дублирует анализ/result.
- **workerCrash**: Новый lease/fencing, stale commit отвергается.
- **busy**: Конкурентный intake→429; очередь не расширяется без benchmark.

## A5 — Дедлайны и сбои backend

Fault-injection проверки intake/auth/queue/repository до общей API-сборки.

- **success**: Failure/retry/deadline semantics готовы для A.
- **timeout**: Deadline→failed и освобождение capacity.
- **failure**: Потеря job/двойной result/stale commit — blocked до исправления.
- **notRun**: Нет DB/Redis — соответствующие checks not_run, не passed.

## A — API и надёжная очередь

собранный настоящий FastAPI из принятых A1–A5: upload/status/auth/media, PostgreSQL/outbox/Celery и tests на реальных сервисах. Собрать main/settings/schemas/API routing и fixture runner только test profile. Не повторять модульные задачи отдельными копиями; исправлять существующие карточки. Общие locks K не менять параллельно другим веткам без обновлённого контракта.

- **success**: Настоящий API с persistence/queue/auth прошёл проверки.
- **missing**: Нет реальных DB/Redis/runtime — интеграционная acceptance blocked, mocks отдельно.
- **noModel**: Production503 ожидаем, synthetic runner только test.
- **failure**: API/security/persistence regression — исправить соответствующую A1–A5, затем сборку A.

## F1 — Клиент API и ключ

TypeScript/Vite scaffold, typed Query client и lifecycle ключа с отдельным test transport.

- **success**: Общий client/types готовы для F2/F3/F4.
- **unauthorized**: 401→повторный ввод ключа без storage.
- **network**: Network failure→видимая ошибка/retry GET, без fixtures.
- **reset**: Отмена запросов и освобождение media; принятый backend job продолжает свой lifecycle.

## F2 — Загрузка и статусы

Dropzone/upload и polling processing/done/failed с корректными ошибками и busy состоянием.

- **success**: 202→processing→done с результатом или failed с причиной.
- **invalid**: 400/413/415→исправить файл без job.
- **busy**: 429→повторить позже без POST спама.
- **modelMissing**: 503 model_not_ready→инструкция release.
- **network**: Состояние неизвестно до повторного GET; не подставлять done/failed.

## F3 — Видео и доказательства

HTML video/seek и события с исходными кадрами, source time mapping и ограничениями.

- **success**: Оператор проверяет тот же ролик, timecode и исходный кадр.
- **mediaFailure**: Нет видео/кадра — явная ошибка, не выдуманное доказательство.
- **unknown**: Неизвестные условия/источники показаны с ограничениями.
- **resourceLimit**: Blob сверх лимита — контролируемый отказ, не падение вкладки.

## F4 — Ошибки и доступность UI

Model/error panels и адаптивные стили с доступностью для последующей сборки UI.

- **success**: Понятные ошибки и доступный адаптивный UI.
- **missing**: Нет модели — инструкция пакета без запуска train из UI.
- **a11yFailure**: Focus/keyboard/читаемость не проходят — исправить F4/F и проверить.
- **partial**: Нет preview/источника — видимое ограничение, не замена фактами.

## F — Интерфейс анализа

собранный React UI из F1–F4: App/main, полный upload/poll/video/evidence/model-readiness путь на contract fixtures и production API client. Проверить typecheck/build и компонентную интеграцию. Полный браузер с настоящим backend после I проверяется в U.

- **success**: UI собран, typed client/fixtures изолированы; готов к I.
- **noModel**: Показана инструкция release, нет выдуманного результата.
- **failure**: Build/contract/a11y/fixture leakage — исправить F1–F4 или F, не подменять API.

## D1 — Аудит данных и среды

Инвентарь исходников/разметки/прав использования и CPU/GPU preflight CLI без обучения.

- **success**: Инвентарь и preflight команды готовы.
- **noData**: Нет видео/labels — data_missing, synthetic только code smoke.
- **imagesOnly**: Только фото — object/frame dataset возможен, temporal training ждёт видео.
- **hardware**: Нет CUDA/другого ПК — CPU smoke, hardware gate unverified.
- **license**: Права данных неизвестны — не использовать для train, указать конкретный пробел.

## D2 — Классы и инструкция разметки

Отдельные versioned taxonomies объектов, действий и состояний; гайд разметчика и связь с C01–C15.

- **success**: Определения и гайд позволяют начать локальную разметку.
- **noCase**: Нет исходного кейса — draft и gap report, не окончательный набор.
- **ambiguous**: Не различимы объект/действие — unknown/needs_review.
- **architecture**: Датасет объектов не означает готовый detector. Его обучение/интеграция — отдельный этап.

## D3 — Импорт и split без утечки

Read-only импорт, manifest/hashes, дубли и grouped split до формирования кадров/окон.

- **success**: Versioned manifest/split без утечки source groups.
- **invalidArchive**: Небезопасный архив отвергнут без скрытого частичного импорта.
- **corrupt**: Источник quarantine с причиной, original сохранён.
- **leakage**: Группы/дубли пересекают partitions — split invalid, train gate закрыт.
- **empty**: Инструмент проверен на fixture; пустой manifest не объявляется реальным датасетом.

## D4 — Кадры и клипы по PTS

CLI извлечения сцен, кадров и клипов с source PTS и provenance для object/action datasets.

- **success**: Кадры/клипы и mapping manifest готовы для разметки.
- **short**: Хвост получает padding mask; неполный интервал не даёт false absence.
- **scene**: Смена сцены разрывает окно/память.
- **missingPTS**: Невосстановимое время — quarantine/unsupported, не вымышленные timecodes.
- **noData**: CLI проверен на synthetic; реальные clips ждут originals.

## D5 — Разметка объектов и событий

Локальные annotation bundles, canonical JSONL/interval CSV, COCO roundtrip и QA без выдуманного gold.

- **success**: Annotation/COCO/QA инструменты готовы; dataset_ready только по реальным reviewed labels.
- **noLabels**: Есть кадры без labels — annotation_missing и очередь ручной разметки.
- **badLabels**: Неверные bbox/time/class/split — validation failure, train gate закрыт.
- **objectsOnly**: Object annotation ready; temporal gate остаётся закрыт.
- **disagreement**: Расхождения — needs_review, не автоматический gold.
- **toolAbsent**: Нет локального annotation UI — bundles/validators доступны, ручная разметка отложена.

## D — Данные и preflight

собранные D1–D5 и единый data preparation CLI: inventory→safe import/dedup/group split→PTS/scenes/frame/clip export→object/action annotation import→QA/readiness. Документировать команды в DATA.md и отдельный data readiness report. Tools ready, object dataset ready и temporal dataset ready — разные состояния. Без оригиналов/labels инструменты проверяются tiny synthetic, а реальные gates остаются закрыты.

- **success**: Все инструменты подготовки проверены, readiness report воспроизводим.
- **noData**: Tools ready/data_missing — UI/API и ML tooling могут продолжаться; реальные clips/dataset не существуют.
- **objectsOnly**: Object annotation ready, temporal dataset ещё not_ready.
- **invalid**: Leakage/bad labels/missing human review — training gate закрыт, исправить D2–D5.
- **readyData**: Только реальные reviewed видео/labels и valid split позволяют data_ready; полный train всё равно отдельное поручение.

## M1 — Preprocessing и кэш

единый train/inference preprocessing и воспроизводимый кэш последовательностей с полным происхождением.

- **success**: Единый preprocessing и проверяемый cache готовы для M2.
- **changedInput**: Версия/хэш изменились — пересчитать затронутый кэш, не использовать старый marker.
- **interrupted**: Неполная запись — восстановить из source manifest, не принять за готовую.
- **dataMissing**: Code smoke возможен; cache_ready=false до реальных данных и локальных weights.

## M2 — GRU и CPU train/resume

MobileNetV3-Small features + pooling → 576 → GRU 1×256 → Linear и работоспособный ограниченный CPU train/resume.

- **success**: Код модели и CLI train/resume работает на CPU fixture.
- **mismatch**: Несовместимые shape/config/taxonomy — отказ resume с причиной.
- **oom**: Smoke OOM/NaN/invalid loss — blocked, исправить размер tiny fixture/код; не объявлять train успешным.
- **futureTraining**: Реальное обучение ждёт отдельного поручения, готовых данных и другого локального ПК.
- **allUnknown**: Полностью unknown/padded окно не создаёт NaN и не становится negative.

## M3 — Оценка и экспорт пакета

реализованные evaluator/calibration/export CLI и неизменяемый release со всеми версиями и SHA-256.

- **success**: CLI оценки/thresholds/export готов и проверен на synthetic.
- **leakage**: Final использован в настройке или split пересекается — оценка invalid, training/validation gate закрыт.
- **overBudget**: Реальный экспорт превысил бюджет — честный failure/ограничение, не исключать encoder из подсчёта.
- **noWeights**: Production release отсутствует, модель not trained/not validated; current software delivery возможна с503.

## M4 — Loader и inference adapter

строгая локальная загрузка release, ActionTimeline и безопасные отказы до production анализа.

- **success**: Совместимый подтверждённый release может быть загружен после отдельного обучения/передачи.
- **missing**: Нет пакета — model_not_ready/503 через backend.
- **invalid**: Hash/version/shape/test-only mismatch — отказ с причиной и сохранение прежнего пакета.
- **failure**: OOM/decode/inference exception — failed с причиной, не no_violation.
- **uncertain**: Непроверенная наблюдаемость/actors остаются unknown в timeline.

## M — ML CLI и загрузка release

собранные M1–M4 и реальные CLI cache/train/resume/evaluate/thresholds/export/import. ml/cli.py, CLI.md и TRAINING.md дают другому локальному ПК точные команды подготовки данных/окружения, CUDA preflight, annotation QA, обучение/оценку, export/hash/import и rollback. Проверяется только короткий CPU tiny pipeline; полное обучение/fine-tune/GPU search/реальная ML-оценка отложены.

- **success**: CPU pipeline и handoff работают, production пока not trained/not validated.
- **missing**: Нет real data/pretrained local weights/другого ПК — условие будущего этапа, не выдуманный success.
- **failure**: Smoke/loader/schema/CLI regression — blocked до исправления M1–M4.
- **future**: Отдельное разрешение+данные+hardware→train/evaluate/export→import; до этого503.

## R1 — Кейсы и нормативные источники

матрица C01–C15: необходимые наблюдения, границы доказуемости, подтверждённые источники и точные пробелы.

- **success**: Для подтверждённого подмножества есть применимый source-backed mapping.
- **missingSource**: Нет нормы/редакции/исходного кейса — unsupported/unknown; юридическая приёмка соответствующего кейса не пройдена.
- **notObservable**: Сумма/подделка/проводка/полномочия/закрытая сумка недоказуемы — не делать вывод.
- **changedRule**: Новая редакция источника требует новой rules version и повторной проверки затронутых кейсов.

## R2 — Память ролика и связей

память существенных интервалов обслуживания/партий на весь ролик с неизвестными actors/relations и reset по сцене.

- **success**: Последовательные наблюдения образуют воспроизводимое состояние ролика.
- **scene**: Новая сцена — reset и границы unknown, без переноса участников/денег.
- **missingActor**: Нет проверенного actor/party link — unknown, не подстановка наиболее вероятного.
- **truncated**: Начало/конец этапа отсутствует — недостаточная наблюдаемость для absence rule.

## R3 — Правила и сложные примеры

engine пяти шаблонов с трёхзначной логикой и покрытием всех кейсов без ложной юридической уверенности.

- **success**: Поддержанное правило объяснимо и покрыто сценарными тестами.
- **unknown**: Нет видимости/полного этапа/recognizer/источника — unknown, не not_triggered.
- **exception**: Подтверждённое исключение снимает trigger по явной логике, а не эвристической догадке.
- **failure**: Ложный trigger на hard-negative — blocked до исправления, критерии не ослабляются.

## R — Правила и источники

собранные R1–R3: versioned case/source mapping, session memory и tri-state rules с положительными, сложными отрицательными, неполными/закрытыми интервалами и исключениями. Проверить source provenance и объяснение на всём rule output. Отсутствие источника/наблюдаемости не выдавать за отсутствие нарушения.

- **success**: Поддержанное подмножество engine/source mappings проверено.
- **unknown**: Нет применимой нормы/видимости/actors — unknown/unsupported; юридический gate не пройден.
- **failure**: Ложный trigger/ложное not_triggered — исправить R1–R3, критерии не ослаблять.

## O2 — Compose и offline worker

конфигурация nginx/api/worker/redis/postgres с локальными volumes и изоляцией GPU/сети.

- **success**: Воспроизводимые контейнеры/volumes/изоляция готовы для I.
- **noDocker**: Config может быть подготовлен, но реальный container/offline test остаётся blocked/not_run.
- **noGPU**: Нет подтверждённого GPU runtime — gpu_ready=false, CPU test profile отдельно.
- **egress**: Интернет доступен worker — isolation failure, устранить до финала.
- **volume**: Данные пропали после restart — blocked, пользовательские volumes не удалять для исправления.

## O3 — TLS и внешний smoke

настроенный Nginx/HTTPS и наблюдённый внешний upload/status smoke на явном synthetic harness.

- **success**: Trusted внешний HTTPS маршрут наблюдён на synthetic data.
- **localOnly**: Доступен только localhost — local_only, обязательный внешний критерий не пройден.
- **certificate**: Нет валидной цепочки/имени/срока — TLS failure до исправления.
- **network**: CGNAT/firewall/маршрут не разрешены — external_access_blocked, без самовольного туннеля.
- **leak**: Сервис БД/Redis/media стал публичен безauth — blocked до исправления.

## O — Compose и доступ по HTTPS

собранные O1–O3: preflight, Compose isolation/volumes, Nginx/TLS и фактически наблюдённый внешний synthetic smoke. Начать O1 в первые два часа; №4 выполняет свои готовые R/O карточки последовательно без искусственных связей. До I проверка на infra harness не считается запуском всего приложения; после I внешний real-API повтор в B.

- **success**: Среда/изоляция/volumes/внешний HTTPS подтверждены реальными checks.
- **localOnly**: Только localhost — local_only; внешний обязательный критерий blocked.
- **missing**: Нет Docker/GPU/FFmpeg/сертификата/маршрута — конкретный blocker, остальные ветки продолжаются.
- **failure**: Public DB/Redis,worker egress,потеря volumes или TLS error — blocked до исправления.

## I — Интеграция без весов

интегрированные A/F/M/R/O и все их текущие принятые ancestors в одной собственной ветке с реальными commits. Соединить UI/API/repository/outbox/worker/inference/rules/media/diagnostics, реально запустить полный Compose при доступной среде. Без trained compatible release production возвращает503; test/demo fixtures явно отделены. Приёмочные U/E/B — заранее перечисленные дочерние Z; на стадии планирования чаты не создаются.

- **success**: Полная software интеграция прошла, открываются U/E/B.
- **noRelease**: Production503 и инструкция импорта; test journey только с explicit synthetic profile.
- **failure**: Контракт/медиа/очередь/Compose/rules wiring не проходит — fix профильной карточки и повтор I.
- **unknown**: Неизвестные ML/legal capabilities явно в diagnostics; fixtures не валидируют их.
- **insufficientEvidence**: Все существенные наблюдения unknown — failed insufficient_evidence, без clean verdict; partial coverage явно в diagnostics.

## U — Браузерная приёмка

браузерная приёмка интегрированного UI с настоящим API: production503 и отдельно synthetic test-mode полный путь. Проверить клавиатуру, адаптивность, auth/reset, tab/network interruption, video/seek/evidence/source/unknown. Исправления только frontend/e2e после I; backend дефекты возвращать в существующую профильную карточку.

- **success**: Реальный browser journey/seek/auth/адаптивность проверены.
- **missingFrames**: Нет реальных исходников — это limitation, synthetic frame provenance проверяется фактически.
- **failure**: Browser/API/evidence mismatch — вернуть в F/I/A по месту, не прятать ошибку.
- **noRelease**: 503 UI ожидаем и проверен, не чистый вердикт.

## E — Передача ML-инструментов

проверенная передача всех data/annotation/ML инструментов другого локального ПК: CLI, object COCO roundtrip, temporal labels/split/windows, preprocessing/cache/model/train-resume/evaluation/export/import, readiness gates и документация. CPU tiny fixture подтверждает код, не датасет/обучение/качество. Образец model card содержит реальные неизвестные, а не выдуманные metrics.

- **success**: Инструменты/команды/форматы переданы и воспроизведены на CPU tiny.
- **noDataset**: Реальные объекты/temporal labels не предоставлены — readiness=false, без выдуманного датасета.
- **future**: Full training/independent ML evaluation/production size budget отложены.
- **failure**: Инструкция не соответствует CLI/format или leakage — blocked до исправления D/M.

## B — Восстановление и benchmark

сквозные fault/offline/capacity/deadline/HTTPS проверки после I плюс готовая benchmark-команда для будущего trained release. Реальные сервисные failure/recovery тесты обязательны сейчас; latency/VRAM/RAM модели остаются не измерены до weights. Не удалять пользовательские volumes и не открывать worker internet ради прохождения проверки.

- **success**: Fault/offline/queue/HTTPS проверки прошли; benchmark инструменты готовы.
- **noWeights**: Настоящие latency/VRAM/RAM не измерены, synthetic цифры отдельно.
- **networkBlocked**: Нет trusted external route — обязательный network gate blocked.
- **failure**: Crash/retry/stale job/security regression — исправить A/O/I, затем повторить затронутые проверки.

## Z — Финальная сдача

окончательная интеграция всех36 карточек через U/E/B, итоговый commit, software E2E и инструкция с готовностью/ограничениями. Все прямые и транзитивные prerequisites должны быть приняты по manual policy. Текущий итог только implementation ready / training deferred либо blocked. Product ready + ML validated требует отдельного будущего обучения, imports и независимой ML/performance оценки.

- **success**: Все обязательные software/network acceptance подтверждены → implementation ready / training deferred.
- **blocked**: Любой обязательный software/network критерий не пройден → blocked с точной причиной.
- **futureValidated**: Только отдельный будущий train/import/independent ML+performance evaluation даёт product ready + ML validated.

Current review policy is automatic-all. Historical manual/planning-only text in the source plan does not cancel the later user execution authorization. Every successful check still needs actual command, exit code and candidate commit.

No usable production release: HTTP 503 model_not_ready before acceptance. Failure after durable acceptance: failed with a reason. Fully insufficient observable coverage: failed/insufficient_evidence. Partial coverage: supported findings may complete, with unknown/unsupported/limitations visible in diagnostics. no_violation means no violation found by the supported observable checks; it does not certify universal safety.
