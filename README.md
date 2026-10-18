# Fortress

Локальный AI-прототип для проверки кассового видео: загрузка MOV/MP4, очередь анализа, API и просмотр исходных кадров. Обработка выполняется на вашем ПК без облачных AI-сервисов.

**Текущий статус:** обученная модель подключена в явном режиме прототипа. Средняя точность на отложенных семействах видео — **71,30%**. Цель 80% не достигнута. Сервис показывает интервалы предполагаемых действий, описания и исходные кадры для проверки. Точный тип нарушения и нормативная применимость не подтверждены. [Проверка событий и ограничения](docs/model/EVENT_REVIEW.md).

## Запуск на Windows

Нужны Windows 10/11 x64, Node.js 22.12+ и локальная копия пакета модели `transition-state-bundle-v1`. Установщик подготовит Python 3.11, зависимости CUDA/CPU и FFmpeg. Веса, видео и ключи хранятся вне Git.

Из корня репозитория:

```powershell
powershell -ExecutionPolicy Bypass -File tools/setup_local.ps1
powershell -ExecutionPolicy Bypass -File tools/start_local.ps1 -Background
```

| Что | Адрес / расположение |
| --- | --- |
| Web interface URL | http://127.0.0.1:8000/ |
| API base URL | http://127.0.0.1:8000/api/v1 |
| API key | `%LOCALAPPDATA%\Fortress\jury-access.json`, поле `api_key` |
| Конфигурация | `%LOCALAPPDATA%\Fortress\local-config.json` |
| Очередь, оригиналы и результаты | `%LOCALAPPDATA%\Fortress\runtime` |

Откройте интерфейс → **Настройки** → введите ключ → добавьте видео → запустите очередь. Ключ передаётся только заголовком `X-API-Key` и хранится в памяти вкладки.

Остановка:

```powershell
powershell -ExecutionPolicy Bypass -File tools/stop_local.ps1
```

Подробности, перенос на другой ПК и выбор CPU/CUDA: [локальная установка](docs/LOCAL_SETUP.md). **127.0.0.1 доступен только на этом ПК.** Для удалённого жюри нужен отдельный публичный HTTPS-адрес; он сейчас не настроен.

## API жюри

- `POST /api/v1/analyze` — multipart-поле `file`, ответ `202 {job_id}`.
- `GET /api/v1/jobs/{job_id}` — `processing`, затем `done` или `failed`.
- Все `/api/…` требуют `X-API-Key`; неверный/отсутствующий ключ → `401`.
- Одно незавершённое задание; переполнение → `429`. Общий бюджет — 240 секунд.
- MOV/MP4 до 200 МиБ, 180 секунд, 60 fps, 1920×1080 или 1080×1920.

[Примеры запросов и сдача жюри](docs/JURY_HANDOFF.md) · [OpenAPI](contracts/openapi.yaml).

## Состав проекта

| Каталог | Назначение |
| --- | --- |
| `frontend/` | React / TypeScript, очередь загрузок, результаты и плеер |
| `backend/local/` | Запускаемый на Windows прототип: FastAPI, SQLite, отдельный процесс модели |
| `backend/app/` | Общие API/auth/media и отдельный Linux-вариант PostgreSQL/Celery |
| `ml/` | Модель, локальный inference, инструменты разметки и обучения |
| `rules/` | Правила и нормативные источники; применимость отделена от визуального сигнала |
| `contracts/` | JSON Schema, API и интерфейсы компонентов |
| `infra/` | Опциональная инфраструктура Linux/Compose/TLS |
| `tests/`, `tools/` | Проверки и команды установки/запуска |

[Архитектура](docs/ARCHITECTURE.md) · [текущее состояние](docs/PROJECT_STATUS.md) · [карта документации](docs/README.md).

## Разработка и проверки

```powershell
.venv\Scripts\python.exe -B -m pytest tests/local tests/contracts tests/ml tests/rules -q
npm --prefix frontend test
npm --prefix frontend run build
```

FFmpeg/ffprobe должны находиться в PATH для медиа-проверок; установщик кладёт их в приватный каталог. Тесты распределённого backend требуют отдельные PostgreSQL/Redis и описаны в [backend/README.md](backend/README.md). Tiny/synthetic tests проверяют код, а не точность модели.

Основные ветки объединены с сохранением истории. Генерируемые отчёты, окружения, датасет и секреты исключены из Git и Docker build context. Старый план четырёх разработчиков сохранён в `docs/github-plan/` как история; актуальные инструкции — этот README и `AGENTS.md`.
