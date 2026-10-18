import pytest
import torch
from ml.dino_probe import summary, fit, predict, validate_folds


def test_temporal_summary_preserves_order_and_single_frame_is_finite():
    x=torch.tensor([[1.,2.],[3.,4.],[6.,8.],[9.,12.]])
    assert torch.allclose(summary(x,'appearance'),summary(x.flip(0),'appearance'))
    assert not torch.allclose(summary(x,'temporal'),summary(x.flip(0),'temporal'))
    assert torch.isfinite(summary(x[:1],'temporal')).all()


def test_readout_statistics_are_training_only_and_do_not_mutate_on_prediction():
    rows=[{'video_id':str(i),'features':torch.tensor([[float(i),1.],[float(i)+.1,2.]]),'target':i>=2} for i in range(4)]
    state=fit(rows,{'mode':'appearance','ridge':.1})
    before={k:state[k].clone() for k in ('mean','scale','weight')}
    values=predict(state,[{'video_id':'foreign','features':torch.full((2,2),1000.),'target':False}])
    assert 0<=values[0]['score']<=1
    assert all(torch.equal(before[k],state[k]) for k in before)
    assert state['train_ids']==['0','1','2','3']


def test_invalid_features_and_single_class_are_rejected():
    with pytest.raises(ValueError):summary(torch.tensor([[float('nan')]]),'temporal')
    with pytest.raises(ValueError):fit([{'video_id':'0','features':torch.ones(2,2),'target':False}],{'mode':'appearance','ridge':1.})


def test_same_family_is_rejected_even_when_video_ids_differ():
    data={'a':{'group_id':'same'},'b':{'group_id':'same'}}
    with pytest.raises(ValueError,match='family leakage'):
        validate_folds(data,[{'train':['a'],'validation':['b']}],data)
