"""Weak operation masks, temporal padding, and actual optimizer isolation."""
import copy
import torch
import pytest

from ml import temporal_actions as m


def record(name='receive_cash',start=2.,end=5.,role='cashier'):
    return {'event_type':'action.'+name,'start_sec':start,'end_sec':end,
            'weak_source_record':{'actor_role':role,'label_kind':'observable_action','known':True,
                                  'reviewed':True,'boundary_uncertainty_sec':1.}}


def test_weak_labels_use_only_supplied_interiors_and_cashier_not_customer():
    times=[0.,2.,2.5,3.,4.,4.5,5.,8.]
    y=m.operation_targets([record(),record('give_cash',6.,9.,'customer')],times)
    assert torch.where(y.sum(1)>0)[0].tolist()==[3,4]
    assert torch.all(y[[0,1,2,5,6,7]]==0)
    assert y[3,m.TAXONOMY.index('cash_exchange')]==1


def test_overlapping_operations_share_mass_without_making_unlabelled_frames_negative():
    y=m.operation_targets([record(),record('manual_count_cash')],[0.,3.,4.,8.])
    assert y[1].sum()==1 and y[1,m.TAXONOMY.index('cash_exchange')]==.5
    assert y[1,m.TAXONOMY.index('cash_handling')]==.5 and y[0].sum()==0


def test_unknown_or_inferred_nonvisual_labels_are_not_supervision():
    value=record();value['weak_source_record']['known']=False
    other=record();other['weak_source_record']['label_kind']='normative_inference'
    assert m.operation_targets([value,other],[3.,4.]).sum()==0
    with pytest.raises(ValueError):m.operation_targets([record(start=5.,end=2.)],[3.])


def rows():
    generator=torch.Generator().manual_seed(19)
    result=[]
    for n in range(4):
        fine=torch.zeros(5,len(m.TAXONOMY));fine[1:4,1+n%2]=1
        result.append({'video_id':f'v{n}','group_id':f'family{n}','target':n%2,
                       'features':torch.randn(3,5,m.DIM,generator=generator),'fine':fine,
                       'coarse':torch.tensor([[n%2]*len(m.COARSE)]*5),'times':torch.arange(5)/2})
    return result


def test_class_support_counts_independent_training_families():
    data=rows();enabled,*_=m.support(data)
    assert enabled[1] and enabled[2] and not enabled[3]
    data[2]['group_id']=data[0]['group_id']
    assert not m.support(data)[0][1]


def test_training_and_normalization_ignore_changed_held_out_rows():
    torch.set_num_threads(1)
    data=rows();held_out=copy.deepcopy(data[0]);held_out['video_id']='held-out'
    before=m.fit(data,'temporal_actions',42,'cpu',epochs=2)
    before_prediction=m.predict(before,[held_out],'cpu')[0]
    held_out['features'].fill_(999);held_out['fine'].fill_(0);held_out['target']=1-held_out['target']
    after=m.fit(data,'temporal_actions',42,'cpu',epochs=2)
    for name in before['model']:assert torch.equal(before['model'][name],after['model'][name])
    assert torch.equal(before['normalization']['mean'],after['normalization']['mean'])
    assert before['train_ids']==after['train_ids']
    # A new, untouched video has the same prediction with each deterministic fit.
    assert m.predict(before,[data[0]],'cpu')[0]['score']==m.predict(after,[data[0]],'cpu')[0]['score']
    predictions=m.predict(before,data,'cpu')
    assert all(type(p['truth']) is bool for p in predictions)
    assert 0 <= m.clip_threshold(predictions) <= 1


def test_padding_does_not_leak_the_next_video_into_valid_predictions():
    torch.manual_seed(1);model=m.TemporalOperations().eval()
    x=torch.randn(1,5,m.DIM)
    padded=torch.cat((x,torch.zeros(1,4,m.DIM)),1)
    with torch.inference_mode():
        a=model(x,torch.tensor([5]));b=model(padded,torch.tensor([5]))
    assert torch.allclose(a[0],b[0],atol=1e-6,rtol=0)
    assert torch.allclose(a[2],b[2][:,:5],atol=1e-6,rtol=0)
