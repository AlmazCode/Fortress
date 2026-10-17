# Передача №3: программные инструменты готовы к review

Software candidate **85e5b2162d86e95d831ce9fb7ef2c7578b9ee92d**, ветка `codex/fortress-no3-ml`, репозиторий AlmazCode/Fortress. Позднейшие documentation commits записаны в [журнале №3](../github-plan/status/DEV-3.md). Публикация ветки не означает acceptance главным или production readiness.

## Проверено

`python -m pytest tests/contracts/test_schemas.py tests/ml -q` → exit0, **269 passed in137.76s**, no skips. Общие CLI cache/train/resume/dev scoring/thresholds/final diagnostics/export/import/activation/rollback/infer и13 --help проверены в subprocess/in-process тестах. Actual native PyAV/Pillow/NumPy/PyTorch операции выполнены на synthetic CPU.

Standalone `python -m ml.cli smoke --output-dir <new-directory>` → exit0: три generated видео, grouped train/dev/final, actual PTS/PNG/tasks/canonical labels, три feature caches, CPU optimizer1+resume2, dev-only thresholds, final diagnostics, full FP32 measured export/import и unknown timeline. Summary/model/package SHA сохранены в журнале. Readiness data/trained/validated/production=false, verdict_metrics=null, timeline coverage=none.

Общий набор также покрывает extraction/COCO roundtrip/annotation QA и regression D3 re-split: прежний independent_test не возвращается в train/dev, поздний выбор final отвергается, transitive source/near groups сохраняются. Исправленный D3 — **54493fcd10b1824356f82df3f6bbbfadc1ea5ffc**, вместо отклонённого d0b9704.

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
