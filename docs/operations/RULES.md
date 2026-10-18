# Правила: техническая логика и границы доказуемости

Актуальный Windows-сервис использует отдельный [RK review-адаптер](RK_RULES.md) с проверенным официальным текстом НБРК №231. Он формирует условные кандидаты и нормативный контекст, сохраняя неизвестную применимость. Описанный ниже строгий engine C01–C15 и его прежние отрицательные результаты сохранены; источники/гарантии старого engine не подменяются новым адаптером.

Контракт K `2e44bf555ad1a824d92e73770a1ee85d1bf20d0f` интегрирован в отдельную ветку №4. Его 55 schema/fixture tests прошли в изолированном Python 3.11.17 с `uv sync --locked --group test`. Это собственная проверка точного опубликованного commit, не человеческий approval и не тест работающего приложения.

## Использование

```python
from rules.engine import RuleEngine

engine = RuleEngine(job_id=job_id)
findings = engine.evaluate(action_timeline)  # K events JSON, no extra public fields
technical_diagnostics = engine.diagnostics()
```

Один engine/memory принадлежит одному job/video. `evaluate` валидирует events offline через K, сохраняет последовательные overlapping windows, сортирует поздние события в той же сцене и проверяет сериализацию findings тем же контрактом. Результат не содержит JPEG или новых полей публичной jury schema. Служебные diagnostics должны попадать только в защищённую часть API.

## Память

`SessionMemory(job_id, video_id)` не разделяется между заданиями. Повторные observations дедуплицируются по полному содержимому; для ролика сохраняется история всех сцен. При смене сцены текущие связи/партии разделяются, незакрытые этапы не помечаются завершёнными. Поздний пакет уже закрытой сцены не оживляет старых actor/party links.

Никакой score не превращается в actor ID. Неизвестные ссылки остаются nullable/unknown. Внутренние технические маркеры `service_start/service_end`, `party_opened/party_stored/party_cleared` используют только явно переданные known relations; они не являются заявленными ML-классами и не добавлены в draft taxonomy. Без проверенного upstream adapter они не означают готового распознавания сессий. Наблюдение occluded/unknown никогда не закрывает unresolved state.

## Пять шаблонов

`evaluate_template(template, RuleInputs(...))` — чистая трёхзначная логика для явных внутренних evidence inputs. `condition` означает prerequisite, resolution, previous-party resolution, forbidden presence или response соответственно. Missing event не устанавливает condition=false. Recognizer/relations/exception неизвестны по умолчанию.

| Шаблон | Условие срабатывания при известных предпосылках |
| --- | --- |
| prerequisite | Действие наблюдается, обязательная предпосылка подтверждённо не выполнена |
| unresolved-state | Состояние открыто, до подтверждённого конца этапа не разрешено |
| cross-session | Связанные партии/сессии известны; необходимое разрешение предыдущего состояния отсутствует |
| presence | Наблюдается запрещённое применимой нормой присутствие |
| response | Наблюдается триггер, обязательная реакция подтверждённо отсутствует |

Для любого absence-trigger и каждого `not_triggered` нужны полный существенный интервал, полная видимость, проверенный recognizer, известный конец этапа, проверенные альтернативы и relations. Подтверждённое исключение снимает trigger только при достаточной наблюдаемости; неизвестное исключение даёт unknown. Для прямого положительного presence полный ролик не обязателен, если сам факт и применимость подтверждены; occlusion и отсутствие recognizer всё равно дают unknown.

Эти metadata передаются внутренним `RuleInputs`, привязанным к точному video/scene/interval. K events не содержит достаточных флагов для самостоятельного вывода об отсутствии действия; engine их не выдумывает из coverage или score. При переходе сцены или несоответствии интервала metadata не используются. Ни один текущий production-маршрут не получает trigger: все источники пока unverified/unsupported.

## Проверки и ограничения

```sh
python -m pytest tests/contracts/test_schemas.py tests/rules tests/performance/test_preflight_report.py -q
```

Тесты используют явные synthetic observations/evidence: positive, hard-negative, truncated interval, occlusion, exception, unknown actor/link/recognizer; cross-session, unresolved party, поздние события, scene reset и разные jobs. Они подтверждают код и честный unknown, не реальную видимость, ML precision/recall или нормативную применимость.

Для активации production rules нужны материалы из SOURCES.md, проверенный producer для evidence flags и реальные observation/recognizer данные. Сейчас все C01–C15 `unsupported/legal unknown`; полная неинформативность должна обрабатываться pipeline как `failed/insufficient_evidence`, а не `done/no_violation`. Поддержанная частичная coverage остаётся явно описанной в diagnostics.
