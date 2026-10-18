from backend.local.inference import make_result
from tests.local.test_action_review import Evidence, job, output
from fastapi.testclient import TestClient
from backend.local.app import create_app
from backend.app.schemas import MissingRelease


def test_rule_candidate_has_linked_source_description_original_frames_and_frozen_binary_verdict(tmp_path):
    data = output()
    for f in data['frames']:
        f['state_scores'].update(operator_at_station=.95 if f['timestamp_sec'] < 20 else .05,
                                 person_at_counter=.95)
    evidence = Evidence()
    result = make_result(job(tmp_path), data, evidence, deadline_monotonic=999)
    event = result.public['violations'][0]; finding = result.diagnostics['timeline']['findings'][0]
    assert event['type'] == 'Возможный уход кассира до окончания обслуживания'
    assert event['description'].startswith('['+finding['rule_id']+']')
    assert finding['reason'] in event['description'] and finding['source']['verified']
    assert 'https://adilet.zan.kz/rus/docs/V1900019680' in event['description']
    assert finding['source']['section'] == 'п.22' and finding['status'] == 'unknown'
    assert all(20 <= f['timestamp_sec'] <= 25.5 for f in event['evidence_frames'])
    assert len(event['evidence_frames']) == 3
    assert result.diagnostics['versions']['rules'].startswith('rk-cash-review-v1-')
    data['prediction'] = 'no_violation'; evidence = Evidence()
    result = make_result(job(tmp_path), data, evidence, deadline_monotonic=999)
    assert result.public['verdict'] == 'no_violation' and result.public['violations'] == []
    assert evidence.calls == []


def test_normal_cash_action_has_context_source_without_becoming_a_confirmed_violation(tmp_path):
    result = make_result(job(tmp_path), output(), Evidence(), deadline_monotonic=999)
    event = result.public['violations'][0]; finding = result.diagnostics['timeline']['findings'][0]
    assert event['type'].startswith('Для проверки:')
    assert finding['rule_id'] == 'RK-CASH-019-FLAT'
    assert finding['status'] == 'unknown' and 'не установленное отклонение' in event['description']
    assert finding['source']['title'] and finding['source']['snapshot_sha256']


def test_normative_catalog_requires_api_key_and_serves_pinned_local_text(tmp_path):
    frontend = tmp_path/'ui'; frontend.mkdir(); (frontend/'index.html').write_text('<html>test</html>')
    config = {'runtime_root': str(tmp_path/'runtime'), 'api_key': 'test-key-for-rk-catalog-only'}
    client = TestClient(create_app(config, frontend, release=MissingRelease(), start_worker=False))
    assert client.get('/api/ui/v1/rules').status_code == 401
    response = client.get('/api/ui/v1/rules', headers={'X-API-Key': config['api_key']})
    assert response.status_code == 200 and response.json()['document']['revision'] == '2026-03-16'
    assert response.headers['cache-control'] == 'private, no-store'
