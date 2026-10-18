# Ансамбль трёх seeds — локальный прототип

Новый [пакет действий](SOURCE_ACTIONS.md) содержит этот ансамбль без изменения clip verdict и заменяет только прошедшие gates визуальные головы. Сам `seed-vote-v1` сохранён для возврата; описанные ниже его метрики и SHA остаются прежними.

После проверки оригинального ТЗ снято ошибочное ограничение прежних экспериментов «одна CNN + одна GRU, до12MB». ТЗ такого лимита не содержит. Это позволило проверить заранее фиксированное голосование трёх существующих seed-контролей42/137/2026, без подбора весов или нового порога по outer-ответам.

## Результат

36 development-источников, четыре прежних grouped outer folds. Каждый участник использует свой уже сохранённый inner-порог; решение — не менее двух положительных голосов из трёх. Четыре зарезервированных источника исключены из fit/selection; они исторически уже просматривались и не являются новой независимой приёмкой.

| Метрика | Прежняя подключённая модель seed42 | Среднее прежних трёх одиночных seeds | Ансамбль |
| --- | ---: | ---: | ---: |
| Accuracy | 72,22% (26/36) | 71,30% | **75,00% (27/36)** |
| Balanced accuracy | 64,88% | 64,72% | **68,73%** |
| Macro F1 | 65,38% | 65,29% | **69,75%** |
| Ложные тревоги /13 отрицательных | 8 | — | **7** |
| Пропуски /23 положительных | 2 | — | **2** |

Это одна дополнительная верная классификация относительно подключённого seed42. Лучший одиночный seed2026 тоже имел75%; выбирать его по outer-ответам как новую настройку не стали. Метод голосования и gate зафиксированы до вычисления его результата. Повторные исследования тех же development folds не являются независимой проверкой; устойчивый прирост,80%/95% и качество нового ракурса не подтверждены.

Качество событий и нормативных выводов этим экспериментом не повышается автоматически. Общие action/state heads оставлены от прежнего пакета; их наблюдения unreviewed. Показанный кадр22,5с в первом ролике не является доказательством подмены денег.

## Пакет и исполнение

Версия `three-seed-vote-extension-v1`, model SHA `8075af005222a5de4eccfceac9d24a8f9ee2e50a8eff9c2b6b153d72993f2dad`. Пакет17 351 645байт. Исходный control сохранён целиком в `control/`, включая весаSHA `c5c673f54cabb1e675f058950454a4f431d39aae5fa656c26cc79f7853b0a077`; seed42 использует прежний fitSHA `7349746e3807545ac493780a63525364554738a8830d56f873cb4658fb854085`. Дополнительные spatial/GRU головы обучены только на тех же36 источниках с seeds137/2026. Из новых загрузок API ничего не обучается.

Один общий MobileNet-энкодер вычисляет исходные признаки; дополнительные головы используют их повторно. Нового CNN-прохода для каждого участника нет. Финальный порог каждого seed — прежние0,2965284585952759; итоговый score — доля положительных голосов, итоговый порог0,5. Score не является калиброванной вероятностью.

`ml.seed_vote` проверяет coverage/fold/identity трёх OOF-предсказаний. `ml.seed_vote_infer` проверяет SHA протокола, отчёта, исходного control manifest и дополнительных весов, точный состав development и улучшение всех трёх метрик. Готовый пакет не требует тренировочных кэшей. Старый backend отвергает новый version вместо случайного запуска одного участника. Native readiness проверяет все файлы ансамбля, включая дополнительные головы; `prototype`, `trained=true`, `validated=false`, `production_ready=false` сохраняются.

Протокол `a20193571fb36036bf97198089ffaf68f54ee2d7187eff661876e5859a9c5705`, отчётSHA `390702c806ac342b43782ad5d46426f3b876c3131d834a79a021a7a3d161fbb7`. Агрегаты: [EVENT_TRAINING_RESULTS.json](EVENT_TRAINING_RESULTS.json). Негативные предыдущие варианты: [TEMPORAL_EVENT_TRAINING.md](TEMPORAL_EVENT_TRAINING.md).

## Воспроизведение и подключение

Все пути — приватные каталоги вне Git. Для оценки нужны исходные `object-stage-v2/cv_report.json` и `temporal-operations-stage-v1c/protocol.json`.

```powershell
.venv\Scripts\python.exe -B -m ml.seed_vote --root D:\FortressData\training-ready --output D:\FortressRuns\vote-new
```

Для экспорта требуются исходные object-stage checkpoints и full-data fits для seeds42/137/2026, все с exact36 development IDs и `uniform` mode. `object_events.Experiment.fit` создаёт их с прежним протоколом; сохраните `final_members.json` с `reference_protocol_sha256`, `development_ids` и списком `members` (seed,fit,fit_sha256). Существующие checkpoints не перезаписываются. Удерживайте общий GPU lock сервиса. Seed42 экспорт берёт из явно заданного исходного `final_reference.json`, сохраняя подключённый контроль точно.

```powershell
.venv\Scripts\python.exe -B -m ml.seed_vote_infer --experiment D:\FortressRuns\vote-new --reference D:\FortressData\training-ready\object-stage-v2 --base-bundle D:\Models\control-v1 --control-reference D:\FortressData\training-ready\transition-state-stage-v1\final_reference.json --output D:\Models\seed-vote-v1
```

На уже установленном ПК остановите сервис, выберите проверенный пакет и запустите снова:

```powershell
powershell -ExecutionPolicy Bypass -File tools/stop_local.ps1
powershell -ExecutionPolicy Bypass -File tools/select_local_model.ps1 -ModelBundle D:\Models\seed-vote-v1
powershell -ExecutionPolicy Bypass -File tools/start_local.ps1 -Background
```

Selector проверяет пакет на CPU до изменения конфигурации, сохраняет приватную резервную копию config и атомарно меняет только `bundle_root`. Работающий сервис менять запрещено. Ключ и runtime остаются прежними. Для возврата выберите старый `control-v1` тем же способом. На новом ПК сначала выполните `setup_local.ps1 -ModelBundle D:\Models\seed-vote-v1\control`, затем selector для корня нового пакета.

## Проверки

На настоящих MOV001/010 компоненты автономного пакета совпали с тренировочным кэшем с максимальным расхождением0,000002325; выводы положительный/отрицательный сохранены. Это функциональная проверка знакомых источников, не новый benchmark. CPU/CUDA parity на всём наборе не подтверждена.

После подключения проверен настоящий API: MOV001 →202/processing/done,20,625с, три карточки10,5/15,5/22,5с; MOV010 →no_violation,11,937с, карточек тревоги нет. Проверены genuine JPEG, модельный SHA в diagnostics и75% в readiness; нормативные findings пустые. Эти два времени не являются средним по42 видео. Приватные результаты находятся в `verification/seed-vote-api-v1`; ключи и медиа в Git не добавлены.

Финальные проверки кода:480 Python tests и29 subtests,152,76с,exit0; frontend144 tests и typecheck/production build,exit0. Отдельно83 targeted tests прошли до добавления selector/readiness-тестов. Software checks не измеряют качество модели.
