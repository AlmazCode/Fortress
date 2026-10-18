"""Source-bound action candidates, independent of the frozen clip classifier.

No dataset, labels, filename or source-hash lookup is used here. These are
unreviewed observations, never a causal explanation or a legal finding.
"""
import math


VERSION = 'source-action-review-v2'
MAX_REVIEW_EVENTS = 4
LABELS = {
    'risk_candidate': ('Подозрительный фрагмент по сценарию', 'Модель локализовала фрагмент по слабым сценарным меткам. Причина и нормативная применимость требуют проверки.'),
    'flat_item_handling': ('Работа с купюрой, карточкой или бумагой', 'Модель выделила работу с плоским предметом. Номинал, подлинность и подмена денег не установлены.'),
    'counter_interaction': ('Взаимодействие с настольным устройством', 'Модель выделила контакт с настольным устройством проверки или пересчёта. Результат проверки и сумма не установлены.'),
    'computer_interaction': ('Работа с компьютером', 'Модель выделила взаимодействие с клавиатурой, тачпадом или крышкой. Проведение операции и блокировка ОС не установлены.'),
    'storage_interaction': ('Взаимодействие с сейфом', 'Модель выделила работу у дверцы или внутреннего пространства сейфа. Запирание и содержимое не установлены.'),
    'bag_interaction': ('Перемещение или работа с сумкой', 'Модель выделила манипуляции с сумкой. Содержимое сумки и передача денег не установлены.'),
    'door_interaction': ('Взаимодействие с дверью', 'Модель выделила контакт с дверью прохода. Право доступа не установлено.'),
    'writing': ('Запись на бумаге', 'Модель выделила движение руки при записи. Содержание записи не установлено.'),
    'cup_to_mouth': ('Чашка у лица', 'Модель выделила движение чашки к лицу. Требуется просмотр исходных кадров.'),
    'storage_open': ('Открытая дверца сейфа', 'Модель выделила видимую открытую дверцу. Запирание, сохранность и присутствие ответственного лица не установлены.'),
    'safe_open': ('Открытая дверца сейфа', 'Модель выделила видимую открытую дверцу. Запирание и сохранность не установлены.'),
    'bag_on_desk': ('Сумка на рабочей поверхности', 'Модель выделила сумку на рабочей поверхности. Оставление без присмотра и содержимое не установлены.'),
    'laptop_screen_lit': ('Светящийся экран', 'Модель выделила светящийся экран. Блокировка ОС и доступность данных не установлены.'),
    'garment_on_desk': ('Одежда на рабочей поверхности', 'Модель выделила предмет одежды на рабочей поверхности. Нормативная оценка не установлена.'),
}
ACTIONS = frozenset(('risk_candidate', 'flat_item_handling', 'counter_interaction', 'computer_interaction',
                     'storage_interaction', 'bag_interaction', 'door_interaction', 'writing', 'cup_to_mouth'))


def segments(raw, duration):
    """Validate every candidate against the actual source PTS and frame scores."""
    frames = raw['frames']
    by_pts = {}
    previous = -1.
    for frame in frames:
        timestamp = frame['timestamp_sec']
        point = frame['source_pts']
        if (not math.isfinite(timestamp) or not previous < timestamp < duration
                or not isinstance(point, int) or point in by_pts):
            raise ValueError('Invalid source frame timeline')
        by_pts[point] = frame
        previous = timestamp
    result = []
    seen = set()
    for event in raw.get('candidate_events', []):
        action = event['action']
        points = event['source_pts']
        if not points or len(set(points)) != len(points) or any(p not in by_pts for p in points):
            raise ValueError('Candidate has foreign or duplicate source PTS')
        selected = [by_pts[p] for p in points]
        times = [f['timestamp_sec'] for f in selected]
        scores = [f['state_scores'].get(action) for f in selected]
        if (times != sorted(times) or any(b-a > .75 for a, b in zip(times, times[1:]))
                or event['start_sec'] != times[0] or event['end_sec'] != times[-1]
                or any(s is None or not math.isfinite(s) or not .5 <= s <= 1 for s in scores)):
            raise ValueError('Candidate interval disagrees with model source frames')
        identity = (action, tuple(points))
        if identity in seen:
            continue
        seen.add(identity)
        middle = (max(selected, key=lambda f: f['state_scores'][action]) if action == 'risk_candidate'
                  else min(selected, key=lambda f: abs(f['timestamp_sec']-(times[0]+times[-1])/2)))
        result.append({'action': action, 'start': times[0], 'end': times[-1],
                       'score': sum(scores)/len(scores), 'middle': middle['timestamp_sec'],
                       'frame_count': len(points), 'source_pts': points.copy()})
    return sorted(result, key=lambda s: (s['start'], s['end'], s['action']))


