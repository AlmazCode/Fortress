# Протокол будущей независимой ML-оценки

Версия протокола: **event-boundary-v1**, базовый tolerance **0.5 секунды**. Зафиксирован до любой реальной ML-оценки этого поставляемого инструментария. Здесь проверены вычисления на synthetic CPU, а не качество модели или юридическая применимость правил.

## Зафиксировать данные и модель

Сохранить точные content hashes manifest/split/canonical annotations/taxonomy/preprocessing/cache/checkpoint, seed и runtime. Dataset version не заменяет SHA. Весь source/scene/canonical/duplicate component относится к одному partition; near-duplicate candidates группируются консервативно. Объём и30/10 не выдумывать: считать actual videos/groups/known labels.

Train обновляет weights только на train. Dev используется для выбора checkpoint/порогов и заранее объявленного протокола. Independent final должен содержать ранее не виденные независимые видео/ракурс, что отдельно проверяет человек; scene IDs или разные имена файлов не доказывают независимость. Evidence reviewer/manifest_sha256/final_viewpoint_independent/previously_unseen связывается с точным manifest. После назначения final его нельзя демотировать обычным re-split или назначать из уже использованного train/dev.

После фиксации checkpoint и thresholds не менять их по результатам final. Если final использован для настройки, этот запуск не independent validation; нужен новый неиспользованный final с проверенным происхождением. Любое изменение classes/annotation/split/checkpoint/protocol invalidates прежнюю согласованную оценку. Нельзя удалять неудобные errors/unknown samples без объявленного правила и нового отчёта.

## Verdict metrics

Реальные цели: verdict **accuracy≥0.80**, **balanced accuracy≥0.80**, **macro-F1≥0.80** на независимых видео. До будущей оценки все три — **not evaluated**, не ожидаемые значения в model card.

Action scores отдельно от verdicts: для последних нужны reviewed case verdict truth и фактический результат правил. Их нельзя вывести из bbox или назначения роли актёру. При отсутствии verdict labels/report `verdict_metrics=null`; это закрытый validation gate, не100% accuracy. Normative applicability/источники проверяет R и человек.

Реализация `binary-covered-v1` выдаёт:

- total/known_truth, positive/negative support, covered и coverage;
- TP/TN/FP/FN/absolute_errors, unknown_truth/unknown_prediction_on_known/unknown_rate;
- accuracy по covered known observations и отдельно accuracy_over_all_known;
- balanced accuracy — среднее recalls классов с поддержкой; macro-F1 — среднее обеих binary classes, undefined F1=0.

Unknown predictions не превращать в negatives или автоматически исключённые «лёгкие» примеры. FP/FN считаются по covered known pairs; непокрытая known часть показана отдельно, all-known accuracy не позволяет скрыть её из знаменателя. Сохранить абсолютные counts по video/scene/class/case, disagreement/visibility/review provenance. Высокая covered accuracy при низком coverage не доказывает пригодность.

## Event metrics

Сопоставлять события только внутри одного video_id/scene_id/class_id. Событие — положительный interval `[start_sec,end_sec)` в исходных source seconds. Требуются reviewed comparable intervals и известные границы; unknown/occluded/unreviewed не negative gold. Временное отображение должно быть обратимо к actual source PTS/time_base/origin, включая VFR/rotation. Actor/relations nullable без отдельной подтверждённой идентификации.

Матч существует, если **обе** границы отличаются не более чем на0.5с. Maximum-cardinality one-to-one matching не позволяет нескольким predictions получить один truth TP. Несопоставленные известные predictions → FP, truths → FN; считать precision/recall/F1/support/число unknown events. Если denominator пуст — null, не1. Предсказания вне reviewed comparable coverage не считать ложными отрицаниями по отсутствию разметки.

При ином заранее объявленном tolerance (допустимый параметр CLI) записать численное значение и версию protocol до final. Threshold document связывает protocol hash/значение с checkpoint/dataset/taxonomy; поздняя подмена отвергается. Default0.5с не утверждает достаточную точность для всех быстрых передач:2fps не гарантируют их наблюдаемость, small-object/occlusion limits отдельно исследуются на реальных данных.

## Выполнение и отчёт

Команды scoring/dev thresholds/final metrics — [CLI.md](CLI.md). Score input содержит полный grouped manifest/hash/partition, bool/null labels, probabilities/null и отдельные verdicts/events. Не заполнять отсутствующие verdict/event truth из scores. Человеческую ревизию truth сохранить до запуска; pseudo proposals не gold.

В итоговый report включить весь fixed configuration, model/hash/data lineage, counts/errors/coverage/unknown и event P/R/F1, реальные gaps поC01–C15, размер всего FP32 encoder+GRU+head и всех моделей, actual hardware/runtime. Quality, budgets и latency/RAM/VRAM — разные проверки. Synthetic smoke может подтвердить arithmetic/formats/shape/resume, но не реальную цель≥0.80 или production taxonomy budget.

Перед production требуется независимый review реальных результатов с привязкой к точным hashes, final human-reviewed taxonomy, права/наблюдаемость/источники и совместимость rules. Пустой/untrained/test-only/неполный release остаётся model_not_ready. Интеграция с backend/правилами проверяется после принятого I; текущий пакет документов её не подтверждает.
