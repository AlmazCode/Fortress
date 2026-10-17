# Fortress Frontend

React / TypeScript / Vite / Tailwind / TanStack Query / Dropzone. Кандидат этапов F1–F4/F разработчика №2. Настоящая сквозная приёмка API/браузера относится к U после I. Обученного release и подтверждённого ML-качества этот интерфейс не создаёт.

## Подготовка и проверки

Node >=22.12; проверено на Node 22.22.2, npm 11.1.0. Из каталога frontend своего checkout:

```powershell
npm ci --ignore-scripts --no-fund --no-audit --registry=https://registry.npmjs.org
npm run typecheck
npm test
npm run build
```

Все версии закреплены package-lock.json. Установка требует доступа к npm; приложение/сборка используют локальные зависимости без CDN. Офлайн-изоляция рабочего сервиса проверяется профильными задачами инфраструктуры.

## Работа с настоящим API

```powershell
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Открыть http://127.0.0.1:5173. Vite проксирует /api на http://127.0.0.1:8000; запуск и конфигурация backend принадлежат №1/I. Без работающего backend будет видимая ошибка связи, без обученного совместимого release — model_not_ready и инструкция импорта. Точные команды импорта публикует backend/ML; UI не запускает train и не подставляет прогнозы.

Пользователь вводит существующий API-ключ в форме. Ключ живёт только в памяти вкладки и передаётся X-API-Key. Не задавайте его через VITE_*, URL, .env, localStorage/sessionStorage или исходники. После закрытия/перезагрузки требуется повторный ввод. Сброс отменяет fetch/polling и освобождает Blob URL. Принятое сервером задание этим не отменяется.

Производственная сборка — dist/. Проверить только статический результат можно `npm run preview -- --port 4173`; это не запускает backend. При развёртывании /api и protected media маршруты нужно направить на API того же origin согласно infra. У Vite preview нет настроенного API proxy; для браузерных dev-проверок с backend используйте npm run dev. Остановка локальных dev/preview серверов — Ctrl+C в запустившем их терминале.

## Явный synthetic test/demo

```powershell
npm run dev:fixture -- --host 127.0.0.1 --port 5173 --strictPort
```

Используйте отдельный свободный порт или остановите предыдущий Vite. Введите произвольное тестовое обозначение вместо настоящего ключа. Видна метка SYNTHETIC TEST / DEMO; readiness остаётся untrained/not validated. Транспорт возвращает только канонические искусственные примеры contracts/fixtures.json: 202, processing, затем synthetic violation с настоящим декодируемым тестовым JPEG 16×16. Выбранный MP4/MOV в fixture mode не отправляется на сервер и не анализируется. Видео/preview отсутствует явно; JPEG не приписывается выбранному ролику. Реальный seek по исходному видео проверяется в U.

Fixtures подключаются только guarded dynamic import при Vite mode fixture. `vite build --mode fixture` запрещён. Production build не содержит fixture payload/transport, а сетевая ошибка не переключает на demo. Компонентные тесты используют отдельный transport с явным происхождением данных.

## Поведение

- Вход: один непустой MP4/MOV до 200 МиБ. На экране также указаны 180 с, обе ориентации 1920×1080/1080×1920 и 60 fps. Декодирование и фактические лимиты проверяет сервер.
- Fetch не даёт надёжный byte upload progress: передача indeterminate, отдельно от processing; подтверждение приёма — только корректный 202 и UUID. Неопределённый исход POST не повторяется автоматически. Уточняйте состояние по известному ID, а не повторной загрузкой.
- Polling выполняет GET, максимум два повтора при сетевой ошибке; останавливается на done/failed, ошибке и unmount. Ручная повторная проверка не создаёт новое задание. ID хранится в памяти; сохраните его вручную для возврата после закрытия вкладки. Возврат требует ключа.
- 400/401/404/413/415/429/503 и network различимы; 401 освобождает сессию для повторного ввода. Ошибки не показывают raw exception/внутренние пути. Неизвестное состояние не превращается в done/failed.
- JSON проверяется offline схемами K. Jury JSON не расширяется UI-полями. Diagnostics отображаются отдельно, только для того же job_id и текущего public status.
- Защищённый fetch media/preview создаёт Blob URL; фактический поток ограничен не более чем 200 МиБ, даже без Content-Length. URL освобождаются при смене задания/ключа/unmount. Ключ отсутствует в URL; редиректы запрещены.
- По K/A3 preview сохраняет elapsed source time `(PTS-originPTS)*time_base`; seek передаёт точные исходные секунды. Нет расчёта frame_index/fps. Компонентный seek не доказывает VFR/rotation/nonzeroPTS browser correctness: это U после I.
- Событие показывает 1–3 JPEG с исходными timestamp. Unknown, unsupported, partial coverage, source verification, revision и версии остаются видимыми. Пустой список не обещает абсолютной безопасности. K не задаёт связь violation→finding ID: источник не приписывается событию по позиции в массиве; findings и источники показаны отдельно.

## Граница проверки

Компонентные и клиентские тесты проверяют реальное поведение React/Query/client на явных K fixtures и отказах транспорта. В F дополнительно осмотрены начальный экран и synthetic result в браузере при 360/768/1440 px. Это авторская проверка UI; настоящее API, внешний HTTPS, исходное видео/seek и ML readiness не объявляются пройденными. U выполняется только после принятого I.

## Настоящий API в изолированном test profile (для I/U)

```powershell
npm run dev:api-test -- --host 127.0.0.1 --port 5173 --strictPort
```

Этот режим использует настоящий fetch через /api proxy, без frontend fixture transport. На странице видна метка SYNTHETIC API TEST. Выбирайте только искусственные видеопримеры. Для разрешения тестового upload сервер обязан сам сообщить `test_only=true`, `trained=false`, `validated=false`; обычный production not_ready этим режимом не обходится. Компоненты проверки backend и изолированные PostgreSQL/Redis готовятся по backend/README.md в I/U. Production остаётся защищённым trained/validated gate.

Режим только для dev: `vite build --mode api-test` запрещён, как и fixture build. Стандартный production build игнорирует test/demo props; это проверено отдельным тестом. Реальный test-profile API в браузере пока не запускался, зависимость I не принята. Этот запуск не называется ML validation.
