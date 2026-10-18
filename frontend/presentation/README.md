# Материалы для презентации

`synthetic-bank-lobby.png` — искусственный интерьер, созданный встроенным imagegen 18 октября 2026 года. Людей, клиентских данных и реального банковского видео нет. Это иллюстрация интерфейса, не доказательство и не материал для ML-оценки. Изображение не импортируется приложением и не входит в production bundle. Превью рабочих файлов всегда извлекаются из самих выбранных видео.

Сцену можно превратить в два статичных MP4 длительностью 8 и 12 секунд для проверки выбора нескольких файлов, превью и плеера. Нужен установленный FFmpeg; скрипт ничего не скачивает и не заменяет существующие файлы. Укажите каталог вывода вне Git checkout:

```powershell
.\Generate-DemoVideo.ps1 -FfmpegPath 'C:\tools\ffmpeg.exe' -OutputDirectory 'C:\demo\fortress'
```

Откройте `npm run dev:fixture`, введите произвольное тестовое обозначение вместо ключа, выберите созданные MP4 и запустите очередь. События в fixture — независимые искусственные примеры; загруженные видео не анализируются. Реальные демонстрационные записи человеком не предоставлены, поэтому сгенерированная сцена явно обозначена как synthetic.

Способ генерации: встроенный image_gen, без CLI/API-ключа. Финальный prompt:

> Use case: photorealistic-natural. Asset type: fictional, privacy-safe demonstration video still for an internal bank video-analysis UI presentation. Create a single wide 16:9 high-angle fixed security-camera view of an empty contemporary bank customer service lobby: neutral warm grey floor, a few modest waiting chairs, service desks and glass partitions, subtle burgundy upholstery, soft realistic indoor lighting. Restrained, low saturation, plausible ordinary security footage, enough architectural detail to read at thumbnail size. No people, faces, documents, personal data, bank logos, readable signage, clocks, timestamps, overlays, bounding boxes or watermark. This is a synthetic illustrative scene, not real footage or evidence. Avoid vivid test patterns, cinematic drama, luxury advertising styling and bright saturated colors.
