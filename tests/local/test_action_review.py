"""Regress arbitrary review anchors without importing a dataset or model weights."""
from dataclasses import replace
from datetime import datetime, timezone
import io

from PIL import Image
import pytest

from contracts.python_ports import AcceptedUpload, JobRecord, VideoInfo
from backend.app.media import SourceFrame
from backend.local.events import review_segments
from backend.local.inference import make_result
from backend.app.tasks import AnalysisFailure


def output():
    frames = [{'source_pts': n*50, 'timestamp_sec': n*.5,
               'state_scores': {'flat_item_handling': .9 if n >= 40 else .1,
                                'bag_interaction': .999 if n == 3 else .1}}
              for n in range(52)]
    return {'source_sha256': 'a'*64, 'normative_status': 'unknown', 'frames': frames,
            'candidate_events': [{'action': 'flat_item_handling', 'source_pts': [f['source_pts'] for f in frames[40:]],
                                  'start_sec': 20., 'end_sec': 25.5}],
            'prediction': 'violation', 'score': .9, 'threshold': .3, 'model_sha256': 'b'*64}


def job(tmp_path):
    now = datetime.now(timezone.utc)
    upload = AcceptedUpload(tmp_path/'source.video', 'a'*64, 100, VideoInfo(26,64,64,2,0,0,1,100,False))
    return JobRecord('00000000-0000-4000-8000-000000000001','running',now,now,upload)


class Evidence:
    def __init__(self):
        self.calls = []

    def frames(self, path, timestamps, **kwargs):
        self.calls.append(timestamps)
        stream = io.BytesIO()
        Image.new('RGB', (64,64)).save(stream, 'JPEG')
        return [SourceFrame(n,round(t*100),0,1,100,stream.getvalue()) for n,t in enumerate(timestamps)]


def test_review_uses_action_interval_and_three_source_frames_not_unrelated_maximum(tmp_path):
    evidence = Evidence()
    result = make_result(job(tmp_path),output(),evidence,deadline_monotonic=999)
    event = result.public['violations'][0]
    assert evidence.calls == [[22.5,20.,25.5]]
    assert event['timecode_sec'] == 22.5
    assert len(event['evidence_frames']) == 3
    assert '20.0–25.5' in event['description'] and 'подмена денег не установлены' in event['description']
    assert '1.5' not in event['description']
    observation = result.diagnostics['timeline']['observations'][0]
    assert observation['class_id'] == 'flat_item_handling'
    assert observation['known_mask'] is False and observation['state'] == 'unreviewed'
    assert all(f['status'] == 'unknown' for f in result.diagnostics['timeline']['findings'])
    assert result.diagnostics['timeline']['findings'][0]['source']['verified'] is True


@pytest.mark.parametrize('corruption', ['source','pts','bounds','score'])
def test_foreign_source_or_fabricated_intervals_fail_before_evidence(tmp_path,corruption):
    raw = output()
    if corruption == 'source': raw['source_sha256'] = 'c'*64
    if corruption == 'pts': raw['candidate_events'][0]['source_pts'][0] = 9999
    if corruption == 'bounds': raw['candidate_events'][0]['start_sec'] = 1.5
    if corruption == 'score': raw['frames'][40]['state_scores']['flat_item_handling'] = None
    evidence = Evidence()
    with pytest.raises(ValueError):make_result(job(tmp_path),raw,evidence,deadline_monotonic=999)
    assert not evidence.calls


def test_negative_clip_retains_action_observations_without_false_alerts(tmp_path):
    raw = output();raw['prediction'] = 'no_violation'
    evidence = Evidence()
    result = make_result(job(tmp_path),raw,evidence,deadline_monotonic=999)
    assert result.public['violations'] == [] and not evidence.calls
    assert result.diagnostics['timeline']['observations']


@pytest.mark.parametrize('action', ['storage_open', 'bag_on_desk', 'laptop_screen_lit'])
def test_object_with_operator_present_is_not_described_as_unattended(tmp_path, action):
    raw = output()
    raw['candidate_events'][0]['action'] = action
    for frame in raw['frames']:
        frame['state_scores'].update({action: .9, 'operator_at_station': .95})
    result = make_result(job(tmp_path),raw,Evidence(),deadline_monotonic=999)
    text = result.public['violations'][0]['description']
    if action == 'bag_on_desk':
        assert 'Личная принадлежность и назначение предмета не установлены' in text
        assert result.public['violations'][0]['type'] == 'Возможное хранение личной сумки в кассовой зоне'
    else:
        assert 'видит сотрудника' in text and 'оставление без присмотра не подтверждено' in text
    assert 'предполагает его отсутствие' not in text
    assert all(f['status'] == 'unknown' for f in result.diagnostics['timeline']['findings'])


@pytest.mark.parametrize('operator', [None, .5, float('nan')])
def test_missing_or_ambiguous_operator_never_becomes_a_departure(tmp_path, operator):
    raw = output(); raw['candidate_events'][0]['action'] = 'storage_open'
    for frame in raw['frames']:
        frame['state_scores'].update(storage_open=.9,operator_at_station=operator)
    result = make_result(job(tmp_path),raw,Evidence(),deadline_monotonic=999)
    text = result.public['violations'][0]['description']
    assert 'определить уход сотрудника' in text and 'предполагает его отсутствие' not in text


