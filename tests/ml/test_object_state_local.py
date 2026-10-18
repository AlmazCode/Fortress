import numpy as np
import pytest
import torch
from ml import object_state_local as local


def test_green_bag_color_signature_is_translation_invariant():
    torch.manual_seed(4);color=torch.rand(3,7,14,14)
    a=local.color_signature(color.flatten(1));b=local.color_signature(color.roll((4,7),(-2,-1)).flatten(1))
    assert a.shape==(3,19);torch.testing.assert_close(a,b)


def test_camera_anchor_uses_only_training_geometry_and_returns_valid_static_boxes():
    rows=[]
    for value,box in ((0.,[.1,.2,.3,.5]),(1.,[.5,.3,.8,.7])):
        features=np.zeros((4,10588),np.float32);features[:,9216:]=value
        rows.append({'position_features':features,'boxes':[[[4,*box]]] *4})
    model=local.bbox_fit(rows,4)
    for row in rows:
        predicted=local.bbox_predict(model,torch.tensor(row['position_features'][:,9216:]))
        torch.testing.assert_close(predicted[0],torch.tensor(row['boxes'][0][0][1:]))
        torch.testing.assert_close(predicted[0],predicted[-1])
    assert local.bbox_fit([{**r,'boxes':[[]]*4} for r in rows],4)['supported'] is False


def test_visible_bag_departure_probe_requires_person_and_operator_observation():
    scores=torch.zeros(12,20);scores[:,18]=1;scores[:4,7]=1
    support=torch.ones(20,dtype=torch.bool);support[10]=False
    _,risk,available=local.state_summary(scores,support);assert risk[0]>.5 and available[0]
    scores[:,8]=1;_,risk,_=local.state_summary(scores,support);assert risk[0]==0
    support[8]=False;_,risk,available=local.state_summary(scores,support);assert risk[0]==0 and not available[0]


def test_color_presence_fit_masks_unknown_and_requires_both_classes():
    features=np.zeros((6,10588),np.float32);features[3:,9216+196:9216+392]=.1
    target=torch.full((6,20),-1.);target[:,18]=torch.tensor([0,0,0,1,1,1])
    row={'position_features':features,'actions':target,'object_known':torch.zeros(6,10,dtype=torch.bool),'boxes':[[]]*6}
    model=local.presence_fit([row],True);assert model['supported'] and torch.isfinite(model['weight']).all()
    row['actions'][:]=-1;unknown=local.presence_fit([row],True)
    assert not unknown['supported'] and (unknown['weight']==0).all()
