"""Executable boundary checks for K; all media and labels here are synthetic."""
import base64
import copy
import importlib
import io
import json
from pathlib import Path
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / 'contracts'
SCHEMAS = ['job', 'diagnostics', 'events', 'manifest', 'annotations', 'release', 'objects', 'dataset_readiness']


def read(name):
    path = CONTRACTS / name
    assert path.is_file(), f'Required contract is missing: {name}'
    return json.loads(path.read_text())


def validate(schema, payload):
    assert (CONTRACTS / 'python_ports.py').exists(), 'Shared validation port is missing'
    return importlib.import_module('contracts.python_ports').validate_contract(schema, payload)


def example(name):
    return copy.deepcopy(next(c['payload'] for c in read('fixtures.json')['cases'] if c['name'] == name))


@pytest.mark.parametrize('name', SCHEMAS)
def test_schemas_are_valid_and_resolve_offline(name):
    from jsonschema import Draft202012Validator
    schema = read(name + '.schema.json')
    Draft202012Validator.check_schema(schema)
    assert schema['$schema'] == 'https://json-schema.org/draft/2020-12/schema'


def test_all_contract_examples_are_test_only_and_valid():
    fixtures = read('fixtures.json')
    assert fixtures['test_only'] is True
    assert fixtures['provenance']['kind'] == 'synthetic'
    names = {c['name'] for c in fixtures['cases']}
    assert {'processing', 'no_violation', 'violation', 'failed', 'insufficient_evidence', 'model_not_ready', 'unknown', 'objects', 'manifest', 'annotations', 'release', 'dataset_readiness'} <= names
    for case in fixtures['cases']:
        validate(case['schema'], case['payload'])


@pytest.mark.parametrize('status', ['queued', 'running', 'unknown'])
def test_internal_states_are_not_public(status):
    payload = example('processing')
    payload['status'] = status
    with pytest.raises(ValueError):
        validate('job', payload)


@pytest.mark.parametrize('name', ['processing', 'failed', 'no_violation', 'violation'])
def test_public_response_rejects_ui_fields(name):
    payload = example(name)
    payload['stage'] = 'inference'
    with pytest.raises(ValueError):
        validate('job', payload)


@pytest.mark.parametrize('name,verdict', [('violation', 'no_violation'), ('no_violation', 'violation')])
def test_verdict_and_findings_cannot_disagree(name, verdict):
    payload = example(name)
    payload['verdict'] = verdict
    with pytest.raises(ValueError):
        validate('job', payload)


@pytest.mark.parametrize('count', [0, 4])
def test_evidence_requires_one_to_three_frames(count):
    payload = example('violation')
    frame = payload['violations'][0]['evidence_frames'][0]
    payload['violations'][0]['evidence_frames'] = [frame] * count
    with pytest.raises(ValueError):
        validate('job', payload)


@pytest.mark.parametrize('encoded', ['data:image/jpeg;base64,/9j/', 'not-base64', base64.b64encode(b'not a JPEG').decode()])
def test_fake_jpeg_and_data_prefix_are_rejected(encoded):
    payload = example('violation')
    payload['violations'][0]['evidence_frames'][0]['image_base64'] = encoded
    with pytest.raises(ValueError):
        validate('job', payload)


def test_fixture_contains_decodable_jpeg():
    from PIL import Image
    frame = example('violation')['violations'][0]['evidence_frames'][0]
    with Image.open(io.BytesIO(base64.b64decode(frame['image_base64'], validate=True))) as im:
        assert im.format == 'JPEG'
        im.verify()


@pytest.mark.parametrize('missing_bytes', [2, 12])
def test_truncated_jpeg_is_rejected_even_with_a_valid_header(missing_bytes):
    payload = example('violation')
    frame = payload['violations'][0]['evidence_frames'][0]
    encoded = base64.b64decode(frame['image_base64'], validate=True)
    frame['image_base64'] = base64.b64encode(encoded[:-missing_bytes]).decode()
    with pytest.raises(ValueError):
        validate('job', payload)


def test_no_model_is_pre_acceptance_503_and_zero_coverage_is_failed():
    error = example('model_not_ready')
    assert error == {'error': {'code': 'model_not_ready', 'message': 'Import a validated trained release.', 'status': 503}}
    failed = example('insufficient_evidence')
    assert failed['status'] == 'failed' and failed['reason'] == 'insufficient_evidence'
    assert 'verdict' not in failed


