# Журнал разработчика №2 — Frontend

Обновлено 17 октября 2026. Работа через Git/GitHub, без Aster. По указанию пользователя №2 остаётся здесь; другой frontend-чат остановлен. Исходные черновики сохранены в локальной контрольной точке.

| Task | State | Результат / зависимость |
| --- | --- | --- |
| F1 | review | `bab9998bb094605ceadbfb42412080fa1e0f3b3f`, 42 теста, typecheck и build проходят |
| F2 | blocked | Ожидает проверки и интеграции точного F1 главным |
| F3 | blocked | Ожидает проверки и интеграции точного F1 главным |
| F4 | blocked | Ожидает проверки и интеграции точного F1 главным |
| F | blocked | Зависит от F2/F3/F4 |
| U | blocked | Зависит от I; настоящий API и браузер ещё не проверены |

## Checkout и база

- Origin: `https://github.com/AlmazCode/Fortress`, rootPath пустой. Ветка `codex/dev2-frontend`, worktree `${WORKSPACE}/.worktrees/dev2-frontend`; абсолютный путь сохранён в локальном checkpoint `dev2-github-root.json` вне Git.
- Исходная база `46b7bc941e64fec5649242b8290607c8f7339819`, ancestry проверена.
- K: `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`, `origin/codex/fortress-backend`. Контракт прочитан и проверен: 55 тестов схем на Python 3.11.17. Обычный merge без изменения contracts.
- Base F1: `307c3da68798e5468ac009fe64aba148ddd7a324`; head кода F1: `bab9998bb094605ceadbfb42412080fa1e0f3b3f`. Коммит отчёта определяется Git-историей; код F1 им не меняется.
- Последний fetch — exit 0. Интеграционная ветка и принятые SHA пока не опубликованы; общий STATUS.md содержит unverified. Это авторская проверка кандидата, не глобальная приёмка K/F1.

## Изменения F1

Только десять разрешённых файлов: package.json, package-lock.json, tsconfig.json, vite.config.ts, index.html, src/api/client.ts, src/api/types.ts, src/components/ApiKeyForm.tsx, src/fixtures/contract-fixtures.ts, src/api/client.test.ts — всё внутри frontend/. Общие contracts/lock не изменены.

Public Job, diagnostics, model и error envelope проверяются непосредственно JSON-схемами K через offline AJV Draft 2020-12. Unknown/unsupported/null versions сохраняются; неверные job_id, внутренние статусы и дополнительные jury-поля отвергаются.

Ключ остаётся в памяти и передаётся X-API-Key. Reset отменяет fetch/query/media stream и удаляет кеш своей сессии. POST автоматически не повторяется. GET имеет не более двух автоматических повторов при сетевой ошибке. После 202 новый авторизованный сеанс может получить job_id без нового POST. Неподтверждённая отправка остаётся неопределённым исходом.

Protected media/preview проверяются по маршруту, MIME и фактическому числу потоковых байтов до 200 МиБ, независимо от Content-Length. Redirect запрещён. Blob URL и их освобождение относятся к F3; здесь возвращается ограниченный Blob.

Fixtures имеют явный test/demo transport и synthetic provenance; production-client их не импортирует. Production fixture build запрещён. ApiKeyForm показывает synthetic test/demo notice при явном fixtureMode; подключение в полный App относится к F. Сетевой сбой fixtures не включает.

## Реальные проверки

Frontend-команды выполнены из frontend/ на Node 22.22.2 / npm 11.1.0. Проверялся код кандидата; затем удалены только лишние пустые строки в конце двух файлов.

| Команда / проверка | Exit | Наблюдение |
| --- | --- | --- |
| `uv run --locked --group test python -X utf8 -m pytest tests/contracts/test_schemas.py -q` | 0 | 55 passed, Python 3.11.17, внешнее окружение, lock не менялся |
| `npm ci --ignore-scripts --no-fund --no-audit --registry=https://registry.npmjs.org` | 0 | Чистая установка 122 пакетов по lockfile |
| `npm run typecheck` | 0 | Strict TypeScript, текущие файлы F1 |
| `npm test -- src/api/client.test.ts` | 0 | 42 passed: schemas, 400/401/404/413/415/429/503, auth/reset/abort, bounded retry, один POST, media cap/cancel, demo notice |
| `npm run build` | 0 | Vite production build, без CDN |
| `npm exec vite build -- --mode fixture` | 1, ожидаемый | Fixture production build запрещён |
| Проверка production JS | 0 | Нет тестового ключа и маркеров payload/transport fixtures |
| `git diff --cached --check` | 0 | Перед commit, десять файлов F1 |

## Покрытие критериев и ограничения

1. Стек зафиксирован lockfile; чистая установка, typecheck, build и компонентные тесты проходят. Это scaffold клиента: index загружает API-модуль, полноценный экран собирается в F.
2. Header-only key, отсутствие записи storage/logs, очистка формы и сессионная отмена проверены тестами. Полный 401→повторный ввод в работающем App и браузере относится к F/U.
3. Public/diagnostic types проверены на схемах K, unknown не преобразуется в отсутствие. Invalid evidence, противоречивый verdict и none-coverage done отвергаются.
4. Explicit fixtures, synthetic provenance/notice и отсутствие fallback проверены. Визуальная приёмка полного demo UI ещё не выполнена.
5. Abort до acceptance не возвращает done; отключение после 202 не называется отменой server job. Polling/new session не повторяют POST. Backend lifecycle этим тестом не сертифицируется.

Fetch не предоставляет надёжный прогресс байтов отправки: transfer indeterminate, подтверждение завершения только после корректного 202. F2 должен отличать его от server processing.

Черновики App/main и будущих компонентов сохранены локально, не входят в commit и не считаются реализацией следующих этапов. Настоящие API, preview/seek, Blob URL cleanup, адаптивность 360/768/1440 и browser journey — not_run. Release, train и реальные данные не запускались.

## Следующее действие

Главному: проверить и интегрировать точный F1 `bab9998bb094605ceadbfb42412080fa1e0f3b3f`, записать принятую ветку/SHA в STATUS.md. Затем №2 продолжает F2/F3/F4 без нового рутинного разрешения. Push не означает accepted; общая main не изменялась.

## Продолжение по указанию пользователя

Пользователь явно разрешил F2–F4 в собственной ветке на проверенном F1, оставив приёмку и общую интеграцию главному. В свою ветку объединён `origin/codex/integration` на `14e322a`; merge `d22a8bccc8ed384cdc74bb14a2c0a1a97a58c26f`. K не менялся, A1–A3 и их проверки доступны; main не изменялась.

F2: кандидат review, текущий commit определяется заголовком следующей Git-записи. Четыре файла UploadPanel/JobStatus и их тесты. Реализованы ограничения выбора, indeterminate transfer, явная отмена связи, UUID/auth resume и useJobPolling с bounded GET retry, terminal stop и cleanup. `npm test -- src/components/UploadPanel.test.tsx src/components/JobStatus.test.tsx` → exit 0, 19 passed. Отдельный strict tsc для этих четырёх файлов → exit 0. Начальный тест выявил доступный native file input при disabled panel; добавлен disabled, повторная проверка прошла. Сценарии настоящего API остаются U после I.

Уточнение проверки F2: первоначальная команда tsc с явными файлами была отклонена TypeScript 7 (TS5112). После добавления `--ignoreConfig` исправлены типы query options и boolean-условие JSX; strict tsc → exit 0, затем повторно 19 passed. Эти исправления включены в окончательный commit F2 до публикации.
