import numpy as np
import pytest
import torch
from ml.action_kernel import frame_features,statistics,threshold,representation


def test_unknown_is_not_a_negative_and_unavailable_positive_counts_as_miss():
    m=statistics([1,0,-1,1],[.9,.1,.99,float('nan')],.5)
    assert (m['tp'],m['fp'],m['fn'])==(1,0,1)
    assert m['positive']==2 and m['negative']==1


def test_threshold_has_required_precision_and_handles_equal_scores():
    y=np.array([1,1,0,0,-1]);p=np.array([.9,.8,.7,.7,.99])
    t=threshold(y,p);m=statistics(y,p,t)
    assert m['precision']==1 and m['recall']==1
    assert threshold(np.array([0,0]),np.array([.2,.3]))>1


def test_motion_order_and_training_only_kernel_statistics():
    x=torch.randn(5,3840,generator=torch.Generator().manual_seed(3))
    original=frame_features(x,'motion');changed=frame_features(x.flip(0),'motion').flip(0)
    assert not torch.allclose(original,changed)
    train=[{'video_id':'train','features':x}]
    _,a=representation(train,train,'motion',2.)
    _,b=representation(train,train+[{'video_id':'held','features':x*10+100}],'motion',2.)
    assert all(torch.equal(a[k],b[k]) for k in ('anchors','mean','scale'))
    with pytest.raises(ValueError):frame_features(torch.full((2,3840),float('nan')),'motion')
