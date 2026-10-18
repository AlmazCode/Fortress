import copy
import numpy as np
import pytest
import torch
from ml import object_events as events
from ml import object_event_inputs as data
from ml.models.encoder import safe_torch_load


def test_crop_box_projection_keeps_clipped_source_geometry():
    assert data.box_to_roi([0,0,10,10],464,848) is None
    box=data.box_to_roi([100,300,90,100],464,848)
    assert 0<=box[0]<box[2]<=1 and 0<=box[1]<box[3]<=1
    assert box[2]-box[0]==pytest.approx(90/464,abs=1e-6)


def test_center_targets_decode_without_learning_absolute_camera_position():
    box=[3,.12,.23,.41,.57]
    heat,reg,mask,_=events.object_targets([[box]],torch.ones(1,10,dtype=torch.bool))
    iy,ix=mask[0,3].nonzero()[0].tolist();v=reg[0,3,:,iy,ix]
    assert (ix+v[0])/14==pytest.approx((box[1]+box[3])/2)
    assert (iy+v[1])/14==pytest.approx((box[2]+box[4])/2)
    assert heat[0,3,iy,ix]==1


def test_all_unknown_object_and_action_targets_have_zero_gradient():
    torch.set_num_threads(2);model=events.SpatialHeads()
    x=torch.randn(2,576,14,14);target=events.object_targets([[],[]],torch.zeros(2,10,dtype=torch.bool))
    actions=torch.full((2,18),-1.);weights=events.auxiliary_weights(actions[None])
    loss=events.frame_loss(model(x),target,actions,weights);loss.backward()
    assert loss==0
    assert all(p.grad is None or (p.grad==0).all() for p in model.parameters())


def test_spatial_outputs_and_unsupported_categories():
    model=events.SpatialHeads().eval();model.object_support[8]=False
    with torch.no_grad():heat,boxes,state,uniform,focused,meta=model(torch.randn(2,576,14,14))
    assert heat.shape==(2,10,14,14) and boxes.shape==(2,10,4,14,14)
    assert state.shape==(2,18) and focused.shape==uniform.shape==(2,576)
    assert meta.shape==(2,68) and (meta[:,18+8]==0).all()
    assert (meta[:,28+8*4:28+9*4]==0).all()


def test_rule_probes_preserve_unknown_and_never_claim_normative_validation():
    states=torch.ones(5,18)*.9;objects=torch.ones(5,10)*.9;prior=torch.zeros(5,14,14)
    support=torch.ones(18,dtype=torch.bool);support[7]=False
    out=events.rule_diagnostics(states,objects,prior,support)
    assert out[0]['score'] is None and out[1]['score'] is None and out[2]['score'] is None
    assert all(r['normative_status']=='unknown' and r['recognizer_validated'] is False for r in out)
    objsupport=torch.ones(10,dtype=torch.bool);objsupport[5]=False
    support[:]=True
    assert events.rule_diagnostics(states,objects,prior,support,objsupport)[8]['score'] is None


def test_rule_temporal_combination_respects_operator_presence():
    states=torch.zeros(10,18);states[:,10]=1;states[:,7]=1
    prior=torch.zeros(10,14,14);objects=torch.zeros(10,10);support=torch.ones(18,dtype=torch.bool)
    attended=events.rule_features(states,objects,prior,support)
    states[-8:,7]=0;unattended=events.rule_features(states,objects,prior,support)
    assert attended[0]==0 and unattended[0]==1


def test_cup_background_calibration_has_explicit_train_negative_contract():
    calibration=events.cup_background_calibration([.001,.002,.003,.004])
    scores=events.calibrate_cup_prior(torch.tensor([1e-8,.1]),calibration)
    assert scores[0]<.01 and scores[1]>.9
    with pytest.raises(ValueError):events.cup_background_calibration([])


def test_real_rule_engine_bridge_cannot_turn_experimental_scores_into_clean_or_legal_findings():
    from rules.engine import evaluate_template
    evidence=events.technical_rule_inputs('video','scene',0,10)
    for value in evidence.values():
        for template in ('presence','unresolved-state','prerequisite'):
            assert evaluate_template(template,value)=='unknown'


