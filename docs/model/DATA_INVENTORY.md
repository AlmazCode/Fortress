# D1 — инвентарь материалов и окружения

Проверка выполнена 17 октября 2026 года в отдельном worktree №3. Контракт K:
`2e44bf555ad1a824d92e73770a1ee85d1bf20d0f`, получен из
`codex/fortress-backend`, объединён с действующими GitHub-инструкциями.
База D1: `04058fd48ce01d31bb4231769b9ceeaa739b6b38`.
Перед D1 выполнены 55 контрактных тестов — passed. Это проверка границы K, не
проверка backend или модели.

## Наблюдённые материалы

| Материал | Состояние | Ограничение |
| --- | --- | --- |
| TECHNICAL_SPEC.md | отсутствует в рабочем корне | старый текст не восстанавливается по догадке |
| DATA_AND_TRAINING.md | отсутствует | будущая инструкция будет реализована в M |
| CASE_COVERAGE.md | отсутствует | mapping C01–C15 готовится в D2, нормативы — №4 |
| docs/github-plan/REQUIREMENTS.md | доступен, хэш измерен | действует вместе с WORKFLOW.md |
| исходный Кейс_ForteBank.docx | явно предоставлен локально, хэш измерен | остаётся вне Git |
| contracts/ и общий lock | получены из K, доступность/хэши проверены | taxonomy остаётся draft |
| исходные видео | 42 файла, 292870994 байта | число файлов, не число уникальных/валидных видео |
| изображения | 2621 файл | фотографии сами по себе не temporal dataset |
| annotation-or-metadata | 1219 файлов | включает templates/metadata; human review не установлен |
| служебные/прочие файлы | 24 файла | не выдаются за labels |
| production release | не предоставлен для проверки | наличие случайных weights не означает release |

Корень материалов разметки содержал 3864 учтённых файла, 314266802 байта.
Служебные `.annotation_env`, `.annotation_model`, `.annotation_wheels`
исключены из обхода и перечислены в локальном JSON. Исходные медиа и материалы
разметки принадлежат параллельной работе другого чата; D1 ничего в них не записывает.
Для явно заданного скрытого корня доступен отдельный обход. Лимиты числа файлов и
суммарного хэшируемого объёма закрывают неполный обход явной причиной.

Полный локальный отчёт содержит для каждого материала source/path, тип,
доступность, байты, SHA-256, права и неизвестное. Он хранится вне отслеживаемого
кода: абсолютные частные пути и исходные данные не публикуются. При сканировании
не обнаружено нестабильных/нечитаемых файлов или превышения лимитов.
Хэш финального отчёта: `432959c3b6493d9f7a159db29598059fee068448c5205f9dcbcf96e7202bbcda`.
Это снимок момента аудита: другой чат может дальше менять разметку.

Измеренные SHA-256 отдельных материалов:
- active REQUIREMENTS: `038266dfa556a7277b8beaefb7681ebb360ad779e9c83d4eb277c62e0af02f27`;
- исходный case: `f73a951c87aca9d540076aacc5b4fd8a688810a4ec827b1a382512c770d278a0`;
- taxonomy K: `8e52be05f17cd05ab2c26c4932d6db27562282e062e00278290a361be7555c84`;
- uv.lock: `bfd1aa793c8576aa388681c3b84de27838a0c4e96034997bd7ed81b8a7dd412a`.

## Наблюдённое окружение

Python 3.11.14; torch 2.14.1+cpu; torchvision 0.29.1+cpu; NumPy 2.4.6;
PyAV 17.1.0; Pillow 12.3.0. Версии установлены из общего неизменённого uv.lock.
Windows AMD64, total RAM 16707756032 байта, available RAM 4988223488 байт
на момент отчёта. Доступная RAM — меняющийся снимок, не заявленный бюджет обучения.
CUDA этой сборке недоступна, build_version=null; VRAM не измерена.
Это не доказывает отсутствие физического GPU и не проверяет другой training PC.

Реальный CPU self-test: MobileNetV3-Small `features`, weights=None,
spatial average pooling: `[1,3,224,224] → [1,576]`, конечные значения.
Случайная инициализация явно test-only; веса не скачивались.
Обучение, fine-tuning, GPU search и оценка датасета не запускались.

## Воспроизведение

Из проверенного Git-корня, Python 3.11:

```powershell
uv sync --locked --group test --extra ml --no-build
python -m pytest tests/ml/test_preflight.py -q
python -m ml.preflight --project-root . --data-root "$env:FORTRESS_VIDEO_ROOT" --annotation-root "$env:FORTRESS_ANNOTATION_ROOT" --case "$env:FORTRESS_CASE_FILE" --self-test --output "$env:FORTRESS_REPORT_PATH"
```

Переменные задают существующие локальные материалы и **новый** путь отчёта вне Git.
`--output` не перезаписывает существующий файл. Без data roots CLI тоже работает
и честно сообщает data_missing/annotation_missing. Без `--self-test` он пишет
not_run, а не passed. Отдельный `--release-root` учитывает кандидаты release,
не загружая pickle или weights. Декодирование/дедупликация/схемы labels/split
проверяются следующими этапами, не по одному расширению файла.

Для целевого RTX 5060 8 ГБ / RAM 16 ГБ / Ryzen 5 8400 запустить тот же CLI
на том ПК после согласования CUDA-окружения с №1/№4. Он печатает фактические
build/device/available RAM/VRAM. Текущий CPU lock самостоятельно не заменяется
на локальную несовместимую CUDA-сборку; доступ к другому ПК сейчас не требуется.

## Границы готовности

D1 tools_ready=true; наличие файлов наблюдено. Annotation files present=true,
annotation_missing=null (неизвестно до проверки), annotation_review=unverified.
License state=unknown, target hardware_unverified=true, training_ready=false.
Human-approved objects, temporal labels, split и model readiness не подтверждены.
Дополнительные причины и следующие этапы перечислены в MISSING_MATERIALS.md.

Проверки D1: 9 targeted tests passed, финальный inventory+self-test CLI exit 0.
Полные команды с локальными путями, отчёт и точный SHA кандидата сохраняются в
неотслеживаемой контрольной точке и журнале №3. Runtime/API/ML quality не заявляются.
