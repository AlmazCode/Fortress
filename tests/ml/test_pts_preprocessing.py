import copy

import numpy as np
from PIL import Image
import pytest
import torch

from ml.preprocessing import PreprocessConfig, box_to_source, preprocess_image
from ml.windows import labelled_windows, merge_scores
from ml.data.scenes import define_scenes
from test_annotations import sample_documents, add_action
from test_pts_index import tiny_index


@pytest.fixture(scope="module",autouse=True)
def cpu_threads():
    previous=torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


@pytest.mark.parametrize("rotation",[0,90,180,270])
def test_letterbox_rgb_imagenet_and_inverse_use_actual_integer_resize(rotation):
    image=Image.new("RGB",(31,17),(255,0,0))
    output=preprocess_image(image,rotation=rotation)
    assert output["tensor"].shape==(3,224,224) and output["tensor"].dtype==torch.float32
    meta=output["transform"]
    assert box_to_source(meta["content_box"],meta)==pytest.approx([0,0,31,17],abs=1e-7)
    assert output["valid_pixel_mask"].sum().item()==meta["resized_width"]*meta["resized_height"]
    left,top,right,bottom=meta["content_box"]
    pixel=output["tensor"][:,(top+bottom)//2,(left+right)//2]
    assert pixel.tolist()==pytest.approx([(1-.485)/.229,-.456/.224,-.406/.225],abs=1e-5)
    again=preprocess_image(np.array(image),rotation=rotation)
    assert torch.equal(output["tensor"],again["tensor"])
    assert output["transform"]==again["transform"]


def test_preprocessing_rejects_double_normalization_unknown_version_and_padding_as_source():
    with pytest.raises(ValueError):preprocess_image(np.zeros((10,20,3),dtype=np.float32))
    with pytest.raises(ValueError):PreprocessConfig(channel_order="BGR")
    with pytest.raises(ValueError):PreprocessConfig(version="unimplemented")
    output=preprocess_image(Image.new("RGB",(100,20)))
    with pytest.raises(ValueError,match="content"):
        box_to_source([0,0,224,224],output["transform"])


def test_class_targets_use_actual_pts_not_grid_and_unlabeled_never_negative(tmp_path):
    data=sample_documents(tmp_path)
    classes=[c["id"] for c in data["action_taxonomy"]["classes"][:3]]
    add_action(data)
    add_action(data,start_sec=.5,end_sec=1.5,state="absent_verified")
    add_action(data,event_type=classes[1],state="unreviewed",known_mask=False,label_origin="pseudo",
               review_status="unreviewed",reviewer=None,human_approved=False,end_sec=2.5)
    add_action(data,event_type=classes[2],state="absent_verified",actor_id="specific-fixture-actor",end_sec=2.5)
    windows=labelled_windows(data["index"],data["scenes"],data["actions"],classes)
    first=windows[0]
    assert first["targets"][0]==[1,0,0] and first["known_mask"][0]==[True,False,False]
    assert first["targets"][1]==[0,0,0] and first["known_mask"][1]==[True,False,False]
    assert first["image_mask"][2] is False and not any(first["known_mask"][2])
    assert not any(any(row) for row in first["known_mask"][5:])
    assert all(not row[2] for row in first["known_mask"])
    data["actions"]["records"][2].update(state="present",known_mask=True)
    with pytest.raises(ValueError,match="unreviewed"):
        labelled_windows(data["index"],data["scenes"],data["actions"],classes)


def test_overlap_averages_source_pts_and_keeps_unknown_scores_null(tmp_path):
    index,_=tiny_index(tmp_path,points=tuple(range(4,44)))
    windows=labelled_windows(index,define_scenes(index),{"records":[]},["fixture.a","fixture.b"])
    scores=[np.ones((32,2)),np.full((32,2),3.0)]
    scores[1][-1]=np.nan  # Tail padding is ignored, never multiplied into a NaN.
    masks=[np.ones((32,2),dtype=bool),np.ones((32,2),dtype=bool)]
    masks[1][:,1]=False
    rows=merge_scores(windows,scores,score_masks=masks)
    assert len(rows)==40
    by_time={row["time"]["timestamp_sec"]:row for row in rows}
    assert by_time[0]["scores"]==[1,1]
    assert by_time[8]["scores"]==[2,1] and by_time[8]["counts"]==[2,1]
    assert by_time[19.5]["scores"]==[3,None] and by_time[19.5]["score_mask"]==[True,False]
    wrong=copy.deepcopy(windows[0])
    wrong["split"]="independent_test"
    for sample in wrong["samples"]:
        if sample:sample["split"]="independent_test"
    with pytest.raises(ValueError,match="partitions"):
        merge_scores([windows[0],wrong],[scores[0],scores[0]])
    other_scene=copy.deepcopy(windows[0])
    other_scene["scene_id"]="another-scene"
    for sample in other_scene["samples"]:
        if sample:sample["scene_id"]="another-scene"
    with pytest.raises(ValueError,match="scenes"):
        merge_scores([windows[0],other_scene],[scores[0],scores[0]])
