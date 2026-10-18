# Доступ для жюри

## Локальная карточка подключения

Установщик создаёт `%LOCALAPPDATA%\Fortress\jury-access.json`:

```json
{
  "web_interface_url": "http://127.0.0.1:8000/",
  "api_base_url": "http://127.0.0.1:8000/api/v1",
  "api_key": "<случайный ключ из приватного файла>"
}
```

Настоящий ключ отсутствует в Git и frontend build. Введите его в настройках интерфейса; он живёт в памяти вкладки. Ключ общий для оператора/жюри и даёт доступ к загруженным заданиям/медиа: передавайте его только предполагаемым получателям.

## Запросы

```powershell
$access = Get-Content "$env:LOCALAPPDATA\Fortress\jury-access.json" -Raw | ConvertFrom-Json
$headers = @{ 'X-API-Key' = $access.api_key }
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/ui/v1/model' -Headers $headers
$video = 'D:\Videos\example.mov'
$accepted = curl.exe -sS -X POST 'http://127.0.0.1:8000/api/v1/analyze' -H "X-API-Key: $($access.api_key)" -F "file=@$video" | ConvertFrom-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/jobs/$($accepted.job_id)" -Headers $headers
```

POST возвращает 202 с job_id. Polling GET: processing → done или failed. Done сохраняет требуемые поля verdict/violations; evidence_frames содержит настоящий JPEG в base64. Параллельный незавершённый job вызывает429. Неверный/отсутствующий ключ вызывает401. OpenAPI: [contracts/openapi.yaml](../contracts/openapi.yaml).

UI diagnostics отделены от схемы жюри. В них явно указаны experimental model, partial coverage, неизвестные тип/границы/нормативная применимость. Не считайте общий сигнал классификатора в prototype подтверждённым юридическим типом нарушения. Этот прототип ещё не выполняет все качественные требования приложенного кейса.

## Публичная сдача

127.0.0.1 работает только на ПК сервиса. Для удалённого жюри необходимо предоставить публичный HTTPS origin, настроить DNS/маршрут к этому ПК, TLS reverse proxy и проверить доступ из внешней сети. Сам анализ должен оставаться на локальном ПК. Домен и внешний маршрут пока не заданы; публичные URL не выдумываются и внешний доступ не заявляется.

Перед внешней сдачей проверьте: реальный MOV → done менее5минут, авторизацию и protected media, внешний TLS, восстановление, несколько роликов, качество типов/таймкодов/нормативных источников. Сервис и модель сейчас имеют статус локального прототипа; 80%+ и полное соответствие кейсу не подтверждены.