def test_departure_hint_requires_prior_presence_and_retains_unknown_normative_status(tmp_path):
    raw=output(); raw['candidate_events'][0]['action']='storage_open'
    for frame in raw['frames']:
        frame['state_scores'].update(storage_open=.9,operator_at_station=.95 if frame['timestamp_sec']<20 else .05)
    result=make_result(job(tmp_path),raw,Evidence(),deadline_monotonic=999)
    text=result.public['violations'][0]['description']
    assert 'отсутствие кассира не менее 2 с' in text and 'не установленное нарушение' in text
    assert result.diagnostics['timeline']['findings'][0]['status']=='unknown'
    for frame in raw['frames']: frame['state_scores']['operator_at_station']=.05
    result=make_result(job(tmp_path),raw,Evidence(),deadline_monotonic=999)
    assert 'предполагает его отсутствие' not in result.public['violations'][0]['description']
    assert not any(e['type'].startswith('Возможное оставление') for e in result.public['violations'])


def test_bag_handling_does_not_imply_placement_or_abandonment(tmp_path):
    raw=output(); raw['candidate_events'][0]['action']='bag_interaction'
    for frame in raw['frames']:frame['state_scores'].update(bag_interaction=.9,bag_on_desk=.1)
    result=make_result(job(tmp_path),raw,Evidence(),deadline_monotonic=999)
    assert 'манипуляции с сумкой не означают её оставление' in result.public['violations'][0]['description']


def test_intermittent_presence_or_one_prior_spike_does_not_prove_continuous_departure(tmp_path):
    raw=output();raw['candidate_events'][0]['action']='storage_open'
    for frame in raw['frames']:
        frame['state_scores'].update(storage_open=.9,operator_at_station=.95 if frame['timestamp_sec']<20 else .05)
    raw['frames'][46]['state_scores']['operator_at_station']=.95
    result=make_result(job(tmp_path),raw,Evidence(),deadline_monotonic=999)
    assert all(not (f['interval']['start_sec'] <= 23 <= f['interval']['end_sec'])
               for f in result.diagnostics['timeline']['findings'] if f['rule_id']=='RK-CASH-020-SAFE')
    for frame in raw['frames']:frame['state_scores']['operator_at_station']=.05
    raw['frames'][39]['state_scores']['operator_at_station']=.95
    result=make_result(job(tmp_path),raw,Evidence(),deadline_monotonic=999)
    assert 'предполагает его отсутствие' not in result.public['violations'][0]['description']


def test_evidence_outside_event_is_rejected(tmp_path):
    evidence = Evidence()
    original = evidence.frames
    def wrong(*args, **kwargs):
        return [replace(f,source_pts=150) for f in original(*args,**kwargs)]
    evidence.frames = wrong
    with pytest.raises(ValueError,match='outside'):
        make_result(job(tmp_path),output(),evidence,deadline_monotonic=999)


def test_review_card_limit_preserves_late_events_and_does_not_promote_static_presence():
    values = [{'action':'flat_item_handling','frame_count':3,'start':n} for n in range(12)]
    values.insert(0,{'action':'laptop_screen_lit','frame_count':100,'start':0})
    selected = review_segments(values)
    assert len(selected) == 4 and selected[-1]['start'] == 11
    assert all(s['action'] == 'flat_item_handling' for s in selected)


def test_positive_without_localization_fails_explicitly_instead_of_inventing_a_timestamp(tmp_path):
    raw = output();raw['candidate_events'] = []
    evidence = Evidence()
    with pytest.raises(AnalysisFailure) as caught:
        make_result(job(tmp_path),raw,evidence,deadline_monotonic=999)
    assert caught.value.reason == 'insufficient_evidence' and not evidence.calls


def test_accepted_risk_head_uses_its_own_peak_and_keeps_weak_semantics(tmp_path):
    raw=output()
    for frame in raw['frames']:
        frame['state_scores']['risk_candidate']=.7 if frame['timestamp_sec']>=20 else .1
    raw['frames'][49]['state_scores']['risk_candidate']=.95
    raw['candidate_events'].append({**raw['candidate_events'][0],'action':'risk_candidate'})
    evidence=Evidence()
    result=make_result(job(tmp_path),raw,evidence,deadline_monotonic=999)
    assert evidence.calls==[[24.5,20.,25.5]]
    event=result.public['violations'][0]
    assert event['timecode_sec']==24.5 and 'слабым сценарным' in event['description']
    assert result.diagnostics['timeline']['findings']==[]


def test_real_child_can_report_insufficient_evidence_without_losing_the_reason(tmp_path,monkeypatch):
    import subprocess
    import sys
    import threading
    import time
    from backend.local import runtime
    popen = subprocess.Popen
    def report(arguments, **kwargs):
        return popen([sys.executable,'-c', 'import json; print(json.dumps({"failure_reason":"insufficient_evidence"}))'],**kwargs)
    monkeypatch.setattr(runtime.subprocess,'Popen',report)
    config = {'runtime_root':str(tmp_path/'runtime'),'bundle_root':str(tmp_path/'unused'),'device':'cpu'}
    with pytest.raises(AnalysisFailure) as caught:
        runtime.ProcessRunner(config,threading.Event()).analyze(job(tmp_path),deadline_monotonic=time.monotonic()+10)
    assert caught.value.reason == 'insufficient_evidence'
    assert not list((tmp_path/'runtime'/'requests').glob('*.json'))
