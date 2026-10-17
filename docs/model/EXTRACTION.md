# Извлечение кадров и клипов — D4

Инструменты работают локально и читают исходники без изменения. Проверены на tiny synthetic FFV1/MKV и MPEG4/MP4. Это подготовка артефактов, а не разметка, оценка модели или готовый temporal dataset. Исправленный D3 сохраняет final-группы при re-split; extraction сохраняет partition каждого источника.

## Реальные команды

Из корня checkout с установленным locked ML environment. Переменные sourceRoot/workRoot указывают на выбранные локальные каталоги вне Git; manifestPath — результат D3 split, videoId берётся из него. Создать workRoot заранее, не использовать папку с чужими артефактами.

```powershell
$python = '.venv/Scripts/python.exe'
$manifestPath = Join-Path $workRoot 'split.json'
& $python -m ml.data.pts_index --manifest $manifestPath --source-root $sourceRoot --video-id $videoId --output (Join-Path $workRoot 'index.json')
& $python -m ml.data.scenes --index (Join-Path $workRoot 'index.json') --cut-sec 1.3 --output (Join-Path $workRoot 'scenes.json')
& $python -m ml.data.extract_frames --index (Join-Path $workRoot 'index.json') --scenes (Join-Path $workRoot 'scenes.json') --source-root $sourceRoot --output-dir (Join-Path $workRoot 'frames') --rate 2 --crop 2 4 30 22
& $python -m ml.data.extract_clips --index (Join-Path $workRoot 'index.json') --scenes (Join-Path $workRoot 'scenes.json') --source-root $sourceRoot --output-dir (Join-Path $workRoot 'clips') --rate 2 --size 32 --stride 16
```

Эта конкретная cut/crop-конфигурация воспроизведена на synthetic 32×24; для своего видео выбрать реальные cuts и crop либо убрать необязательные параметры. Все четыре модуля имеют --help. Только человек, проверивший все границы сцены, указывает --reviewer; это сохраняемое утверждение проверяющего, а не автоматическое подтверждение. Без него сцены unreviewed. Отсутствие cut не доказывает отсутствие монтажа.

## Время и сцены

Индекс сверяет SHA и метаданные с K manifest, полностью декодирует видео и сохраняет каждый source_pts с time_base и origin_pts. Ноль соответствует первому декодированному PTS; timestamp_sec=(source_pts-origin_pts)×num/den. Преобразование обратимо; nominal FPS и номер кадра не заменяют время. Отсутствующий/nonmonotonic PTS, изменение source/hash/geometry, неизвестный контейнер или превышение decode limits дают отказ. Native loop budgets не являются OS process isolation.

Границы сцен задаются явно в zero-based секундах и сдвигаются к первому существующему PTS не раньше requested cut. Сохраняются обе границы — requested и decoded. Scene intervals полуоткрытые [start,end), покрывают источник без пересечений. Окна/клипы не переходят известную границу сцены или partition. Пропущенные неразмеченные монтажные склейки остаются ограничением до scene review.

## Частота и окна

Частота configurable: --rate для object PNG может отличаться от temporal rate и входит в config/hash. Базовые 2 fps не гарантируют наблюдение быстрого обмена, ключа или других мелких объектов. Sample выбирает ближайший исходный кадр внутри своей сцены; default допустимое отклонение 1/(2×rate). При слишком большом разрыве image_mask=false и time=null, а отсутствие события не утверждается.

Temporal window имеет 32 позиции при 2 fps; stride=16 позиций, то есть 8 секунд. Полное покрытие grid — 16 секунд; расстояние между первым и последним grid sample — 15,5 секунды. Сохраняется и реальный span выбранных source PTS. end_sec обрезается по сцене; grid_interval_complete отдельно отмечает полноту покрытия. Последнее неполное окно дополняется None с padding_mask=true. image_mask обозначает доступность исходного изображения; known_mask остаётся false до разметки. Это три разных маски. Неполный интервал не доказывает negative.

## Геометрия и происхождение

PNG хранится после необязательного crop в original decoded coordinates и поворота CCW 0/90/180/270. Артефакт содержит video_id, scene_id, split, source SHA, реальное время, dimensions и affine to_original 3×3 для corner coordinates bbox_xyxy. box_to_original проверяет границы и преобразует все четыре угла. Original dimensions сохранены отдельно от dimensions PNG. Raw decoded coordinates и rotated artifact coordinates не смешиваются. Crop остаётся пространственным наблюдением и не заменяет temporal sequence.

Каждый PNG/клип имеет hash и file entry. Ключ включает source/index/scenes hashes, rate, crop/transform, encoder format и runtime versions. Смена source/config не возвращает старый набор. Повторный запуск с тем же ключом проверяет marker/metadata и каждый hash; повреждённый или несовместимый output отклоняется, требуется новый каталог. Существующий output не перезаписывается. Все результаты вне Git.

## Клипы, точность и ресурсы

Клипы перекодируются только из полностью декодированных source frames внутри окна. Stream-copy/keyframe seek не используется. В клипе только video, без audio. FFV1/bgr0 в Matroska сохраняет пиксели выбранного изображения; исходный source PTS каждого кадра остаётся в sidecar mapping. Encoded PTS имеют собственную шкалу и проверяются повторным decode. Matroska квантует выходное время: tolerance=0,0011 с, сохранённые original PTS точные. Requested start/end и first/last decoded source boundary записаны отдельно; это не заявление о кадре в несуществующий requested момент.

Output строится в собственном staging и публикуется только с завершённым artifacts.json. При ошибке staging удаляется внутри проверенного parent; чужие каталоги не очищаются. Ограничены count кадров/клипов, encoded frames, полная decode work, output bytes и свободный диск. AVIO write проверяет byte/free-disk предел до записи; metadata также входит в бюджет. Экспорт каждого клипа сейчас повторно декодирует источник, поэтому max_decode_work_frames ограничивает суммарную работу. Для больших видео выбирать нужные сцены/лимиты осознанно. Сбой и прерванный output не считаются готовыми; при повторе используются только завершённые проверенные артефакты.

D4 не присваивает labels, reviewer реальным данным, training_ready или независимость ракурса. Дальнейшие D5/D проверяют разметку, source groups, права и готовность по реальным материалам.
