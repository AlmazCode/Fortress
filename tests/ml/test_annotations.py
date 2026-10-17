import copy
import json
from pathlib import Path

import pytest

from contracts.python_ports import validate_contract
from ml.data.annotation_tasks import prepare_tasks, scene_context
from ml.data.annotations import actions_contract, read_actions, validate_actions, write_actions
from ml.data.extract_frames import export_frames
from ml.data.scenes import define_scenes
from ml.data.taxonomy import load_taxonomy
from test_pts_index import tiny_index

ROOT=Path(__file__).resolve().parents[2]


def sample_documents(tmp_path,rotation=0):
    index,_=tiny_index(tmp_path,rotation=rotation)
    row={k:index[k] for k in ("video_id","canonical_id","group_id","path","split","duration_sec","width","height","time_base","rotation","vfr","provenance")}
    row.update(scene_id=index["video_id"]+":unsegmented",sha256=index["source_sha256"],
               source_start_pts=index["origin_pts"],official_label=None)
    manifest={"schema_version":"1.0","dataset_version":index["dataset_version"],"split_version":index["split_version"],"videos":[row]}
    scenes=define_scenes(index)
    pairs=[{"index":index,"scenes":scenes}]
    contexts=scene_context(manifest,pairs)
    object_taxonomy=load_taxonomy(ROOT/"ml/config/object_taxonomy.draft.json")
    action_taxonomy=load_taxonomy(ROOT/"ml/config/action_taxonomy.draft.json")
    frames=tmp_path/"frames"
    export_frames(tmp_path,index,scenes,frames,crop=[2,4,30,22])
    assets=tmp_path/"tasks"
    report=prepare_tasks(assets,manifest=manifest,pairs=pairs,frame_directories=[frames],
        object_taxonomy=object_taxonomy,action_taxonomy=action_taxonomy,annotation_version="synthetic-labels-v1")
    contexts=json.loads((assets/"tasks.json").read_text())["scene_context"]
    return {"manifest":manifest,"index":index,"scenes":scenes,"contexts":contexts,"pairs":pairs,
            "object_taxonomy":object_taxonomy,"action_taxonomy":action_taxonomy,"asset_root":assets,
            "source_root":tmp_path,"task_report":report,
            "objects":json.loads((assets/"objects.json").read_text()),"actions":json.loads((assets/"actions.json").read_text())}


def add_action(data,**changes):
    scene=next(iter(data["contexts"].values()))
    row={"annotation_id":f"a{len(data['actions']['records'])+1}","video_id":scene["video_id"],"scene_id":scene["scene_id"],
         "source_sha256":scene["source_sha256"],"split":scene["split"],"start_sec":0,"end_sec":.5,
         "event_type":data["action_taxonomy"]["classes"][0]["id"],"taxonomy_version":data["action_taxonomy"]["version"],
         "state":"present","known_mask":True,"visibility":"visible","interval_complete":True,
         "actor_id":None,"relations":[],"annotator":"synthetic-fixture-author","reviewer":"synthetic-fixture-reviewer",
         "review_status":"reviewed","human_approved":True,"label_origin":"manual",**changes}
    data["actions"]["records"].append(row)
    return row


def add_object(data,**changes):
    frame=data["objects"]["frames"][0]
    item={"object_id":"o1","class_id":data["object_taxonomy"]["classes"][0]["id"],"bbox_xyxy":[4,6,12,14],
          "visibility":"partial","occluded":True,"truncated":True,"track_id":None,"actor_id":None,
          "annotator":"synthetic-fixture-author","reviewer":"synthetic-fixture-reviewer","review_status":"reviewed",
          "human_approved":True,"label_origin":"manual","proposal_id":None,**changes}
    frame["objects"].append(item)
    return item


def validate(data):
    validate_actions(data["actions"],manifest=data["manifest"],taxonomy=data["action_taxonomy"],scenes=data["contexts"])


@pytest.mark.parametrize("format",["jsonl","csv"])
def test_interval_exchange_preserves_unknown_identity_and_review_metadata(tmp_path,format):
    data=sample_documents(tmp_path)
    add_action(data)
    add_action(data,start_sec=.5,end_sec=1,state="unknown",known_mask=False,visibility="occluded")
    validate(data)
    output=tmp_path/("labels."+format)
    write_actions(data["actions"],output,format=format)
    restored=read_actions(output,format=format)
    assert restored==data["actions"]
    validate_contract("annotations",actions_contract(restored))
    with pytest.raises(FileExistsError):write_actions(restored,output,format=format)
    with pytest.raises(ValueError,match="limit|oversize"):read_actions(output,format=format,max_bytes=1)


def test_explicit_negatives_unlabeled_and_pseudo_are_distinct(tmp_path):
    data=sample_documents(tmp_path)
    assert data["actions"]["records"]==[]
    add_action(data,state="absent_verified")
    add_action(data,state="unknown",known_mask=False,start_sec=.5,end_sec=1)
    add_action(data,state="unreviewed",known_mask=False,start_sec=1,end_sec=1.5,label_origin="pseudo",
               review_status="unreviewed",reviewer=None,human_approved=False,proposed_state="present")
    validate(data)
    assert [r["valid"] for r in actions_contract(data["actions"])["records"]]==[True,False,False]


@pytest.mark.parametrize("case",["interval","class","incomplete_negative","pseudo_gold","contradiction","partition","hash","actor","relation","occluded_positive"])
def test_invalid_labels_cannot_open_training_mask(tmp_path,case):
    data=sample_documents(tmp_path)
    row=add_action(data)
    if case=="interval":row["end_sec"]=999
    if case=="class":row["event_type"]="invented.official_id"
    if case=="incomplete_negative":row.update(state="absent_verified",interval_complete=False)
    if case=="pseudo_gold":row["label_origin"]="pseudo"
    if case=="contradiction":add_action(data,state="absent_verified")
    if case=="partition":row["split"]="independent_test"
    if case=="hash":row["source_sha256"]="0"*64
    if case=="actor":row["actor_id"]="guessed-from-score"
    if case=="relation":row["relations"]=[{"kind":"party","subject_id":"x","object_id":"y","known":True}]
    if case=="occluded_positive":row["visibility"]="occluded"
    with pytest.raises(ValueError):validate(data)


def test_independent_actions_can_overlap_and_needs_review_stays_unknown(tmp_path):
    data=sample_documents(tmp_path)
    add_action(data)
    add_action(data,event_type=data["action_taxonomy"]["classes"][1]["id"])
    add_action(data,state="unknown",known_mask=False,review_status="needs_review",reviewer=None,human_approved=False)
    validate(data)
    assert actions_contract(data["actions"])["records"][-1]["valid"] is False