def test_unknown_is_explicit_and_cannot_masquerade_as_absence():
    timeline = example('unknown')
    obs = timeline['observations'][0]
    assert obs['state'] == 'unknown' and obs['known_mask'] is False and obs['actor_id'] is None
    obs['known_mask'] = True
    with pytest.raises(ValueError):
        validate('events', timeline)


def test_unverified_rule_cannot_trigger():
    timeline = example('unknown')
    timeline['findings'][0]['status'] = 'triggered'
    with pytest.raises(ValueError):
        validate('events', timeline)


def test_reversed_interval_is_rejected():
    timeline = example('unknown')
    timeline['observations'][0]['interval']['end_sec'] = -1
    with pytest.raises(ValueError):
        validate('events', timeline)
    timeline['observations'][0]['interval'].update(start_sec=2, end_sec=1)
    with pytest.raises(ValueError):
        validate('events', timeline)


def test_source_pts_mapping_is_checked():
    payload = example('objects')
    payload['frames'][0]['time']['timestamp_sec'] += 1
    with pytest.raises(ValueError):
        validate('objects', payload)


def test_object_bbox_must_be_inside_source_frame():
    payload = example('objects')
    payload['frames'][0]['objects'][0]['bbox'] = [15, 0, 2, 5]
    with pytest.raises(ValueError):
        validate('objects', payload)


def test_reviewed_objects_need_reviewer():
    payload = example('objects')
    obj = payload['frames'][0]['objects'][0]
    obj.update(review_status='reviewed', reviewer=None)
    with pytest.raises(ValueError):
        validate('objects', payload)


@pytest.mark.parametrize('identity', ['canonical_id', 'group_id'])
def test_split_rejects_leakage(identity):
    payload = example('manifest')
    second = copy.deepcopy(payload['videos'][0])
    second.update(video_id='test-video-2', canonical_id='test-video-2', group_id='test-scene-2', split='dev_validation')
    second[identity] = payload['videos'][0][identity]
    payload['videos'].append(second)
    with pytest.raises(ValueError):
        validate('manifest', payload)


@pytest.mark.parametrize('path', ['../outside.mp4', '/absolute.mp4', 'C:\\secret.mp4', 'https://example.com/video.mp4'])
def test_manifest_paths_are_local_relative(path):
    payload = example('manifest')
    payload['videos'][0]['path'] = path
    with pytest.raises(ValueError):
        validate('manifest', payload)


def test_release_without_trained_final_taxonomy_is_not_production():
    payload = example('release')
    payload['intended_use'] = 'production'
    with pytest.raises(ValueError):
        validate('release', payload)


def test_release_compatibility_and_hash_fields_required():
    payload = example('release')
    for field in ['checkpoint', 'backbone', 'feature_dim', 'taxonomy', 'preprocessing', 'thresholds', 'metrics', 'model_card', 'versions', 'files']:
        changed = copy.deepcopy(payload)
        del changed[field]
        with pytest.raises(ValueError):
            validate('release', changed)
    payload['files'][0]['sha256'] = 'not-a-hash'
    with pytest.raises(ValueError):
        validate('release', payload)


def test_dataset_readiness_cannot_hide_failed_checks():
    payload = example('dataset_readiness')
    payload['state'] = 'ready'
    with pytest.raises(ValueError):
        validate('dataset_readiness', payload)


def test_baseline_is_single_view_and_taxonomy_is_honest():
    with (ROOT / 'config.example.toml').open('rb') as f:
        config = tomllib.load(f)
    assert config['model']['feature_dim'] == 576
    assert config['model']['gru_hidden_size'] == 256 and config['model']['gru_layers'] == 1
    assert config['preprocessing'] == {'version': 'letterbox-v1', 'size': 224, 'fps': 2, 'window_frames': 32, 'overlap': 0.5, 'views': 1, 'resize': 'letterbox', 'mean': [0.485, 0.456, 0.406], 'std': [0.229, 0.224, 0.225]}
    taxonomy = read('taxonomy.draft.json')
    assert taxonomy['status'] == 'draft' and taxonomy['actions'] == []
    assert taxonomy['production_ready'] is False


