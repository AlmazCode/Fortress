# Сводка проекта — ведёт только главный

Интеграционная ветка: `codex/integration`. Последние проверенные интеграции: A `043eeb6`, F1 merge `f4ae1b5`, D1 merge `8dd2da1`, O1/R merge `df1f398` (K и все A1–A5 входят по ancestry). Общая main не изменяется. Приёмка ниже — фактическая авторская проверка главным №1, не независимая человеческая приёмка. Приёмка этапов относится только к указанному объёму; legal/ML/GPU/external HTTPS gates описаны отдельно ниже.

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
- [ ] F2 — Загрузка и статусы · №2 · ready (F1 принят)
- [ ] F3 — Видео и доказательства · №2 · ready (F1 принят)
- [ ] F4 — Ошибки и доступность UI · №2 · ready (F1 принят)
- [ ] F — Интерфейс анализа · №2 · unverified
- [x] D1 — Аудит данных и среды · №3 · accepted (536fe7a, merge 8dd2da1)
- [ ] D2 — Классы и инструкция разметки · №3 · ready (K принят)
- [ ] D3 — Импорт и split без утечки · №3 · ready (K принят)
- [ ] D4 — Кадры и клипы по PTS · №3 · unverified
- [ ] D5 — Разметка объектов и событий · №3 · unverified
- [ ] D — Данные и preflight · №3 · unverified
- [ ] M1 — Preprocessing и кэш · №3 · unverified
- [ ] M2 — GRU и CPU train/resume · №3 · unverified
- [ ] M3 — Оценка и экспорт пакета · №3 · unverified
- [ ] M4 — Loader и inference adapter · №3 · unverified
- [ ] M — ML CLI и загрузка release · №3 · unverified
- [x] R1 — Кейсы и нормативные источники · №4 · accepted software / missingSource; legal gate unknown
- [x] R2 — Память ролика и связей · №4 · accepted
- [x] R3 — Правила и сложные примеры · №4 · accepted software; все production cases unsupported
- [x] R — Правила и источники · №4 · accepted software (9569729); legal gate unknown
- [ ] O2 — Compose и offline worker · №4 · blocked (entrypoints/runtime/scope)
- [ ] O3 — TLS и внешний smoke · №4 · blocked (нет подтверждённого внешнего HTTPS)
- [ ] O — Compose и доступ по HTTPS · №4 · blocked (O2/O3)
- [ ] I — Интеграция без весов · №1 · blocked (F/M/R/O)
- [ ] U — Браузерная приёмка · №2 · unverified
- [ ] E — Передача ML-инструментов · №3 · unverified
- [ ] B — Восстановление и benchmark · №4 · unverified
- [ ] Z — Финальная сдача · №1 · blocked (I → U/E/B)

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

### Возврат O2/O3 владельцу №4

Кандидат `5834064393dc16de066254c5d10b97826ebadf6a` **не интегрирован и не принят**. Следующие замечания проверены по его точному коду и принятому A:

1. `infra/api.Dockerfile:31` ссылается на отсутствующий `backend.app.main:app`. Поддерживается `python -m backend.app.main api --host 0.0.0.0 --port 8000` либо uvicorn `backend.app.main:create_app --factory --no-access-log`.
2. `infra/compose.yaml:67,99` и `infra/worker.Dockerfile:34` ссылаются на отсутствующий `backend.app.celery_app:celery_app`. Поддерживается `python -m backend.app.main worker`; он запускает принятый prefork, concurrency=1. `--pool=solo` не соответствует проверенному production hard-timeout механизму.
3. `inspect ping` healthcheck несовместим с `worker_enable_remote_control=False`; указанное destination также не совпадает с явным worker hostname. Нужен проверяемый health mechanism без ложного unhealthy.
4. Общая Settings сейчас требует `FORTRESS_API_KEY`, `DATABASE_URL`, `REDIS_URL` для CLI; worker environment не передаёт ключ. Согласовать worker-only settings с №1 либо полный контракт env до runtime test. Запуск миграций тоже должен быть явным до API/worker.
5. `infra/.gitattributes` отсутствует в files всех задач №4; требуется убрать внеплановый путь либо отдельное указание человека о scope. Правки ранее выполненных O1/R в том же commit допустимо описать как их исправления, но не считать весь O2 принятым по ним.
6. Docker daemon, build/start, volume restart и worker egress здесь не подтверждены. Внешний hostname/certificate/incoming route не заданы; trusted внешний HTTPS upload/status не выполнен. CPU torch lock не подтверждает target CUDA.

F/M/O остаются prerequisites I. Z недоступна до I и U/E/B. Не подменять эти проверки синтетическим harness.
