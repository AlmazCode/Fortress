import numpy as np
import pytest
import torch
from ml import object_state_refine as refine,state_focus as parent


def test_roi_sampling_normalizes_object_location_and_preserves_channels():
    maps=torch.zeros(2,2,14,14);maps[0,:,2:6,2:6]=1;maps[1,:,8:12,8:12]=1
    boxes=torch.tensor([[2/14,2/14,6/14,6/14],[8/14,8/14,12/14,12/14]])
    result=refine.roi_pool(maps,boxes,2)
    assert result.shape==(2,8)
    torch.testing.assert_close(result[0],result[1]);assert (result>.99).all()
    with pytest.raises(ValueError):refine.roi_pool(maps,boxes[:1])


def test_multioutput_ridge_agrees_with_individual_weighted_regressions():
    torch.manual_seed(5)
    for shape in ((9,5),(5,9)):
        x=torch.randn(*shape);y=torch.randn(shape[0],3);w=torch.rand(shape[0])+.1
        result=refine.multi_ridge(x,y,w,.8)
        for c in range(3):
            other=parent.ridge(x,y[:,c],w,.8)
            torch.testing.assert_close(result['weight'][:,c],other['weight'],atol=1e-5,rtol=1e-4)
            torch.testing.assert_close(result['bias'][c],other['bias'],atol=1e-5,rtol=1e-4)


def test_real_supervised_bag_and_object_roi_fit_require_explicit_evidence():
    torch.set_num_threads(2);rng=np.random.default_rng(5);rows=[]
    for video in range(2):
        maps=rng.normal(size=(4,576,14,14)).astype(np.float16)
        color=rng.uniform(size=(4,1372)).astype(np.float32);features=np.concatenate((np.zeros((4,9216),np.float32),color),1)
        targets=torch.full((4,20),-1.);targets[:,18]=torch.tensor([0,1,0,0])
        known=torch.zeros(4,10,dtype=torch.bool);known[:,7]=True
        boxes=[[[4,.5,.3,.7,.7],[1,.1,.3,.3,.5]] for _ in range(4)];boxes[1].append([7,.2,.4,.4,.6])
        rows.append({'maps':[maps]*3,'position_features':features,'actions':targets,'object_known':known,'boxes':boxes})
    state=refine.bag_fit(rows,'cpu',True)
    assert state['positive_patches']==8 and state['negative_patches']==48
    values=refine.pixels(rows[0]);score,boxes=refine.bag_predict(state,values)
    assert score.shape==(4,) and boxes.shape==(4,4) and torch.isfinite(score).all()
    bbox=refine.bbox_fit(rows,4,'cpu');prediction=refine.bbox_predict(bbox,torch.tensor(rows[0]['position_features'][:,9216:]))
    assert (prediction[:,2:]>prediction[:,:2]).all() and (prediction>=0).all() and (prediction<=1).all()
    missing=[{**r,'boxes':[[] for _ in range(4)],'actions':torch.full((4,20),-1.),'object_known':torch.zeros(4,10,dtype=torch.bool)} for r in rows]
    unsupported=refine.bag_fit(missing,'cpu',False)
    assert unsupported['supported'] is False and (refine.bag_predict(unsupported,values)[0]==0).all()
    assert refine.bbox_fit(missing,4,'cpu')['supported'] is False


def test_unknown_roi_states_stay_unsupported():
    x=torch.randn(6,5247);target=torch.full((6,2),-1.);target[:,0]=torch.tensor([0,0,0,1,1,1])
    state=refine.appearance_fit(x,target,torch.arange(6)//2,True,'cpu')
    assert state['support'].tolist()==[True,False]
    assert (state['weight'][:,1]==0).all() and torch.isfinite(state['weight']).all()
