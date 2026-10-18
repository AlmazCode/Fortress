import copy
import pytest
import torch
from ml import boundary_temporal as model,boundary_inputs as data
from ml.video_baseline import atomic_json


def test_causal_frame_prefix_and_padding_do_not_change_clip_or_known_frames():
    torch.set_num_threads(2);torch.manual_seed(5)
    net=model.BoundaryNet(dimension=8,hidden=4,dropout=0.).eval();support=torch.ones(6,dtype=torch.bool)
    x=torch.randn(1,9,8)
    with torch.no_grad():
        clip,states=net(x,torch.tensor([9]),support)
        _,prefix=net(x[:,:5],torch.tensor([5]),support)
        padded=torch.cat((x,torch.randn(1,4,8)*100),1);cp,sp=net(padded,torch.tensor([9]),support)
    torch.testing.assert_close(prefix,states[:,:5]);torch.testing.assert_close(cp,clip);torch.testing.assert_close(sp[:,:9],states)


def test_unknown_and_single_class_heads_have_no_auxiliary_gradient_and_sources_balance():
    targets=torch.full((2,10,6),-1.);targets[0,:4,0]=torch.tensor([0.,0.,1.,1.]);targets[1,:,0]=torch.tensor([0.]*5+[1.]*5)
    targets[:,:,1]=1.
    weights,support=model.frame_weights(targets,edge_weight=1.)
    assert support.tolist()==[True,False,False,False,False,False]
    torch.testing.assert_close(weights[:,:,0].sum(1),torch.tensor([.5,.5]))
    logits=torch.randn_like(targets,requires_grad=True)
    loss=(torch.nn.functional.binary_cross_entropy_with_logits(logits,targets.clamp_min(0),reduction='none')*weights).sum();loss.backward()
    assert torch.equal(logits.grad[targets<0],torch.zeros_like(logits.grad[targets<0]))
    assert torch.count_nonzero(logits.grad[:,:,1:])==0
    stronger,_=model.frame_weights(targets,edge_weight=3.)
    assert stronger[0,1,0]>stronger[0,0,0]


def test_exact_review_requires_development_source_and_evidence_timestamps():
    rows=[{'video_id':'a','source_sha256':'sha','source_pts':torch.tensor([10,20])}]
    evidence=[{'video_id':'a','source_sha256':'sha','source_pts':p,'timestamp_sec':t,'image_sha256':str(p)} for p,t in [(10,0.),(20,.5)]]
    video={'video_id':'a','source_sha256':'sha','evidence':evidence,'observations':[{'source_pts':e['source_pts'],'timestamp_sec':e['timestamp_sec'],'image_sha256':e['image_sha256'],'values':[0,0,0,0,-1,-1]} for e in evidence],
           'transitions':[{'type':'safe_opening','before_pts':10,'after_pts':20,'earliest_sec':0.,'latest_sec':.5}]}
    review={'version':'object-boundary-review-v1','taxonomy':list(data.TAXONOMY),'human_approved':False,'original_verdicts_changed':False,'original_source_bytes_changed':False,'videos':[video]}
    result=data.exact_review(review,copy.deepcopy(rows),{'development_ids':['a']});assert result['a']['boundary_targets'].shape==(2,6)
    bad=copy.deepcopy(review);bad['videos'][0]['observations'][0]['timestamp_sec']=.01
    with pytest.raises(ValueError,match='exact evidence'):data.exact_review(bad,copy.deepcopy(rows),{'development_ids':['a']})
    bad=copy.deepcopy(review);bad['videos'][0]['video_id']='reserved'
    with pytest.raises(ValueError,match='development'):data.exact_review(bad,copy.deepcopy(rows),{'development_ids':['a']})
    bad=copy.deepcopy(review);bad['videos'][0]['observations'].append(copy.deepcopy(bad['videos'][0]['observations'][0]))
    with pytest.raises(ValueError,match='invalid boundary target'):data.exact_review(bad,copy.deepcopy(rows),{'development_ids':['a']})


def test_region_features_have_fixed_dimensions_and_reject_nan():
    maps=torch.randn(3,576,14,14);color=torch.randn(3,1372)*.01
    x=data.features(maps,color);assert x.shape==(3,3503) and torch.isfinite(x).all()
    maps[0,0,0,0]=float('nan')
    with pytest.raises(ValueError,match='finite'):data.features(maps,color)


def test_two_observations_confirm_physical_change_without_inventing_initial_event():
    p=torch.zeros(8,6);p[:,3]=1.;p[:,0]=torch.tensor([0.,0.,1.,1.,1.,0.,0.,0.]);pts=list(range(8));timing={n:n*.5 for n in pts}
    events=model.observed_events(p,torch.ones(6,dtype=torch.bool),pts,timing)
    assert [(e['type'],e['time_sec'],e['confirmed_at_sec']) for e in events]==[('safe_opening',1.,1.5),('safe_closing',2.5,3.)]
    events=model.observed_events(p,torch.zeros(6,dtype=torch.bool),pts,timing);assert events==[]


def test_event_match_can_use_exact_fine_bracket_across_unknown_coarse_frame(tmp_path):
    folder=tmp_path/'indices';folder.mkdir();atomic_json(folder/'a.json',{'frames':[{'source_pts':n,'timestamp_sec':n*.5} for n in range(6)]})
    target=torch.zeros(6,6);target[1,0]=-1;target[2:4,0]=1.
    pred=torch.zeros(6,6);pred[2:4,0]=1.
    rows={'a':{'video_id':'a','source_pts':list(range(6)),'boundary_targets':target,'events':[{'type':'safe_opening','earliest_sec':.7,'latest_sec':.8}]}}
    result=model.event_metrics([{'video_id':'a','actions':pred,'actions_supported':torch.ones(6,dtype=torch.bool)}],rows,tmp_path)
    m=result['by_type']['safe_opening'];assert m['tp']==1 and m['fp']==m['fn']==0


def test_real_tiny_neural_training_and_readout_preserve_unsupported_states():
    torch.set_num_threads(2);torch.manual_seed(4);rows=[]
    for n in range(4):
        x=torch.randn(5+n,3503)*.1;y=torch.full((len(x),6),-1.);y[:2,0]=0.;y[2:,0]=1.;y[:,1]=0.
        rows.append({'video_id':str(n),'features':x,'boundary_targets':y,'target':n%2,'group_id':str(n//2)})
    state=model.fit_model(rows,42,{**model.CONFIG,'epochs':3},device='cpu')
    assert state['epochs']==3 and state['support'].tolist()==[True,False,False,False,False,False]
    predictions=model.predict_model(state,rows,'cpu');assert len(predictions)==4
    assert all(0<=p['tcn']<=1 and 0<=p['ridge']<=1 for p in predictions)
    assert all(torch.count_nonzero(p['actions'][:,1:])==0 for p in predictions)


def test_reserved_sources_cannot_enter_fit():
    e=object.__new__(model.Experiment);e.plan={'development_ids':['a','b']}
    e.guard(['a','b'])
    with pytest.raises(ValueError):e.guard(['a','reserved'])
    with pytest.raises(ValueError):e.guard(['a','a'])