def test_openapi_separates_public_ui_auth_and_errors():
    import yaml
    doc = yaml.safe_load((CONTRACTS / 'openapi.yaml').read_text())
    assert doc['openapi'].startswith('3.1.')
    assert doc['components']['securitySchemes']['ApiKey'] == {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'}
    for path, item in doc['paths'].items():
        assert path.startswith('/api/')
        for method, operation in item.items():
            if method in ['get', 'post']:
                assert operation.get('security', doc.get('security')) == [{'ApiKey': []}]
                assert '401' in operation['responses']
    post = doc['paths']['/api/v1/analyze']['post']
    form = post['requestBody']['content']['multipart/form-data']['schema']
    assert form['required'] == ['file']
    assert {'202', '400', '401', '413', '415', '429', '503'} <= set(post['responses'])
    for path in ['/api/ui/v1/jobs/{job_id}', '/api/ui/v1/model', '/api/ui/v1/jobs/{job_id}/media', '/api/ui/v1/jobs/{job_id}/preview', '/api/ui/v1/jobs/{job_id}/frames/{frame_id}']:
        assert path in doc['paths']


def test_all_36_scopes_and_exact_dependencies_are_recorded():
    text = (CONTRACTS / 'OWNERSHIP.md').read_text()
    ownership = json.loads(text.split('```json\n', 1)[1].split('```', 1)[0])
    assert len(ownership) == 36
    assert {v['owner'] for v in ownership.values()} == {1, 2, 3, 4}
    assert 'pyproject.toml' in ownership['K']['files']
    deps = (CONTRACTS / 'DEPENDENCIES.md').read_text()
    graph = json.loads(deps.split('```json\n', 1)[1].split('```', 1)[0])
    assert len(graph) == 36 and graph['K']['depends'] == [] and graph['O1']['depends'] == []
    assert {k for k,v in graph.items() if v['helperFor']} == {'U', 'E', 'B'}
    for key, value in graph.items():
        assert set(value['depends']) <= graph.keys()
        assert key not in value['depends']
    for path in ownership['K']['files']:
        assert (ROOT / path).is_file(), f'Missing K deliverable: {path}'


def test_unverified_rule_cannot_claim_a_negative():
    payload = example('unknown')
    finding = payload['findings'][0]
    finding.update(status='not_triggered', support='supported', observability='full')
    with pytest.raises(ValueError):
        validate('events', payload)


@pytest.mark.parametrize('visibility', ['partial', 'occluded', 'unknown'])
def test_absence_requires_visible_conditions(visibility):
    payload = example('unknown')
    payload['observations'][0].update(state='absent_verified', known_mask=True, visibility=visibility)
    with pytest.raises(ValueError):
        validate('events', payload)


def test_known_relation_requires_both_endpoints():
    payload = example('unknown')
    payload['observations'][0]['relations'] = [
        {'kind': 'same_party', 'subject_id': None, 'object_id': None, 'known': True}
    ]
    with pytest.raises(ValueError):
        validate('events', payload)


@pytest.mark.parametrize('role', ['config', 'preprocessing', 'checkpoint'])
def test_release_manifest_cannot_omit_artifact_roles(role):
    payload = example('release')
    for item in payload['files']:
        if item['role'] == role:
            item['role'] = 'rules'
    with pytest.raises(ValueError):
        validate('release', payload)


def test_diagnostics_never_hide_zero_coverage_as_success():
    payload = example('ui_diagnostics')
    payload.update(public=example('no_violation'), stage='done')
    with pytest.raises(ValueError):
        validate('diagnostics', payload)


def test_openapi_is_valid_and_examples_resolve_without_network():
    from openapi_spec_validator import validate as validate_openapi
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    import yaml
    doc = yaml.safe_load((CONTRACTS / 'openapi.yaml').read_text())
    validate_openapi(doc)
    uri = 'urn:fortress:openapi'
    resource = Resource.from_contents({'$schema': 'https://json-schema.org/draft/2020-12/schema', **doc})
    registry = Registry().with_resource(uri, resource)
    names = {'job': 'Job', 'diagnostics': 'Diagnostics', 'events': 'Events', 'manifest': 'Manifest',
             'annotations': 'Annotations', 'objects': 'Objects', 'release': 'Release',
             'dataset_readiness': 'DatasetReadiness'}
    for case in read('fixtures.json')['cases']:
        schema = {'$ref': uri + '#/components/schemas/' + names[case['schema']]}
        Draft202012Validator(schema, registry=registry, format_checker=FormatChecker()).validate(case['payload'])
