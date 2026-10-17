import copy
import hashlib
import json
from pathlib import Path

import pytest

from ml.data.splits import assign_splits, records_for, validate_splits


def dataset(count=7):
    fixtures = json.loads((Path(__file__).resolve().parents[2]/"contracts/fixtures.json").read_text())
    base = next(c["payload"] for c in fixtures["cases"] if c["schema"]=="manifest")
    template = base["videos"][0]
    rows = []
    for i in range(count):
        row = copy.deepcopy(template)
        sha = hashlib.sha256(f"synthetic-{i}".encode()).hexdigest()
        row.update(video_id=f"v{i}",canonical_id=f"canonical-{i}",group_id=f"session-{i}",
                   scene_id=f"scene-{i}",path=f"synthetic/{i}.mp4",sha256=sha,split="excluded",
                   provenance={"kind":"synthetic","source_id":f"source-{i}","sha256":sha})
        rows.append(row)
    return {**copy.deepcopy(base),"videos":rows}


def assign(manifest, **kwargs):
    return assign_splits(manifest,eligible_video_ids=[r["video_id"] for r in manifest["videos"]],
                         seed=17,**kwargs)


def test_split_reproducible_on_input_order_and_original_manifest_unchanged():
    manifest = dataset()
    before = copy.deepcopy(manifest)
    result = assign(manifest,final_video_ids=["v6"])
    shuffled = copy.deepcopy(manifest)
    shuffled["videos"].reverse()
    assert result == assign(shuffled,final_video_ids=["v6"])
    assert manifest == before
    assert result["audit"]["counts"] == {"train":5,"dev_validation":1,"independent_test":1,"excluded":0}
    assert result["audit"]["training_ready"] is False
    assert result["audit"]["final_independence"] == "unverified"


def test_transitive_source_scene_exact_and_near_groups_stay_together():
    manifest = dataset(7)
    rows = manifest["videos"]
    rows[1]["provenance"]["source_id"] = rows[0]["provenance"]["source_id"]
    rows[2]["scene_id"] = rows[1]["scene_id"]
    rows[3]["sha256"] = rows[2]["sha256"]
    edges = [{"video_ids":["v3","v4"],"review_status":"candidate"}]
    result = assign(manifest,final_video_ids=["v0"],near_candidates=edges)
    assert all(r["split"]=="independent_test" for r in result["manifest"]["videos"][:5])
    assert result["audit"]["components"][0] == ["v0","v1","v2","v3","v4"]
    validate_splits(result["manifest"],near_candidates=edges)


def test_ineligible_member_excludes_whole_source_group_and_leak_is_rejected():
    manifest = dataset(3)
    manifest["videos"][1]["group_id"] = manifest["videos"][0]["group_id"]
    result = assign_splits(manifest,eligible_video_ids=["v0","v2"],seed=1)
    assert [r["split"] for r in result["manifest"]["videos"][:2]] == ["excluded","excluded"]
    with pytest.raises(ValueError,match="ineligible"):
        assign_splits(manifest,eligible_video_ids=["v0","v2"],final_video_ids=["v0"],seed=1)
    leaked = copy.deepcopy(result["manifest"])
    leaked["videos"][0]["split"] = "train"
    with pytest.raises(ValueError):
        validate_splits(leaked)


def test_exact_hash_prevents_leak_even_if_canonical_and_group_ids_lie():
    manifest = dataset(3)
    manifest["videos"][1]["sha256"] = manifest["videos"][0]["sha256"]
    manifest["videos"][0]["split"] = "train"
    manifest["videos"][1]["split"] = "dev_validation"
    with pytest.raises(ValueError,match="crosses"):
        validate_splits(manifest)


def test_final_never_enters_training_or_threshold_calibration():
    result = assign(dataset(),final_video_ids=["v5","v6"])["manifest"]
    assert {r["video_id"] for r in records_for(result,purpose="final_evaluation")} == {"v5","v6"}
    for purpose in ("training","threshold_calibration"):
        assert not {"v5","v6"} & {r["video_id"] for r in records_for(result,purpose=purpose)}
    with pytest.raises(ValueError,match="explicit"):
        records_for(result,purpose="independent_test")


def test_empty_eligibility_small_groups_and_unknown_near_edges_fail_honestly():
    manifest = dataset(1)
    result = assign_splits(manifest,eligible_video_ids=[],seed=1)
    assert result["audit"]["data_state"] == "data_not_ready"
    assert result["audit"]["counts"]["excluded"] == 1
    assert assign(manifest)["audit"]["counts"]["dev_validation"] == 0
    with pytest.raises(ValueError,match="unknown"):
        assign(manifest,near_candidates=[{"video_ids":["v0","missing"]}])
