# Сводка проекта — ведёт только главный

Интеграционная ветка: `codex/integration`. Проверенный merge документации и кода: `c221374` (K и A1 входят по ancestry). Общая main не изменяется. Приёмка ниже — фактическая авторская проверка главным №1, не независимая человеческая приёмка. Другие роли пока unverified; наличие ветки не подтверждает выполнение.

Принятые commits: K — `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`; A1 — `a84cce5e19c8b5a96286473aa9283c2c6b3a1194`. Команды, покрытие и ограничения — [журнал №1](status/DEV-1.md).

- [ ] O1 — Среда и внешний маршрут · №4 · unverified
- [x] K — Контракт API и данных · №1 · accepted
- [x] A1 — БД и состояние заданий · №1 · accepted
- [x] A2 — Приём и проверка видео · №1 · accepted
- [x] A3 — Авторизация и медиа · №1 · accepted
- [x] A4 — Outbox и один worker · №1 · accepted
- [x] A5 — Дедлайны и сбои backend · №1 · accepted
- [ ] A — API и надёжная очередь · №1 · working
- [ ] F1 — Клиент API и ключ · №2 · ready (K опубликован; реализация не проверена)
- [ ] F2 — Загрузка и статусы · №2 · unverified
- [ ] F3 — Видео и доказательства · №2 · unverified
- [ ] F4 — Ошибки и доступность UI · №2 · unverified
- [ ] F — Интерфейс анализа · №2 · unverified
- [ ] D1 — Аудит данных и среды · №3 · unverified
- [ ] D2 — Классы и инструкция разметки · №3 · unverified
- [ ] D3 — Импорт и split без утечки · №3 · unverified
- [ ] D4 — Кадры и клипы по PTS · №3 · unverified
- [ ] D5 — Разметка объектов и событий · №3 · unverified
- [ ] D — Данные и preflight · №3 · unverified
- [ ] M1 — Preprocessing и кэш · №3 · unverified
- [ ] M2 — GRU и CPU train/resume · №3 · unverified
- [ ] M3 — Оценка и экспорт пакета · №3 · unverified
- [ ] M4 — Loader и inference adapter · №3 · unverified
- [ ] M — ML CLI и загрузка release · №3 · unverified
- [ ] R1 — Кейсы и нормативные источники · №4 · unverified
- [ ] R2 — Память ролика и связей · №4 · unverified
- [ ] R3 — Правила и сложные примеры · №4 · unverified
- [ ] R — Правила и источники · №4 · unverified
- [ ] O2 — Compose и offline worker · №4 · unverified
- [ ] O3 — TLS и внешний smoke · №4 · unverified
- [ ] O — Compose и доступ по HTTPS · №4 · unverified
- [ ] I — Интеграция без весов · №1 · unverified
- [ ] U — Браузерная приёмка · №2 · unverified
- [ ] E — Передача ML-инструментов · №3 · unverified
- [ ] B — Восстановление и benchmark · №4 · unverified
- [ ] Z — Финальная сдача · №1 · unverified

A2 принят и включён в `codex/integration`: `df5dae07b4683afff88bdd06bfbf5b34bd7cc382` (19 проверок).

A3 принят в `codex/integration`: `6f7f5bf689440640bdc205642aefe7bf07a4d283` (8 проверок).

A4 принят в `codex/integration`: `61a69ce8edc254b4d62ab0652eb8f89df146e434` (7 проверок).

A5 и исправленный A1 приняты в `codex/integration`: `4e5d9b09b292af03f27991b32cadf9aae2af64d6`. Ветка frontend `551454a` содержит только прежний отчёт о блокировке по K; код frontend отсутствует, K теперь доступен.
