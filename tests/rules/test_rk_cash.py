from copy import deepcopy

import pytest

from contracts.python_ports import validate_contract
from rules import rk_cash as rk


def raw(**scores):
    frames = [{'source_pts': n*100, 'timestamp_sec': n*.5, 'state_scores': dict(scores)} for n in range(16)]
    return {'frames': frames}


def test_official_snapshot_has_current_text_exceptions_and_no_network_dependency(tmp_path):
    document = rk.load_source()
    assert document['revision'] == '2026-03-16' and document['number'] == '231'
    assert 'медицинских изделий' in document['sections']['12']
    assert 'окончания обслуживания' in document['sections']['22']
    damaged = tmp_path/'source.json'; damaged.write_bytes(rk.SNAPSHOT.read_bytes()+b' ')
    with pytest.raises(ValueError, match='integrity'): rk.load_source(damaged)


def test_bag_handling_and_unknown_placement_do_not_become_storage():
    assert rk.candidates(raw(bag_interaction=.99)) == []
    assert rk.candidates(raw(bag_interaction=.99, bag_on_desk=None)) == []
    bag = rk.candidates(raw(bag_on_desk=.95))[0]
    assert bag['rule_id'] == 'RK-CASH-012-BAG'
    description = rk.describe(bag, '')
    assert 'инкассаторское' in description and 'медицинские' in description
    assert 'не установлены' in description and 'п.12' in description
    finding = rk.finding(bag, 'scene', description)
    assert finding['status'] == 'unknown' and finding['source']['verified'] is True


@pytest.mark.parametrize('score', [None, .5, float('nan'), True])
def test_unknown_operator_never_becomes_absent(score):
    assert rk.candidates(raw(storage_open=.95, operator_at_station=score, person_at_counter=.9)) == []


def test_safe_requires_continuous_absence_and_real_prior_presence():
    data = raw(storage_open=.95, operator_at_station=.95)
    assert rk.candidates(data) == []
    for f in data['frames'][6:]: f['state_scores']['operator_at_station'] = .05
    candidate = rk.candidates(data)[0]
    assert candidate['start'] == 3. and candidate['end'] == 7.5
    assert candidate['source_pts'] == [f['source_pts'] for f in data['frames'][6:]]
    assert 'не устанавливает универсальный запрет' in rk.describe(candidate, '')
    for f in data['frames']: f['state_scores']['operator_at_station'] = .05
    assert rk.candidates(data) == []


def test_missing_frames_and_short_spikes_cannot_form_continuous_two_second_evidence():
    data = raw(bag_on_desk=.99)
    data['frames'] = data['frames'][::2]
    assert rk.candidates(data) == []
    data = raw(bag_on_desk=.1)
    for f in data['frames'][4:7]: f['state_scores']['bag_on_desk'] = .99
    assert rk.candidates(data) == []


def test_departure_needs_simultaneous_client_not_any_person_seen_elsewhere():
    data = raw(operator_at_station=.95, person_at_counter=.95)
    for f in data['frames'][6:]: f['state_scores']['operator_at_station'] = .05
    candidate = rk.candidates(data)[0]
    assert candidate['rule_id'] == 'RK-CASH-022-DEPARTURE'
    assert 'обслуживание ещё не завершено' in rk.describe(candidate, '')
    for f in data['frames'][6:]: f['state_scores']['person_at_counter'] = None
    assert rk.candidates(data) == []


def test_screen_cup_and_ordinary_cash_handling_are_not_invented_violations():
    assert rk.candidates(raw(laptop_screen_lit=.99, cup_to_mouth=.99, flat_item_handling=.99)) == []
    event = {'action': 'flat_item_handling', 'start': 1., 'end': 3.}
    context = rk.context(event)
    assert context['candidate'] is False
    assert 'не установленное отклонение' in rk.describe(context, 'Работа с плоским предметом.')
    assert rk.context({**event, 'action': 'laptop_screen_lit'}) is None


def test_official_unknown_findings_are_contract_valid_without_fabricating_actor_identity():
    event = rk.candidates(raw(bag_on_desk=.95))[0]
    finding = rk.finding(event, 'scene', rk.describe(event, ''))
    timeline = {'schema_version': '1.0', 'video_id': 'video', 'scene_id': 'scene',
                'preprocessing_version': rk.VERSION, 'model_version': 'experimental',
                'coverage': 'partial', 'observations': [], 'findings': [finding]}
    validate_contract('events', timeline)
    assert finding['actor_id'] is None and finding['support'] == 'supported'
    changed = deepcopy(timeline); changed['findings'][0]['source']['title'] = ''
    with pytest.raises(ValueError): validate_contract('events', changed)
