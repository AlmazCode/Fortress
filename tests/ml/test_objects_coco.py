import copy

import pytest

from contracts.python_ports import validate_contract
from ml.data.coco_io import export_coco, import_coco
from ml.data.objects import object_known, objects_contract, validate_objects
from test_annotations import sample_documents, add_object


@pytest.mark.parametrize("rotation",[0,90,180,270])
def test_coco_roundtrip_preserves_original_box_pts_crop_unknown_and_nullable_links(tmp_path,rotation):
    data=sample_documents(tmp_path,rotation=rotation)
    add_object(data)
    document=data["objects"]
    validate_objects(document,taxonomy=data["object_taxonomy"],manifest=data["manifest"],scenes=data["contexts"])
    coco,sidecar=export_coco(document,data["object_taxonomy"])
    restored=import_coco(coco,sidecar,data["object_taxonomy"])
    assert restored==document
    assert restored["frames"][0]["objects"][0]["bbox_xyxy"]==[4,6,12,14]
    assert restored["frames"][0]["objects"][0]["track_id"] is None
    assert coco["annotations"][0]["area"]==64
    validate_contract("objects",objects_contract(restored))


@pytest.mark.parametrize("case",["duplicate","category","image_bool","bounds","area","sidecar","geometry"])
def test_coco_rejects_wrong_ids_bounds_area_and_missing_metadata(tmp_path,case):
    data=sample_documents(tmp_path)
    add_object(data)
    coco,sidecar=export_coco(data["objects"],data["object_taxonomy"])
    if case=="duplicate":coco["annotations"].append(copy.deepcopy(coco["annotations"][0]))
    if case=="category":coco["annotations"][0]["category_id"]=999
    if case=="image_bool":coco["annotations"][0]["image_id"]=True
    if case=="bounds":coco["annotations"][0]["bbox"][0]=999
    if case=="area":coco["annotations"][0]["area"]=-1
    if case=="sidecar":sidecar["canonical"]["annotation_version"]="tampered"
    if case=="geometry":coco["images"][0]["width"]+=1
    with pytest.raises(ValueError):
        import_coco(coco,sidecar,data["object_taxonomy"],annotation_version="synthetic-labels-v2")


def test_edited_and_deleted_coco_labels_need_new_version_and_new_human_review(tmp_path):
    data=sample_documents(tmp_path)
    add_object(data)
    before=copy.deepcopy(data["objects"])
    coco,sidecar=export_coco(before,data["object_taxonomy"])
    coco["annotations"][0]["bbox"][0]+=1
    with pytest.raises(ValueError,match="new annotation version"):
        import_coco(coco,sidecar,data["object_taxonomy"])
    changed=import_coco(coco,sidecar,data["object_taxonomy"],annotation_version="synthetic-labels-v2")
    item=changed["frames"][0]["objects"][0]
    assert object_known(item) is False and item["human_approved"] is False
    assert changed["frames"][0]["frame_review"]["complete"] is False
    coco["annotations"]=[]
    removed=import_coco(coco,sidecar,data["object_taxonomy"],annotation_version="synthetic-labels-v3")
    assert not any(f["objects"] for f in removed["frames"])
    assert removed["history"] and data["objects"]==before


def test_new_external_coco_annotation_is_an_unreviewed_proposal_with_sidecar_metadata(tmp_path):
    data=sample_documents(tmp_path)
    coco,sidecar=export_coco(data["objects"],data["object_taxonomy"])
    coco["annotations"]=[{"id":42,"image_id":1,"category_id":1,"bbox":[2,2,8,8],"area":64,
                           "iscrowd":0,"annotation_note":"external proposal"}]
    imported=import_coco(coco,sidecar,data["object_taxonomy"],annotation_version="synthetic-labels-v2")
    item=imported["frames"][0]["objects"][0]
    assert not object_known(item) and item["review_status"]=="unreviewed" and item["reviewer"] is None
    assert item["coco_extra"]["annotation_note"]=="external proposal"
    again,metadata=export_coco(imported,data["object_taxonomy"])
    assert import_coco(again,metadata,data["object_taxonomy"])==imported


@pytest.mark.parametrize("case",["negative","outside","zero_area","nan","class","pseudo","transform","path","provenance","pts"])
def test_canonical_object_validation_keeps_source_geometry_and_review_honest(tmp_path,case):
    data=sample_documents(tmp_path)
    item=add_object(data)
    if case=="negative":item["bbox_xyxy"][0]=-1
    if case=="outside":item["bbox_xyxy"][2]=40
    if case=="zero_area":item["bbox_xyxy"][2]=item["bbox_xyxy"][0]
    if case=="nan":item["bbox_xyxy"][0]=float("nan")
    if case=="class":item["class_id"]="not-in-taxonomy"
    if case=="pseudo":item["label_origin"]="pseudo"
    if case=="transform":data["objects"]["frames"][0]["artifact"]["transform"]["to_original"][0][2]+=1
    if case=="path":data["objects"]["frames"][0]["artifact"]["path"]="../escape.png"
    if case=="provenance":data["objects"]["frames"][0]["source_sha256"]="0"*64
    if case=="pts":
        data["objects"]["frames"][0]["source_time"]["source_pts"]+=500
        data["objects"]["frames"][0]["source_time"]["timestamp_sec"]+=.5
    with pytest.raises(ValueError):
        validate_objects(data["objects"],taxonomy=data["object_taxonomy"],manifest=data["manifest"],scenes=data["contexts"])
