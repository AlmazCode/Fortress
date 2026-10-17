import copy
import json
from pathlib import Path

import pytest
from contracts.python_ports import validate_contract
from ml.data.taxonomy import annotation_decision, class_ids, load_taxonomy, validate_taxonomy

ROOT=Path(__file__).resolve().parents[2]

def read(kind):
    return load_taxonomy(ROOT/f"ml/config/{kind}_taxonomy.draft.json")

@pytest.mark.parametrize("kind",["object","action"])
def test_real_candidates_have_unknown_visibility_and_review_boundaries(kind):
    doc=read(kind)
    assert doc["status"]=="draft" and doc["production_ready"] is False
    assert doc["official_class_ids"] is None
    assert all(c["small_object_limit"]["verified_min_pixels"] is None for c in doc["classes"])
    assert len(class_ids(doc))==len(set(class_ids(doc)))
    if kind=="object":
        assert len(class_ids(doc))==9

def test_append_only_new_version_and_semantics():
    old=read("object")
    new=copy.deepcopy(old)
    new["classes"].append({**copy.deepcopy(new["classes"][-1]),"id":"object.extra_candidate"})
    with pytest.raises(ValueError,match="version"):
        validate_taxonomy(new,previous=old)
    new["version"]="objects-draft-v2"
    validate_taxonomy(new,previous=old)
    changed=copy.deepcopy(old)
    changed["classes"].pop(0)
    changed["version"]="v2"
    with pytest.raises(ValueError,match="append-only"):
        validate_taxonomy(changed,previous=old)
    changed=copy.deepcopy(old)
    changed["version"]="v2";changed["classes"][0]["includes"]=["A different meaning"]
    with pytest.raises(ValueError,match="repurposed"):
        validate_taxonomy(changed,previous=old)

@pytest.mark.parametrize("change",["duplicate","official","production","reviewer"])
def test_invalid_taxonomy_cannot_claim_confirmation(change):
    doc=read("action")
    if change=="duplicate":doc["classes"].append(copy.deepcopy(doc["classes"][0]))
    if change=="official":doc["official_class_ids"]=["invented"]
    if change=="production":doc["production_ready"]=True
    if change=="reviewer":doc["status"]="reviewed"
    with pytest.raises(ValueError):validate_taxonomy(doc)

@pytest.mark.parametrize("observed,visibility,reviewed,complete,expected",[
    (True,"visible",True,True,("present",True)),
    (True,"partial",True,False,("present",True)),
    (False,"visible",True,True,("absent_verified",True)),
    (False,"partial",True,True,("unknown",False)),
    (False,"visible",True,False,("unknown",False)),
    (None,"visible",True,True,("unknown",False)),
    (True,"occluded",True,True,("unknown",False)),
    (True,"visible",False,True,("unreviewed",False)),
])
def test_unlabeled_and_invisible_never_become_negative(observed,visibility,reviewed,complete,expected):
    assert annotation_decision(observed,visibility=visibility,reviewed=reviewed,interval_complete=complete)==expected

def test_decision_states_obey_actual_K_contract():
    fixtures=json.loads((ROOT/"contracts/fixtures.json").read_text())
    source=next(c["payload"] for c in fixtures["cases"] if c["schema"]=="events")
    for observed,visible,complete in [(True,"visible",True),(False,"visible",True),(False,"occluded",False),(None,"unknown",False)]:
        timeline=copy.deepcopy(source)
        item=copy.deepcopy(timeline["observations"][0])
        state,mask=annotation_decision(observed,visibility=visible,reviewed=True,interval_complete=complete)
        item.update(state=state,known_mask=mask,visibility=visible,actor_id=None,relations=[])
        timeline["observations"]=[item]
        validate_contract("events",timeline)

def test_case_data_map_covers_every_route():
    text=(ROOT/"docs/model/CASE_DATA_MAP.md").read_text(encoding="utf-8")
    for number in range(1,16):
        assert f"| C{number:02d} |" in text
    assert "R1" in text and "unknown" in text
