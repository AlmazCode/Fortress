"""Offline RK cash-rule review from source-frame observations.

Verified law text and a verified visual conclusion are different. This adapter
emits conditional review candidates; experimental recognizers never manufacture
confirmed findings, personal ownership, cash contents, or an unfinished service.
The existing binary classifier remains unchanged.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

VERSION = 'rk-cash-review-v1'
SNAPSHOT = Path(__file__).with_name('sources')/'rk/nbrk-231-20260316.json'
SNAPSHOT_SHA256 = '3fab4a3cd0a0f48b66ca50c41e0cac9f92815ec44e30b2279cbf944157c352b6'
RULES = {
    'RK-CASH-012-BAG': ('12', 'Возможное хранение личной сумки в кассовой зоне'),
    'RK-CASH-012-GARMENT': ('12', 'Возможное хранение личной одежды в кассовой зоне'),
    'RK-CASH-020-SAFE': ('20', 'Возможное оставление открытого сейфа без кассира'),
    'RK-CASH-022-DEPARTURE': ('22', 'Возможный уход кассира до окончания обслуживания'),
    'RK-CASH-019-FLAT': ('19', 'Проверка порядка приёма и пересчёта наличности'),
    'RK-CASH-019-DEVICE': ('19', 'Проверка обработки наличности на настольном устройстве'),
}


def load_source(path=None):
    content = (Path(path) if path else SNAPSHOT).read_bytes()
    if hashlib.sha256(content).hexdigest() != SNAPSHOT_SHA256:
        raise ValueError('RK normative snapshot integrity failure')
    value = json.loads(content)
    if value['act_id'] != 'V1900019680' or value['revision'] != '2026-03-16':
        raise ValueError('RK normative snapshot identity failure')
    return value


def source(rule_id):
    document = load_source(); paragraph, _ = RULES[rule_id]
    return {'source_kind': 'official', 'title': 'Правила кассовых операций — НБРК №231 от 29.11.2019',
            'url': document['url'], 'revision': document['revision'],
            'section': 'п.19, подп.2' if paragraph == '19' else 'п.'+paragraph,
            'snapshot_sha256': SNAPSHOT_SHA256, 'verified': True,
            'limitations': ['Текст первоисточника проверен; применимость к конкретному эпизоду требует проверки человеком.',
                            'Модель и распознавание условий остаются экспериментальными.',
                            'Действующая редакция на дату исследования 18.10.2026; дата съёмки и внутренние условия банка неизвестны.']}


def catalog():
    document = load_source()
    return {'version': VERSION, 'snapshot_sha256': SNAPSHOT_SHA256, 'document': document,
            'rules': [{'id': key, 'title': title, 'section': paragraph,
                       'mode': 'review_candidate' if paragraph != '19' else 'context_only'}
                      for key, (paragraph, title) in RULES.items()],
            'unsupported': ['Блокировка ОС по светящемуся экрану', 'Запрет питья по наличию чашки',
                            'Подлинность/номинал/подмена купюр', 'Проводки и сверки в банковской системе',
                            'Права доступа или личности по внешности', 'Нарушение только по факту открытия сейфа']}


def score(frame, name, present=True):
    value = frame['state_scores'].get(name)
    return (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
            and (value >= .8 if present else value <= .2))


def runs(frames, predicate, seconds=2.):
    run = []
    for frame in frames:
        if run and frame['timestamp_sec']-run[-1]['timestamp_sec'] > .75:
            if run[-1]['timestamp_sec']-run[0]['timestamp_sec'] >= seconds: yield run
            run = []
        if predicate(frame):
            run.append(frame)
        else:
            if run and run[-1]['timestamp_sec']-run[0]['timestamp_sec'] >= seconds: yield run
            run = []
    if run and run[-1]['timestamp_sec']-run[0]['timestamp_sec'] >= seconds: yield run


def earlier_presence(frames, start):
    before = [f for f in frames if 0 < start-f['timestamp_sec'] <= 8]
    return any(runs(before, lambda f: score(f, 'operator_at_station'), seconds=1.))


def candidates(raw):
    frames = raw['frames']; result = []

    def append(rule, run, observed, limitation):
        middle = run[len(run)//2]
        result.append({'rule_id': rule, 'type': RULES[rule][1], 'start': run[0]['timestamp_sec'],
                       'end': run[-1]['timestamp_sec'], 'middle': middle['timestamp_sec'],
                       'source_pts': [f['source_pts'] for f in run], 'observed': observed,
                       'limitation': limitation, 'candidate': True})

    for name, rule, noun in [('bag_on_desk', 'RK-CASH-012-BAG', 'сумку'),
                             ('garment_on_desk', 'RK-CASH-012-GARMENT', 'предмет одежды')]:
        for run in runs(frames, lambda f: score(f, name)):
            append(rule, run, f'Модель предполагает {noun} на рабочей поверхности не менее 2 с.',
                   'Личная принадлежность и назначение предмета не установлены. '
                   'Для сумки исключите инкассаторское назначение и медицинские принадлежности; '
                   'для одежды — рабочую одежду. Само перемещение предмета не означает хранение.')

    def open_safe(frame):
        return (score(frame, 'storage_open') or score(frame, 'safe_open')) and score(frame, 'operator_at_station', False)

    for run in runs(frames, open_safe):
        if earlier_presence(frames, run[0]['timestamp_sec']):
            append('RK-CASH-020-SAFE', run,
                   'После ранее распознанного присутствия кассира модель одновременно предполагает открытую дверцу сейфа и отсутствие кассира не менее 2 с.',
                   'Пункт20 относится к хранению ранее принятой наличности и не устанавливает универсальный запрет открывать сейф. Содержимое сейфа, стадия операции, '
                   'запирание и наличие другого ответственного работника не установлены. Открытие сейфа при работе кассира не является основанием срабатывания.')
    for run in runs(frames, lambda f: score(f, 'operator_at_station', False) and score(f, 'person_at_counter')):
        if earlier_presence(frames, run[0]['timestamp_sec']):
            append('RK-CASH-022-DEPARTURE', run,
                   'После ранее распознанного присутствия кассира модель предполагает его отсутствие не менее 2 с; человек у стойки остаётся в те же моменты.',
                   'Необходимо подтвердить, что это обслуживаемый клиент и обслуживание ещё не завершено. '
                   'Замещение другим кассиром, выход за область видимости и ошибки распознавания не исключены.')
    return sorted(result, key=lambda e: (e['start'], e['end'], e['rule_id']))


def context(event):
    """An ordinary action gets a relevant source, never a violation inference."""
    rule = {'flat_item_handling': 'RK-CASH-019-FLAT', 'counter_interaction': 'RK-CASH-019-DEVICE',
            'bag_interaction': 'RK-CASH-012-BAG', 'bag_on_desk': 'RK-CASH-012-BAG',
            'garment_on_desk': 'RK-CASH-012-GARMENT',
            'storage_interaction': 'RK-CASH-020-SAFE', 'storage_open': 'RK-CASH-020-SAFE',
            'safe_open': 'RK-CASH-020-SAFE'}.get(event['action'])
    if not rule: return None
    return {**event, 'rule_id': rule, 'candidate': False}


def describe(event, observation):
    reference = source(event['rule_id']); paragraph = RULES[event['rule_id']][0]
    norm = {'12': 'Личные вещи работников хранятся вне кассового узла; предусмотрены исключения для лекарств, медицинских изделий и отдельных средств связи.',
            '19': 'При приёме банкнот предусмотрены полистный пересчёт и проверка подлинности и платёжности.',
            '20': 'Ранее принятая наличность хранится в специальных устройствах, закрывающихся на ключ.',
            '22': 'Кассовому работнику не допускается покидать рабочее место до окончания обслуживания клиента.'}[paragraph]
    observation = event['observed'] if event['candidate'] else observation
    qualification = event['limitation'] if event['candidate'] else (
        'Это наблюдение действия, а не установленное отклонение от нормы. '
        'Содержание предметов, завершение операции, личная принадлежность и выполнение невидимых проверок не установлены.')
    return (f"[{event['rule_id']}] Интервал {event['start']:.1f}–{event['end']:.1f} с. {observation} "
            f"Почему нужна проверка: {norm} {qualification} "
            f"Источник: {reference['title']}, {reference['section']}, редакция {reference['revision']}. {reference['url']} "
            'Результат — подсказка для проверки человеком, не установленное нарушение.')


def finding(event, scene, reason):
    return {'rule_id': event['rule_id'], 'status': 'unknown',
            'interval': {'start_sec': event['start'], 'end_sec': event['end'], 'scene_id': scene},
            'actor_id': None, 'reason': reason, 'support': 'supported', 'observability': 'partial',
            'source': source(event['rule_id'])}
