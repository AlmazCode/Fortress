import torch
from torch.nn.utils.rnn import pad_packed_sequence
from ml import temporal_risk as risk
from ml import temporal_actions as operations
from ml import object_events as reference


def test_positive_outside_weak_interval_stays_unknown_and_normal_policy_is_explicit():
    row={'video_id':'v','target':1,'times':[0.,1.,2.,3.,4.,5.,6.]}
    annotation={'video_id':'v','label_kind':'scenario_interpretation','known':True,'start_sec':2.,'end_sec':5.,'boundary_uncertainty_sec':1.}
    y=risk.targets(row,[annotation])
    assert y.tolist()==[-1.,-1.,-1.,1.,1.,-1.,-1.]
    assert risk.targets({**row,'target':0},[annotation]).tolist()==[0.]*7


def test_hidden_capture_preserves_the_frozen_one_gru_clip_verdict():
    torch.set_num_threads(1);torch.manual_seed(9)
    model=reference.Temporal().eval();x=torch.randn(1,5,646);length=torch.tensor([5])
    with torch.inference_mode():before=model(x,length)[0].clone()
    captured=[]
    hook=model.gru.register_forward_hook(lambda module,args,out:captured.append(pad_packed_sequence(out[0],batch_first=True)[0]))
    with torch.inference_mode():after=model(x,length)[0]
    hook.remove()
    assert torch.equal(before,after) and captured[0].shape==(1,5,256)
    assert sum(isinstance(m,torch.nn.GRU) for m in model.modules())==1


def test_real_risk_optimizer_uses_known_masks_and_produces_finite_source_scores():
    torch.set_num_threads(1);torch.manual_seed(12)
    rows=[];representations={}
    for n in range(4):
        target=n%2
        rows.append({'video_id':str(n),'target':target,'risk':torch.tensor([-1.,1.,1.,-1.]) if target else torch.zeros(4)})
        values=torch.randn(4,risk.DIM)*.1
        if target:values[1:3,:5]+=1
        representations[str(n)]={'features':values,'score':.7 if target else .2}
    fitted=risk.fit(rows,representations,'cpu')
    result=risk.predict(fitted,rows,representations)
    assert fitted['train_ids']==['0','1','2','3']
    assert all(len(r['frame_risk'])==4 and torch.isfinite(r['frame_risk']).all() for r in result)
    assert result[1]['risk']>result[0]['risk']
