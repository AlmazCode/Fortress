import pytest
import torch
from PIL import Image
from ml import boundary_roi as model,boundary_crop_inputs as data
from ml.models.encoder import FrozenEncoder


def test_magnified_regions_use_actual_preprocessing_and_same_frozen_encoder():
    torch.set_num_threads(2)
    tensors=data.tensors(Image.new('RGB',(464,848),(170,190,130)),{'width':464,'height':848,'rotation':0})
    assert tensors.shape==(2,3,224,224)
    descriptor=data.descriptors(FrozenEncoder(test_only=True),tensors[None],'cpu')
    assert descriptor.shape==(1,2,960) and torch.isfinite(descriptor).all()
    with pytest.raises(ValueError):data.descriptors(FrozenEncoder(test_only=True),torch.zeros(9,2,3,224,224),'cpu')


def test_relative_safe_features_are_causal_and_bag_geometry_is_finite_when_absent():
    crops=torch.randn(8,2,960);bag=torch.zeros(8,29)
    full=model.frame_features(crops,bag)[0];prefix=model.frame_features(crops[:2],bag[:2])[0]
    torch.testing.assert_close(full[:2],prefix)
    torch.testing.assert_close(full[0,960:],torch.zeros(960))
    geometry=data.bag_geometry(torch.zeros(8,1372));assert geometry.shape==(8,29) and torch.isfinite(geometry).all()
    assert torch.count_nonzero(geometry[:,19:])==0


def test_actual_state_ridge_fit_uses_only_known_labels_and_preserves_missing_support():
    torch.set_num_threads(2);torch.manual_seed(5);rows=[]
    for n in range(3):
        crops=torch.randn(8,2,960);bag=torch.randn(8,29)*.01;target=torch.full((8,6),-1.)
        target[:4,0]=0;target[4:,0]=1;target[:,1]=0;target[:4,2]=0;target[4:,2]=1
        rows.append({'crops':crops,'bag':bag,'boundary_targets':target})
    state=model.fit_states(rows,'cpu');assert [h['supported'] for h in state]==[True,False,True,False]
    context=torch.ones(8,18)*.9;support=torch.ones(18,dtype=torch.bool);support[8]=False
    p,enabled=model.predict_states(state,rows[0]['crops'],rows[0]['bag'],context,support)
    assert enabled.tolist()==[True,False,True,False,True,False]
    assert torch.count_nonzero(p[:,[1,3,5]])==0 and (p[:,4]==.9).all()
    unknown=torch.full((8,),-1.);head=model.fit_head(torch.randn(8,5),unknown,torch.zeros(8),(5,),1.,'cpu')
    assert head['supported'] is False and torch.count_nonzero(head['weight'])==0
