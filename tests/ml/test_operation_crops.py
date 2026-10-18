from PIL import Image
import pytest
import torch
from ml.operation_crops import tensors,ROIS


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_detail_views_apply_source_rotation_and_keep_four_normalized_regions(rotation):
    source=Image.new('RGB',(46,84),(255,0,0))
    values=tensors(source,{'width':46,'height':84,'rotation':rotation})
    assert values.shape==(len(ROIS),3,448,448) and torch.isfinite(values).all()
    mean=torch.tensor((.485,.456,.406))[None,:,None,None]
    std=torch.tensor((.229,.224,.225))[None,:,None,None]
    rgb=values*std+mean
    for frame in rgb:
        assert frame[0].max()>.99 and frame[1:].abs().max()<1e-6
