import copy

from ml.data.quality import quality_report
from test_annotations import sample_documents, add_action, add_object


def report(data,**changes):
    return quality_report(manifest=data["manifest"],objects=data["objects"],actions=data["actions"],
        object_taxonomy=data["object_taxonomy"],action_taxonomy=data["action_taxonomy"],scenes=data["contexts"],
        asset_root=data["asset_root"],source_root=data["source_root"],**changes)


def test_empty_task_bundle_is_portable_verified_and_not_gold(tmp_path):
    data=sample_documents(tmp_path)
    qa=report(data)
    assert data["task_report"]["data"]["annotation_ui"]=="not_verified"
    assert data["task_report"]["data"]["task_count"]==len(data["objects"]["frames"])+1
    assert qa["valid"] is True and qa["annotation_records"]==0 and qa["unknown_rate"] is None
    assert qa["data_ready"] is False and qa["training_ready"] is False
    assert qa["assets_verified"] is True and qa["sources_verified"] is True
    assert all(row["records"]==0 for row in qa["per_class"].values())


def test_objects_only_coverage_small_occluded_and_unknown_norms_do_not_become_gru_ready(tmp_path):
    data=sample_documents(tmp_path)
    item=add_object(data)
    qa=report(data)
    assert qa["per_class"][item["class_id"]]["small_box"]==1
    assert qa["per_class"][item["class_id"]]["occluded"]==1
    assert qa["per_class"][item["class_id"]]["truncated"]==1
    assert qa["per_case"]["C01"]["annotation_records"]==1
    assert qa["per_case"]["C01"]["normative_status"]=="unknown"
    assert qa["temporal_annotations_ready"] is False and qa["training_ready"] is False
    assert qa["real_data"] is False


def test_disagreement_and_duplicate_proposals_remain_needs_review(tmp_path):
    data=sample_documents(tmp_path)
    item=add_object(data,review_status="needs_review",reviewer=None,human_approved=False)
    duplicate=copy.deepcopy(item)
    duplicate["object_id"]="o2"
    data["objects"]["frames"][0]["objects"].append(duplicate)
    qa=report(data)
    assert qa["valid"] is True and qa["duplicate_annotation_count"]==1
    assert qa["disagreement_count"]==2 and qa["unknown_rate"]==1
    assert qa["object_annotations_ready"] is False


def test_label_change_creates_a_new_dataset_revision_and_bad_pixels_or_split_block_qa(tmp_path):
    data=sample_documents(tmp_path)
    before=report(data)["dataset_revision"]
    add_action(data)
    after=report(data)["dataset_revision"]
    assert before!=after
    frame=data["objects"]["frames"][0]
    (data["asset_root"]/frame["artifact"]["path"]).write_bytes(b"corrupt")
    assert report(data)["valid"] is False
    leaked=copy.deepcopy(data["manifest"]["videos"][0])
    leaked.update(video_id="copy-in-final",canonical_id="different",group_id="different",split="independent_test")
    data["manifest"]["videos"].append(leaked)
    qa=report(data)
    assert qa["valid"] is False and qa["data_ready"] is False
