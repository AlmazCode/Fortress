import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from tools.label_review import ReviewStore,create_app,QUESTIONS,digest


@pytest.fixture
def dataset(tmp_path):
    manifest={'version':'test-only','questions':QUESTIONS,'videos':[{'id':'video_001','source_sha256':'a'*64,
             'group_id':'family_1','time_base':{'num':1,'den':100},'origin_pts':0,'duration_sec':2}],
              'frames':[{'id':f'frame-{n}','video_id':'video_001','source_pts':n*50,'timestamp_sec':n*.5} for n in range(3)]}
    manifest['sha256']=digest(manifest)
    return tmp_path,manifest


def change(frame='frame-0',question='storage_open',value='open'):
    return {'frame_id':frame,'question':question,'value':value}


def test_only_explicit_answers_are_reviewed_unknown_is_masked_and_exports_are_source_bound(dataset):
    path,manifest=dataset;store=ReviewStore(path,manifest)
    assert store.snapshot()=={'revision':0,'answers':{}}
    store.save([change(),change('frame-1',value='unknown')],0)
    export=json.loads(store.export().read_text(encoding='utf-8'))
    assert len(export['records'])==2
    assert {r['source_sha256'] for r in export['records']}=={'a'*64}
    assert {r['source_pts'] for r in export['records']}=={0,50}
    assert all(r['human_approved'] for r in export['records'])
    unknown=next(r for r in export['records'] if r['value']=='unknown')
    assert unknown['known'] is False and unknown['training_value']==-1
    assert export['training_started'] is False and export['original_labels_changed'] is False
    assert 'frame-2' not in store.snapshot()['answers']
    before=store.export().read_bytes();assert store.export().read_bytes()==before
    assert ReviewStore(path,manifest).snapshot()==store.snapshot()


def test_bulk_is_atomic_conflicts_do_not_overwrite_and_undo_survives_restart(dataset):
    path,manifest=dataset;store=ReviewStore(path,manifest)
    store.save([change(),change('frame-1',value='closed')],0)
    with pytest.raises(RuntimeError):store.save([change(value='closed')],0)
    with pytest.raises(ValueError):store.save([change(value='closed'),change('foreign')],1)
    assert store.snapshot()['answers']['frame-0']['storage_open']['value']=='open'
    store.save([change(value='closed')],1)
    store=ReviewStore(path,manifest);store.undo(2)
    assert store.snapshot()['answers']['frame-0']['storage_open']['value']=='open'
    store.undo(3)
    assert store.snapshot()=={'revision':4,'answers':{}}


def test_bag_position_does_not_fabricate_motion_or_known_absence(dataset):
    path,manifest=dataset;store=ReviewStore(path,manifest)
    store.save([change(question='bag_position',value='in_hands')],0)
    records=json.loads(store.export().read_text(encoding='utf-8'))['records']
    assert len(records)==1 and records[0]['training_class']=='bag_on_desk' and records[0]['training_value']==0
    assert records[0]['question']=='bag_position'
    assert 'bag_interaction' not in store.snapshot()['answers']['frame-0']


def test_private_session_origin_and_revision_are_required_for_mutations(dataset):
    path,manifest=dataset
    with TestClient(create_app(path,manifest)) as client:
        assert client.get('/api/session').status_code==403
        assert client.get('/').status_code==200
        assert client.get('/api/session').json()['answers']=={}
        payload={'revision':0,'changes':[change()]}
        assert client.post('/api/answers',json=payload).status_code==403
        assert client.post('/api/answers',json=payload,headers={'Origin':'https://foreign.example'}).status_code==403
        assert client.post('/api/answers',json=payload,headers={'Origin':'http://testserver'}).status_code==200
        assert client.post('/api/answers',json=payload,headers={'Origin':'http://testserver'}).status_code==409
        response=client.get('/api/export')
        assert response.status_code==200 and response.json()['human_approved_records']==1
        assert client.get('/../review.sqlite3').status_code==404
        assert client.get('/api/frame/not-a-frame').status_code==404
        assert client.get('/api/session',headers={'Host':'foreign.example'}).status_code==403