def review_segments(values):
    # Actions are useful review context; static presence alone must not outrank them.
    eligible = [s for s in values if s['action'] in LABELS and (s['frame_count'] >= 2 or s['action'] == 'risk_candidate')]
    risk = [s for s in eligible if s['action'] == 'risk_candidate']
    actions = [s for s in eligible if s['action'] in ACTIONS]
    eligible = risk or actions or eligible
    if len(eligible) <= MAX_REVIEW_EVENTS:
        return eligible
    # Bound JPEG/decode cost, keeping temporal coverage rather than only the start.
    return [eligible[round(n*(len(eligible)-1)/(MAX_REVIEW_EVENTS-1))]
            for n in range(MAX_REVIEW_EVENTS)]


def describe(event, raw, values):
    """Describe simultaneous source observations without inventing a violation.

    Missing/ambiguous operator scores never imply absence. A departure hint
    needs an earlier presence observation and a continuous two-second absence.
    Bag handling alone never implies that the bag was left on the desk.
    """
    label, description = LABELS[event['action']]
    points = set(event['source_pts'])
    frames = [f for f in raw['frames'] if f['source_pts'] in points]

    def stable(name, present):
        scores = [f['state_scores'].get(name) for f in frames]
        valid = [s for s in scores if type(s) in (float, int) and math.isfinite(s) and 0 <= s <= 1]
        return (len(valid) == len(frames) and len(valid) >= 3
                and sum(s >= .8 if present else s <= .2 for s in valid)/len(valid) >= (.8 if present else 1))

    operator_present = stable('operator_at_station', True)
    operator_absent = (event['end']-event['start'] >= 2 and stable('operator_at_station', False))
    earlier_presence = False
    run = []
    for frame in raw['frames']:
        score = frame['state_scores'].get('operator_at_station')
        timestamp = frame['timestamp_sec']
        if (0 < event['start']-timestamp <= 8 and type(score) in (int,float) and .8 <= score <= 1):
            if run and timestamp-run[-1] > .75: run = []
            run.append(timestamp)
            if len(run) >= 3 and run[-1]-run[0] >= 1: earlier_presence = True
        else: run = []
    action = event['action']
    if action in ('storage_open','safe_open','bag_on_desk','laptop_screen_lit'):
        if operator_present:
            description += ' В те же моменты модель видит сотрудника у рабочего места; оставление без присмотра не подтверждено.'
        elif operator_absent and earlier_presence:
            description += ' После ранее видимого сотрудника модель предполагает его отсутствие не менее 2 с. Проверьте оставление рабочего места по кадрам; это гипотеза, а не установленное нарушение.'
        else:
            description += ' Надёжно определить уход сотрудника по этому интервалу не удалось.'
    if action == 'bag_interaction':
        description += (' Одновременно модель предполагает положение сумки на столе.' if stable('bag_on_desk', True)
                        else ' Размещение сумки на столе не подтверждено; манипуляции с сумкой не означают её оставление.')
    companions = []
    for other in values:
        if (other['action'] != action and other['action'] in ACTIONS and other['action'] != 'risk_candidate'
                and other['frame_count'] >= 3
                and min(event['end'],other['end'])-max(event['start'],other['start']) >= 1):
            name = LABELS[other['action']][0].lower()
            if name not in companions: companions.append(name)
    if companions:
        description += ' Пересекающиеся предположения модели: '+', '.join(companions[:2])+'.'
    return label, description


def timeline(job, raw, values):
    scene = job.job_id+':unreviewed'
    return {'schema_version': '1.0', 'video_id': job.job_id, 'scene_id': scene,
            'preprocessing_version': VERSION, 'model_version': raw['model_sha256'],
            'coverage': 'partial', 'findings': [], 'observations': [
                {'class_id': s['action'], 'interval': {'start_sec': s['start'], 'end_sec': s['end'], 'scene_id': scene},
                 'score': s['score'], 'state': 'unreviewed', 'known_mask': False,
                 'visibility': 'unknown', 'actor_id': None, 'relations': []} for s in values]}
