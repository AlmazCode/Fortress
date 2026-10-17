# Fortress — шаблон model card

**not trained / not validated / production not ready**

Это шаблон будущей поставки. Заполнить только после наблюдённых запусков и проверки фактических hashes. Незнакомые поля оставить null/unknown; software smoke не переносить в показатели качества.

| Поле | Текущее значение шаблона |
| --- | --- |
| Release version / полный manifest SHA | null |
| Intended use | software review; production заблокирован |
| Backbone | MobileNetV3-Small.features + spatial mean576 |
| Temporal model | causal GRU1×256 → LinearC, C production неизвестно |
| Production encoder weights | требуется локальный IMAGENET1K_V1, полный доверенный SHA не предоставлен |
| Frozen baseline / preprocessing | frozen encoder/BatchNorm; RGB letterbox224/ImageNet normalization,1view,2fps,window32,stride16 |
| Dataset/split/annotations/QA revisions | null; нужны реальные reviewed temporal данные |
| Taxonomy | текущие project candidate actions/objects/states draft; official25 IDs не предоставлены |
| Rules version/applicability/sources | unknown; проверка R и человека не завершена |
| Other-PC Python/CUDA/RAM/VRAM | unverified; текущий общий lock CPU-only |
| Training run/checkpoint/config/seed/RNG metadata | null для real training |
| Independent final viewpoint/unseen evidence | отсутствует для реального validation |
| Real verdict accuracy/balanced accuracy/macro-F1 | null / not evaluated; цели≥0.80 |
| Support/TP/TN/FP/FN/errors/coverage/unknown | null для реальных данных |
| Event precision/recall/F1/support/unknown | null; заранее event-boundary-v1/tolerance0.5с |
| Production full FP32 model≤12MB / all models≤35MB | not evaluated для production taxonomy |
| Real latency/RAM/VRAM/performance | not evaluated |

## Наблюдённое software evidence

Точные commits и exit codes — [DEV-3](../github-plan/status/DEV-3.md). Tiny generated CPU проверяет raw PTS/rotation/masks/features576/GRU shapes/masked loss/AdamW/resume/evaluation arithmetic/export/import/rollback. Random encoder имеет test-only provenance, не ImageNet weights. Artificial reviewed-format labels не human gold. Полный real train/fine-tuning/GPU search/реальная dataset ML-оценка не запускались.

Для двух smoke classes измерен весь model.pt6385243 bytes (6.385243MB,6.089442MiB): encoder tensors3756752 bytes, GRU/head2564104, total tensors6320856. Training checkpoint с optimizer11543771 bytes хранится отдельно. Это пример измерения конкретного smoke artifact, не размер неизвестного production release или других будущих моделей.

## Предназначение и ограничения

Action score — оценка модели по наблюдениям, не actor ID, принадлежность партии, полномочия, сумма или юридический вердикт. Object bbox не action. Отдельный object detector/four-view/face recognition/actor matching этим baseline не вводятся. Actors/relations остаются nullable/unknown без подтверждений.

Без независимой observability visibility остаётся unknown; низкий score не доказывает отсутствие.2fps/32sample windows могут пропустить быстрые действия; small objects/occlusion/монтаж требуют реального исследования. Raw inference не обнаруживает сцены автоматически, reviewed cuts передаются отдельно. Unknown/coverage=none не no_violation; decode/OOM/hash/deadline errors не clean results.

## Материалы, которые ещё нужны

Реальные права/источники originals, reviewed objects/actions/states/scenes/explicit negatives, подтверждённая taxonomy/official IDs при предоставлении, independent previously unseen final, source application/context и normative materials, локальный pretrained state_dict с доверенным SHA, проверенный другой ПК/runtime. Пользовательский case доступен по D1 snapshot; остальные недостающие приложения не выдумывать. Текущая annotation сборка другого чата здесь не оценивалась.

После отдельного поручения: actual preflight/QA → real train/resume → dev calibration → independent final metrics → human review → whole FP32 budget/performance → immutable export/hash/transfer/import → проверка backend/rules I/E. До этого сохранять not trained/not validated/model_not_ready503.
