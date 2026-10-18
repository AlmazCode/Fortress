"""Offline package lineage and actual temporal-head numerical round trip."""
import json
from types import SimpleNamespace

import pytest
import torch
import torchvision

from ml import temporal_actions as training
from ml import temporal_actions_infer as runtime
from ml.video_baseline import atomic_json, atomic_checkpoint
from ml.models.encoder import file_sha256


@pytest.fixture
def candidate(tmp_path,monkeypatch):
    torch.manual_seed(7);torch.set_num_threads(1)
    experiment=tmp_path/'experiment';experiment.mkdir()
    model=training.TemporalOperations().eval()
    protocol='a'*64
    state={'train_ids':['unit-a','unit-b'],'protocol_sha256':protocol,'threshold':.4,
           'action_thresholds':[1.]+[.6]*(len(training.TAXONOMY)-1),'model':model.state_dict(),
           'normalization':{'mean':torch.zeros(training.DIM),'scale':torch.ones(training.DIM)},
           'fine_support':torch.ones(len(training.TAXONOMY),dtype=torch.bool),
           'coarse_support':torch.ones(len(training.COARSE),dtype=torch.bool)}
    atomic_checkpoint(experiment/'final.pt',state)
    atomic_json(experiment/'protocol.json',{'code_sha256':training.code_hash(),'development_ids':state['train_ids'],
                'protocol_sha256':protocol,'encoder_weights':'unit-only-no-download','encoder_sha256':'b'*64})
    report={'protocol_sha256':protocol,'promoted_clip_model':False,'results':{'temporal_actions':{
        'mean':{'accuracy':.5,'balanced_accuracy':.5,'macro_f1':.5},
        'actions':{'classes':[{'class':name,'precision':.8,'recall':.7,'interval_precision_proxy':.7}
                              for name in training.TAXONOMY[1:]]}}}}
    atomic_json(experiment/'cv_report.json',report)
    atomic_json(experiment/'complete.json',{'report_sha256':file_sha256(experiment/'cv_report.json'),
                                          'fit_sha256':file_sha256(experiment/'final.pt')})
    # Random encoder is confined to a unit-test package; never an application fallback.
    encoder=torchvision.models.mobilenet_v3_small(weights=None).features.eval()
    monkeypatch.setattr(runtime,'FrozenEncoder',lambda **kwargs:SimpleNamespace(features=encoder))
    bundle=tmp_path/'unit-test-only-bundle'
    metadata=runtime.export(experiment,bundle)
    return bundle,metadata,state


def test_package_roundtrip_keeps_actual_temporal_scores_and_source_pts(candidate):
    bundle,metadata,state=candidate
    predictor=runtime.Predictor(bundle,'cpu')
    values=torch.randn(5,training.DIM)
    result=predictor.predict_features(values,[0,50,100,150,200],[0.,.5,1.,1.5,2.])
    model=training.TemporalOperations().eval();model.load_state_dict(state['model'])
    with torch.inference_mode():expected=float(model(values[None],torch.tensor([5]))[0].sigmoid()[0])
    assert result['score']==expected
    assert [f['source_pts'] for f in result['frames']]==[0,50,100,150,200]
    assert result['normative_status']=='unknown' and not metadata['clip_promoted']
    assert (bundle/'weights.pt').stat().st_size<training.MAX_BYTES


@pytest.mark.parametrize('field,value',[('threshold',.1),('action_thresholds',[1.]*len(training.TAXONOMY)),('clip_promoted',True)])
def test_decision_fields_cannot_change_without_changing_bound_weights(candidate,field,value):
    bundle,metadata,_=candidate
    metadata[field]=value
    (bundle/'bundle.json').write_text(json.dumps(metadata),encoding='utf-8')
    with pytest.raises(ValueError):runtime.Predictor(bundle,'cpu')


def test_changed_evaluation_or_weights_are_rejected(candidate):
    bundle,_,_=candidate
    (bundle/'evaluation.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='evaluation changed'):runtime.Predictor(bundle,'cpu')
