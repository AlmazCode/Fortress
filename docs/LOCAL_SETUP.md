# Установка и запуск на одном ПК

## Windows: основной путь

Установлены Node.js 22.12+ и Git; Python 3.11 при необходимости устанавливает uv. Нужны интернет для первой установки и приватный пакет `source-actions-v1` (111MB, ансамбль75% и обновлённые головы действий). Обработка после установки не использует облачный AI и не скачивает веса. [Состав текущего пакета и проверка](model/SOURCE_ACTIONS.md).

```powershell
powershell -ExecutionPolicy Bypass -File tools/setup_local.ps1 -ModelBundle "D:\FortressModels\source-actions-v1\seed_vote\control"
powershell -ExecutionPolicy Bypass -File tools/select_local_model.ps1 -ModelBundle "D:\FortressModels\source-actions-v1"
powershell -ExecutionPolicy Bypass -File tools/start_local.ps1 -Background
```

`setup_local.ps1` устанавливает исходный контроль из `seed_vote/control/`, а selector проверяет полный пакет и атомарно выбирает его до запуска. Без `-ModelBundle` установщик по-прежнему использует `%USERPROFILE%\FortressArtifacts\training-ready\transition-state-bundle-v1` — это запуск старого контроля. После повторного setup снова выполните selector, если нужен текущий пакет. На текущем ПК пакет находится в `%LOCALAPPDATA%\Fortress\models\source-actions-v1`; на другом ПК его нужно отдельно скопировать вне Git. В публичном репозитории весов нет; для удалённого тестирования жюри они не нужны на компьютере жюри.

Установщик:

1. Создаёт закрытый каталог `%LOCALAPPDATA%\Fortress` с доступом текущего пользователя и SYSTEM.
2. Скачивает uv 0.13.1 из PyPI, проверяя SHA-256 wheel из метаданных; ставит locked зависимости из uv.lock.
3. Скачивает FFmpeg 9.0.2 с gyan.dev, проверяя SHA-256 `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`.
4. Выполняет npm ci и production build интерфейса.
5. Проверяет PyTorch/CUDA и копирует измеренный пакет модели в приватный `models/control-v1`.
6. Создаёт случайный 256-битный ключ. При повторном запуске сохраняет существующий ключ.

[Источник Windows-сборок FFmpeg](https://ffmpeg.org/download.html), [страница сборки](https://www.gyan.dev/ffmpeg/builds/). Пользовательские данные и секреты не загружаются при установке.

По умолчанию используется CUDA. Для CPU укажите `-Device cpu`; численное совпадение с CUDA не подтверждено (известная разница оценки 0.00598 на контрольном ролике). CUDA — измеренный путь этого прототипа. `-Port 8080` меняет локальный порт. `-PrivateRoot` задаёт другое абсолютное расположение вне Git; API и worker должны пользоваться одним приватным каталогом.

## Доступ и остановка

- Web: http://127.0.0.1:8000/
- API: http://127.0.0.1:8000/api/v1
- Ключ/адреса: `%LOCALAPPDATA%\Fortress\jury-access.json`.
- Конфигурация: `%LOCALAPPDATA%\Fortress\local-config.json`.
- Журнал запуска: `logs/service.err.log`; ошибки анализа: `runtime/logs/<job_id>.log`.
- SQLite и приватные оригиналы: `runtime/`. Перезапуск сохраняет завершённые результаты и очередь.

```powershell
Get-Content "$env:LOCALAPPDATA\Fortress\jury-access.json"
powershell -ExecutionPolicy Bypass -File tools/stop_local.ps1
```

Без `-Background` сервис работает в текущем терминале; остановка — Ctrl+C. Повторный запуск на занятом порту останавливается с объяснением, не завершает чужой процесс. Остановка активного анализа фиксирует failed/worker_lost; результаты done сохраняются. Удаление runtime не является штатной остановкой.

Пока Windows-worker работает, сервис запрашивает предотвращение автоматического сна, включая время ожидания загрузок. `/healthz` сообщает `idle_sleep_inhibited: true`, если запрос принят Windows. При остановке worker восстанавливает прежний режим своего потока. Настройки питания и таймер отключения экрана не меняются. Ручной сон, закрытие крышки, отключение питания или сети всё равно прервут доступ: [поведение Windows API](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).

## Что именно запущено

Production-сборка React и настоящий FastAPI доступны на одном origin. SQLite WAL с synchronous=FULL хранит задания и результаты; частичный уникальный индекс допускает одно незавершённое задание. Worker читает очередь на диске. Lease/fencing предотвращают запись устаревшего результата; OS-lock сериализует GPU. Модель работает в отдельном процессе с общим дедлайном 240 секунд; Windows Job Object завершает дерево модели/FFmpeg при закрытии/падении родителя.

Этот native-профиль не использует PostgreSQL/Redis и не заявляет приёмку распределённого профиля. На Windows POSIX directory fsync недоступен: исходный файл fsync выполняется, но гарантия POSIX fsync каталога не заявляется. Не используйте сетевую папку для SQLite/runtime. Одновременно запускайте один API-процесс для одного приватного каталога.

Бинарный GRU-контроль действительно обучен, но качество 80% не достигнуто. Положительный ответ показывает интервалы предполагаемых действий, описания и до трёх исходных кадров на фрагмент. Все наблюдения доступны в UI/diagnostics также для отрицательных роликов. Точный тип/начало нарушения и нормативная применимость не валидированы. [Как выбираются события и что проверено](model/EVENT_REVIEW.md). Режим prototype явно виден; production gate не ослаблен. Старые done-результаты сохраняются: после обновления загрузите видео заново для нового анализа.

## Linux / Compose

Существующий распределённый вариант описан в [backend](../backend/README.md) и [operations](operations/SETUP.md). Ему нужны PostgreSQL, Redis, Docker/WSL2, TLS и отдельная интеграция совместимого событийного release. Наличие исследовательского bundle не открывает его production gate. На текущем Windows-хосте этот путь не запущен и внешний HTTPS не подтверждён.

## Если запуск не прошёл

- Нет модели / SHA не совпал: используйте исходный измеренный bundle, не редактируйте manifest/порог и не переименовывайте случайные веса.
- CUDA недоступна: проверьте NVIDIA driver и соответствие ml-cuda extra; CPU включается только явно.
- Нет npm: установите Node.js 22.12+ с официального nodejs.org и повторите setup.
- Занят порт: проверьте существующий сервис или выберите новый порт через setup.
- Ошибка анализа: сохраните job_id и приватный лог; public API выдаёт только безопасный reason. Не публикуйте медиа/ключ/лог с частными путями в GitHub.
