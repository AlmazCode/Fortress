import numpy as np
import pytest
import torch
from ml import state_focus as focus,state_focus_inputs as inputs


def test_pixel_features_preserve_color_and_positional_geometry():
    torch.set_num_threads(2)
    rgb=torch.zeros(2,3,448,448);rgb[1,1,:,:224]=1
    mean=torch.tensor((.485,.456,.406))[None,:,None,None];std=torch.tensor((.229,.224,.225))[None,:,None,None]
    color=inputs.color_features((rgb-mean)/std)
    assert color.shape==(2,inputs.COLOR_DIM)
    grid=color[1,:3*14*14].reshape(3,14,14)
    assert grid[1,:,:7].mean()>.99 and grid[1,:,7:].mean()<.01
    maps=torch.zeros(2,576,14,14);maps[1,:,:7,:7]=1
    x=inputs.combine(maps,color)
    assert x.shape==(2,inputs.DIM) and not torch.equal(x[0],x[1])


def test_weighted_ridge_matches_primal_with_unpenalized_intercept():
    torch.manual_seed(2);x=torch.randn(9,5,dtype=torch.float64);y=torch.randn(9,dtype=torch.float64);w=torch.rand(9,dtype=torch.float64)+.1
    model=focus.ridge(x,y,w,.7);w=w/w.sum()*len(w);xm=(x*w[:,None]).sum(0)/w.sum();ym=(y*w).sum()/w.sum()
    centered=x-xm;coefficient=torch.linalg.solve(centered.T@(centered*w[:,None])+torch.eye(5)*.7,centered.T@(w*(y-ym)))
    torch.testing.assert_close(model['weight'],coefficient)
    torch.testing.assert_close(model['bias'],ym-xm@coefficient)
    with pytest.raises(ValueError):focus.ridge(x,y,w,-1.)


def test_masked_state_fit_never_trains_unsupported_classes_and_roundtrips(monkeypatch):
    torch.manual_seed(3);monkeypatch.setattr(inputs,'CNN_DIM',8);monkeypatch.setattr(inputs,'COLOR_DIM',4)
    x=torch.randn(12,12);target=torch.full((12,20),-1.);target[:,4]=torch.tensor([0]*6+[1]*6);target[:,7]=1
    groups=torch.arange(12)//3
    base=focus.state_fit(x,target,groups,False,'cpu');hard=focus.state_fit(x,target,groups,True,'cpu')
    assert base['support'][4] and not base['support'][7]
    prediction=focus.state_predict(hard,x)
    assert (prediction[:,7]==0).all() and (base['weight'][:,7]==0).all()
    assert (prediction[:,4].isfinite()).all()
    changed=target.clone();changed[:,7]=-1
    other=focus.state_fit(x,changed,groups,False,'cpu')
    torch.testing.assert_close(base['weight'][:,4],other['weight'][:,4])


def test_persistence_rejects_single_frame_spike_and_requires_observed_departure():
    scores=torch.zeros(12,20);support=torch.ones(20,dtype=torch.bool)
    scores[:,7]=1;scores[-1,19]=1
    _,risk,_=focus.state_summary(scores,support);assert risk[2]==0
    scores[:4,19]=1;scores[-6:,19]=1;scores[-6:,7]=0
    _,risk,available=focus.state_summary(scores,support);assert risk[2]>=.5 and available[2]
    support[7]=False
    _,risk,available=focus.state_summary(scores,support);assert risk[2]==0 and not available[2]


def test_readout_pairs_use_only_requested_training_families_and_unknown_is_not_a_feature():
    values=torch.tensor([[0.,1],[1,2],[2,3],[3,4]]);truth=torch.tensor([0.,1,0,1])
    result=focus.fit_readout(values,truth,['a','a','b','c'],.1,[2])
    assert result['training_pairs']==1 and torch.isfinite(focus.readout_predict(result,values)).all()
    e=object.__new__(focus.Experiment);e.plan={'development_ids':['a','b']}
    with pytest.raises(ValueError):e.frame_fit(['reserved'],False)
    with pytest.raises(ValueError):e.fit(['a','a'],{})


def test_visual_tail_change_is_directional_not_a_source_identifier():
    values=torch.arange(20,dtype=torch.float32).reshape(5,4)
    forward=focus.visual_summary(values);reverse=focus.visual_summary(values.flip(0))
    torch.testing.assert_close(forward[:8],reverse[:8]);torch.testing.assert_close(forward[8:],-reverse[8:])
    assert len(focus.candidates())==23 and len({c['name'] for c in focus.candidates()})==23


def test_real_state_clip_fit_checkpoint_and_heldout_prediction(tmp_path):
    e=object.__new__(focus.Experiment);e.device='cpu';e.fits=tmp_path;e.memo={};e.old={}
    e.plan={'development_ids':['a','b'],'protocol_sha256':'a'*64};e.rows={}
    rng=np.random.default_rng(4)
    for n,video in enumerate(('a','b','heldout')):
        target=torch.full((4,20),-1.);target[:,7]=torch.tensor([1,1,0,0]);target[:,9]=torch.tensor([0,1,1,0])
        e.rows[video]={'target':n%2,'group_id':'pair','actions':target,'position_features':rng.normal(size=(4,inputs.DIM)).astype(np.float32)}
    c={'name':'fused_base_1','arm':'fused','hard':False,'alpha':1.}
    path=e.fit(['a','b'],c);p=e.predict(path,['heldout'])
    assert len(p)==1 and 0<=p[0]['score']<=1 and len(list(tmp_path.glob('*.pt')))==2
    assert e.fit(['a','b'],c)==path
