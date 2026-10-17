# Передача №3: программные инструменты готовы к review

Software candidate **85e5b2162d86e95d831ce9fb7ef2c7578b9ee92d**, ветка `codex/fortress-no3-ml`, репозиторий AlmazCode/Fortress. Позднейшие documentation commits записаны в [журнале №3](../github-plan/status/DEV-3.md). Публикация ветки не означает acceptance главным или production readiness.

## Проверено

`python -m pytest tests/contracts/test_schemas.py tests/ml -q` → exit0, **269 passed in137.76s**, no skips. Общие CLI cache/train/resume/dev scoring/thresholds/final diagnostics/export/import/activation/rollback/infer и13 --help проверены в subprocess/in-process тестах. Actual native PyAV/Pillow/NumPy/PyTorch операции выполнены на synthetic CPU.

Standalone `python -m ml.cli smoke --output-dir <new-directory>` → exit0: три generated видео, grouped train/dev/final, actual PTS/PNG/tasks/canonical labels, три feature caches, CPU optimizer1+resume2, dev-only thresholds, final diagnostics, full FP32 measured export/import и unknown timeline. Summary/model/package SHA сохранены в журнале. Readiness data/trained/validated/production=false, verdict_metrics=null, timeline coverage=none.

Общий набор также покрывает extraction/COCO roundtrip/annotation QA и regression D3 re-split: прежний independent_test не возвращается в train/dev, поздний выбор final отвергается, transitive source/near groups сохраняются. Исправленный D3 — **54493fcd10b1824356f82df3f6bbbfadc1ea5ffc**, вместо отклонённого d0b9704.

## Повторный review D3 для №1

После fetch ветки №1 `codex/integration` и `codex/fortress-backend` остаются на **bfff45447f74a5263b1d728e05ebb41490d91b58**. Последний опубликованный STATUS/DEV-1 проверяет старый **d0b9704b005e85675191baf0c0737b5d6da8cc49**; нового замечания к54493fc нет. Оба54493fc и итоговый M85e5b21 присутствуют в ветке №3 и отсутствуют в ancestry integration. Это кандидаты review, не accepted.

Сопоставление замечаний с уже пройденными проверками в [test_splits.py](../../tests/ml/test_splits.py):

| Сценарий | Поведение исправленного D3 | Регрессия |
| --- | --- | --- |
| Повторный split без повторного final flag, seed17 и99 | Previous final входит в reserved holdout; старые final IDs не возвращаются ни одним train/dev selector | `test_resplit_without_final_flag_preserves_holdout_for_every_selector` |
| Связанные source/точные дубли/near candidates транзитивно | Вся компонента остаётся final после re-split с seed99; новая связь final↔train отвергается до output | `test_resplit_preserves_transitive_final_source_duplicate_and_candidate_groups` |
| Повтор без near-candidate sidecar | Компонента сохранена в manifest.group_id и не распадается на partitions | `test_near_components_persist_when_resplit_caller_omits_candidate_sidecar` |
| Другая final selection после назначения split | Новый final из ранее train/dev отвергается; повтор прежнего final idempotent | `test_final_selection_is_immutable_after_assignment_and_repeated_flags_are_idempotent` |
| Реальный CLI, независимые и связанные источники | Seeds17/99 сохраняют final1/final3; training/threshold_calibration исключают все final IDs; rejected reselection не пишет output, originals/первый bundle неизменны | `test_real_cli_resplit_retains_final_and_rejects_reselection_without_output` |

Эти API/CLI регрессии уже входят в зафиксированный общий run **269 passed**, exit0, на M85e5b21. При повторной передаче проверена неизменность splits.py/test_splits.py относительно54493fc и всех ML/K/test sources относительно85e5b21 через `git diff --exit-code` →0. Успешный набор повторно не запускался: новых исходников, контрактов и воспроизводимого дефекта №1 не появилось. Для review diff исправления: `git diff d0b9704 54493fc -- ml/data/splits.py tests/ml/test_splits.py`.

## Что передать другому ПК

- Точный принятый code commit/общий lock/контракты, [CLI.md](CLI.md) и [TRAINING.md](TRAINING.md).
- Originals/полный manifest+audit+split, raw PTS index/scenes, task assets и versioned canonical annotations/taxonomies с hashes.
- После реальной подготовки — локальный IMAGENET1K_V1/full trusted SHA, actual preflight и freshly bound reviewed QA; никаких runtime downloads.
- После будущего обучения — immutable checkpoint/config/RNG lineage, dev thresholds/fixed [evaluation protocol](EVALUATION.md), independent real metrics и честную [model card](MODEL_CARD.template.md).
- После review — полный package/K manifest+каждый SHA, измерение encoder+GRU+head/all-model budget, совместимые taxonomy/rules/runtime, previous release для atomic rollback.

Другой ПК сейчас не доступен и не объявляется проверенным. Текущий lock CPU-only; CUDA/перенос между torch builds ещё требуют проверки. Full training/real data ML evaluation/цели≥0.80/production taxonomy budget/performance не выполнены.

## Остаток E

**E blocked: требуется принятый I.** Последняя проверенная опубликованная integration — bfff45447f74a5263b1d728e05ebb41490d91b58; она ещё содержит rejection старого D3 и ожидание M/O. Новый D3 туда не включён. D1/D2 приняты ранее, остальные результаты №3 — review.

После I получить его точный SHA, проверить ports/ready503/failed-vs-unknown путь в сочетании с backend/rules и воспроизвести handoff-команды на принятом составе. Не объявлять HTTP/Docker/external HTTPS/реальное training quality выполненными по одному local CPU smoke. Материалы E подготовлены заранее; окончательная integration verification не выполнена.

Машиночитаемая запись текущей подготовки — [ACCEPTANCE.json](ACCEPTANCE.json). Её state=blocked относится к E, software checks pass относятся к кандидату №3. Main/shared lock/backend/данные другого чата этим исполнителем не изменялись.
