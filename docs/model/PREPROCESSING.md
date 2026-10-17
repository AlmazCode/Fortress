# Общий preprocessing, PTS windows и кэш — M1

PreprocessConfig(version=letterbox-imagenet-v1) задаёт один путь для cache/train/inference: uint8 RGB → CCW quarter-turn → letterbox224 с чёрным padding → float32 CHW /255 → ImageNet mean(0.485,0.456,0.406), std(0.229,0.224,0.225). Grayscale расширяется до RGB; alpha/float/BGR/неизвестные версии не угадываются. Не используется default torchvision center crop. Baseline — один полный decoded frame, без дополнительных views и без подмены global sequence annotation crop.

preprocess_image возвращает tensor[3,224,224], valid_pixel_mask и transform to_original. Сохраняются фактические целочисленные resize dimensions и отдельные scale X/Y: rounding не теряется. box_to_source принимает bbox только в real content, padding не превращается в source evidence. Четыре поворота/нечётные размеры/normalization/channel order/inverse проверены тестами.

## Время и labels

labelled_windows использует D4 source PTS/time_base/origin, scene/split и размер32/2fps/stride16 по умолчанию. Слоты хранят original source path/hash/geometry. При назначении labels используется actual timestamp выбранного source frame, не только target grid. Сохраняются отдельные image_mask, padding_mask и class known_mask[T,C].

Reviewed present даёт target1/masktrue; reviewed complete visible absent_verified даёт target0/masktrue. Unreviewed/pseudo/unknown/needs_review, несуществующий sample и padding имеют maskfalse. Нулевое значение target при maskfalse — заполнение массива, не negative. Отрицание для одного actor не означает глобальное отсутствие action; action score не actor ID.

merge_scores объединяет overlap по (video,scene,split,sourcePTS). Выход — mean по фактически доступным class scores, counts и score_mask. Ненаблюдённый класс остаётся null. Разные source hashes/partitions одного видео или один PTS в разных сценах отвергаются, а не смешиваются. Padding и отсутствующие images не участвуют, включая NaN в padding slots.

## CacheSpec и источники

build_cache/load_cache — API подготовки numeric feature cache. CacheSpec содержит полные SHA-256 source/dataset/split/annotation/taxonomy/encoder/preprocessing/config/windows, ordered class IDs, partition и test_only. Любое изменение ключевого поля исключает reuse старого marker. Задачи/окна/классы ограничены; hidden tensor shape fixed576.

build_cache требует source_root и проверяет actual original SHA до reuse и после построения. Смена bytes при старом manifest даёт отказ: сначала обновить manifest/spec, затем новый output. Frame producer полностью декодирует original через D4 iterator, не использует PNG crop; проверяются source dimensions/rotation/PTS keys. Завершённый matching cache не запускает encoder заново, но original SHA всё равно проверяется.

Encoder — явно frozen torch module. Hash вычисляется по реальным именам/shapes/dtypes/bytes state_dict, descriptor содержит state hash/device/weights/feature_dim/test_only. Проверяется FP32 finite[1,576] output и отсутствие mutation encoder state. Неизвестные dtype/веса/подмена descriptor/device/frozen state отвергаются. Prepared local ImageNet encoder нужен для real features; weights=None/test-only не становится production encoder.

Cache completeness отдельно от dataset/model readiness. production_cache_ready=false: один кэш не подтверждает labels, rights, independent holdout или обученную модель. Реальный feature cache пользовательского датасета и pretrained weights здесь не заявлены. Tiny smoke encoder случайный, source kind synthetic.

## Numeric format и пределы

Каждое окно — NPZ с пятью numeric arrays: features[T,576] float32, targets[T,C] float32, known_mask[T,C] bool, image_mask[T] bool, padding_mask[T] bool. Перед np.load проверяются ZIP entries/count/storage type, ограниченный NPY1.0 header, exact shape/dtype/byte count. Object arrays не принимаются, allow_pickle=False всегда. [NumPy load API](https://numpy.org/doc/stable/reference/generated/numpy.load.html) и [bounded header API](https://numpy.org/doc/stable/reference/generated/numpy.lib.format.read_array_header_1_0.html) сверены с установленным runtime.

По умолчанию ≤2048 windows, ≤1024 samples/window, ≤256 classes, ≤100000 unique source frames, encoder state≤64MiB, array file≤8MiB, source≤2GiB, весь cache≤2GiB. Original frame≤16777216 pixels. Это software limits, не измерение peak RAM/VRAM или OS sandbox. Cache загрузка читает проверенные arrays в RAM; при больших наборах выбрать меньшие partitions/generations и допустимый byte limit.

Каждый file hash и cache.json входят в completion marker. Запись в private staging публикуется только целиком. Реальная partial write проверена: нет готового destination/marker, originals не меняются. Полный cache проверяется на повторе. Повреждённый/foreign/неполный existing output не перезаписывается и не принимается: реконструировать новую generation из source manifest и compare loaded arrays. Старые данные остаются для диагностики. Resume training checkpoint — отдельный M2 механизм.

load_cache проверяет предоставленный immutable CacheSpec и все derived bytes; он может читать переносимый snapshot без media. Он не утверждает, что любые внешние файлы по старому пути всё ещё те же. Перед raw-source reuse проверку делает build_cache; real-training CLI должен подтвердить текущий data readiness/source context.

Общий `ml.cli cache` пересчитывает data QA по actual originals/assets/canonical labels/context/taxonomies и сохраняет optional readiness_binding. Его четыре dataset/split/annotation/taxonomy fingerprints и полный report hash входят в cache config; tampering даже с пересчитанным artifact marker отвергается. QA dataset_revision отдельно включает весь annotation context, тогда как CacheSpec.dataset_sha256 означает immutable manifest content. Legacy API caches без binding допустимы для tiny synthetic smoke; future real training требует bound data_ready, explicit instruction flag, real pretrained cache и source_root для повторной проверки original SHA. Production_cache_ready по одному feature cache по-прежнему false.

## Наблюдённые проверки

Targeted M1 —28 tests passed. До публикации тесты воспроизвели и закрыли JSON tuple/list inconsistency на reuse и старый cache при изменённом original. Invalidation каждого SHA/class order/partition/test provenance, corrupted/foreign cache, source mutation, annotation crop, header/object/numeric/mask errors и partial-write recovery покрыты.

Отдельный CPU smoke реально использовал MobileNetV3-Small features(weights=None)+spatial mean на четырёх tiny source frames: два cache windows [32,576], четыре synthetic known class labels, production_cache_ready=false, training_ran=false. Это code/shape/cache проверка, не качество bank actions и не supervised обучение. Полные локальные команды/артефакты и candidate SHA — в журнале №3/локальном checkpoint.