def test_temporal_padding_and_action_causality():
    torch.manual_seed(4);model=events.Temporal().eval();values=torch.randn(2,7,646);lengths=torch.tensor([3,7])
    with torch.no_grad():
        v,a=model(values,lengths);values[0,3:]=100;values[1,4:]=100
        vv,aa=model(values,lengths)
    torch.testing.assert_close(v[0],vv[0]);torch.testing.assert_close(a[0,:3],aa[0,:3]);torch.testing.assert_close(a[1,:4],aa[1,:4])


def test_training_rejects_reserved_or_duplicate_sources_before_io():
    experiment=object.__new__(events.Experiment);experiment.plan={'development_ids':['v1']}
    with pytest.raises(ValueError):experiment.fit(['v2'],'objects',42)
    with pytest.raises(ValueError):experiment.train_spatial(['v1','v1'],42)


def test_group_folds_reject_related_sources_on_both_sides():
    folds=[{'train':['a'],'validation':['b']},{'train':['b'],'validation':['a']}]
    events.validate_folds(folds,['a','b'],{'a':'g1','b':'g2'})
    with pytest.raises(ValueError,match='family leakage'):events.validate_folds(folds,['a','b'],{'a':'g','b':'g'})
    with pytest.raises(ValueError):events.validate_folds(folds[:1],['a','b'],{'a':'g1','b':'g2'})


def test_localization_metric_excludes_unsupported_and_reports_top1_not_map():
    known=torch.zeros(2,10,dtype=torch.bool);known[:,4]=True;known[0,8]=True
    rows={'v':{'object_known':known,'boxes':[[[4,.25,.25,.75,.75],[8,.1,.1,.2,.2]],[]]}}
    boxes=torch.zeros(2,10,4);boxes[:,4]=torch.tensor([.5,.5,.5,.5]);support=torch.ones(10,dtype=torch.bool);support[8]=False
    o={'video_id':'v','object_support':support,'objects':torch.ones(2,10)*.9,'boxes':boxes}
    metrics=events.localization_metrics([o],rows)
    assert metrics['safe_7']['mean_top1_iou']==1 and metrics['safe_7']['localized_recall_iou50_score50']==1
    assert metrics['safe_7']['negative_false_alarm_rate']==1 and metrics['safe_7']['is_map'] is False
    assert metrics['cup']['unsupported_known_frames']==1 and metrics['cup']['mean_top1_iou'] is None


def test_real_spatial_temporal_checkpoint_and_heldout_prediction(tmp_path,monkeypatch):
    torch.set_num_threads(2)
    monkeypatch.setattr(events,'CONFIG',{**events.CONFIG,'frame_epochs':1,'pretrain_epochs':1,'epochs':1})
    experiment=object.__new__(events.Experiment);experiment.directory=tmp_path;experiment.fits=tmp_path;experiment.memo={};experiment.device='cpu'
    experiment.plan={'development_ids':['v0','v1'],'protocol_sha256':'b'*64};experiment.rows={}
    rng=np.random.default_rng(2)
    for n in range(3):
        actions=torch.full((4,18),-1.);actions[:,0]=torch.tensor([0,0,1,1]);actions[:,7]=torch.tensor([1,1,0,0])
        maps=rng.normal(size=(4,576,14,14)).astype(np.float16)
        experiment.rows[f'v{n}']={'video_id':f'v{n}','target':n%2,'group_id':'pair','split':'train' if n<2 else 'independent_test',
             'actions':actions,'maps':[maps]*3,'cup_prior':np.zeros((4,14,14),dtype=np.float32),
             'object_known':torch.ones(4,10,dtype=torch.bool),'boxes':[[[4,.4,.3,.6,.7]] for _ in range(4)]}
    path=experiment.fit(['v0','v1'],'objects',42);state=safe_torch_load(path)
    assert state['identity']['ids']==['v0','v1']
    prediction=experiment.predict(path,['v2'])[0]
    assert 0<=prediction['gru']<=1 and 0<=prediction['linear']<=1
    assert len(list(tmp_path.glob('*.pt')))==2
