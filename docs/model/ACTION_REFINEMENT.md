# Обучение с уточнёнными наблюдениями действий

`ml.action_refinement` — локальный исследовательский этап после `ml.small_data`.
Пользователь поручил ассистенту разобрать15 проблемных случаев, уточнить действия
на прежних видео и запустить обучение. Это разрешает эксперимент с такой
разметкой, но не превращает её в человеческую приёмку событийной модели.

## Что считается разметкой

Отдельный versioned JSON содержит `provenance=assistant_sequence_review`,
`human_approved=false`, SHA исходного видео, evidence JPEG с SHA, исходные PTS
и наблюдения по11 классам. Значения: `1` — наблюдаемое присутствие,
`0` — наблюдаемое отсутствие, `-1` — неизвестно. Интервалы в отчёте выбирают
только действительно просмотренные кадры; загрузчик **не заполняет** промежутки.
Пограничные/закрытые корпусом действия остаются неизвестными. Обзор с шагом1с
покрывает всю длительность каждого ролика; выбранные моменты дополнительно
проверены с шагом0.25/0.5с. Это проверка последовательности кадров, а не
непрерывная покадровая разметка или доказательство отсутствия быстрого события.

Классы: работа с плоским предметом, счётчиком/малым настольным устройством,
компьютером, сейфом, сумкой, дверью, письмо; присутствие оператора у станции,
другого человека у стойки, открытая дверь сейфа, сумка на столе.
Точные определения хранятся в overlay. Работа с карточкой не доказывает
проверку личности; клавиатура/крышка не доказывают OS-lock или проводку;
закрытая дверь не доказывает запирание. Тип маленького ключа не выдумывается.

Оригинальные actions/weak labels/verdicts не переписываются. Конфликты
user/organizer сохраняются с объяснением. Основная video loss продолжает
использовать ранее заявленную политику `user_scenario`.

Объектная auxiliary loss использует предоставленную COCO-разметку только на
точно совпавших source PTS development-роликов. Отрицательные object labels
допустимы только благодаря существующим `reviewed=true` и
`confirmation_basis=user_declared_objects_complete` для8 категорий.
Новых human approvals не создаётся. Ключ исключён из обучаемых категорий из-за
отсутствия положительных примеров. Эти цели — присутствие объекта в кадре,
а не обучение детекции bbox или подтверждение содержимого предмета.

## Модель и честное сравнение

Один прежний frozen MobileNetV3-Small ImageNet →576 признаков → один causal
GRU256. Masked mean/max pooling и video head сохраняются; два линейных
auxiliary head используют выход того же GRU. Дополнительные labels не подаются
на вход модели при предсказании. Используются все2fps кадры без прежнего
ограничения64; поэтому контроль `video_only` получает ту же полную
последовательность, тот же seed, архитектуру и аугментацию.

До первого fit фиксируются3 варианта: `video_only`, `actions`,
`actions_objects`; video loss +0.3 action loss +0.15 object loss в последнем.
Каждая auxiliary loss учитывает только известные значения. Вес классов и
нормализация вычисляются только по тренировочным роликам текущего fold.
Класс без положительных или отрицательных тренировочных примеров отключается;
OOF отчёт показывает исключённые из-за отсутствия поддержки наблюдения.
Состояния, редкое письмо и object presence не суммируются в «точность95%».

4 outer ×3 inner grouped folds совпадают с предыдущим этапом. Целое исходное
видео и его scenario family остаются в одной части. Ни targets действий,
ни объектов отложенного fold не участвуют в обучении/нормализации/весах loss.
Две конфигурации на вариант:60epochs/lr0.001/dropout0.35/wd0.01 и
100epochs/lr0.0003/dropout0.5/wd0.05. Train-only Gaussian noise0.03 в
нормализованных признаках одинаков для контроля и assisted моделей.

Основной seed42;137/2026 оценивают чувствительность без выбора удачного seed.
Конфигурация, вариант и порог выбираются только по inner OOF: balanced
accuracy, затем macro-F1, затем BCE. Порог — середины inner OOF scores.
Outer labels используются только для оценки. Решение для финального fit
на36 development роликах фиксируется с SHA **до** scoring4 reserved роликов.
Их labels не собираются даже в auxiliary training tensors.

Данные одной камеры и прежний test уже изучались. Все результаты остаются
исследовательской внутренней оценкой, не новой независимой оценкой95%.
OOF action metrics при фиксированном0.5 — согласие с assistant annotations,
а не человеческая валидация событий. Production model gate не меняется.

## Команды

Артефакты, разметка, кадры и веса находятся вне Git. Создание протокола
проверяет evidence hashes, source PTS, cache/source/label/group binding и
записывает snapshot исходников. Изменение кода/данных требует новой версии
каталога; завершённый эксперимент не перезаписывается.

```powershell
$env:CUBLAS_WORKSPACE_CONFIG=':4096:8'
python -m ml.action_refinement prepare --cache <feature-cache> --overlay <assistant-actions.json> --previous <small-data-experiment> --output <new-experiment>
python -m ml.action_refinement run --experiment <new-experiment> --device cuda
python -m ml.action_refinement evaluate-reserved --experiment <new-experiment> --device cuda
python -m ml.action_refinement infer --experiment <new-experiment> --video <source.mov> --encoder-weights <weights.pth> --encoder-sha256 <sha256> --device cuda
```

Raw inference возвращает диагностический video score и покадровые action
scores с source PTS. Unsupported классы имеют `null`; у `video_only` все action
scores `null`. Это не нормативные findings, откалиброванные интервалы,
human gold или готовый API release. Исходное видео не меняется.

Checks: `python -m pytest tests/ml/test_action_refinement.py tests/ml/test_small_data.py tests/ml/test_video_baseline.py -q`.
Они проверяют exact PTS/unknown masks, нулевой градиент неизвестных целей,
отключение unsupported классов, padding/causality, реальные маленькие fits,
изменение shared GRU от auxiliary loss и изоляцию train/family/inner selection.
