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

@pytest.mark.parametrize("seed", [17, 99])
def test_resplit_without_final_flag_preserves_holdout_for_every_selector(seed):
    first = assign(dataset(), final_video_ids=["v6"])["manifest"]
    second = assign_splits(first, eligible_video_ids=[r["video_id"] for r in first["videos"]],
                           seed=seed)["manifest"]
    assert {r["video_id"] for r in records_for(second,purpose="final_evaluation")} == {"v6"}
    for purpose in ("training","threshold_calibration"):
        assert "v6" not in {r["video_id"] for r in records_for(second,purpose=purpose)}


def test_final_selection_is_immutable_after_assignment_and_repeated_flags_are_idempotent():
    first = assign(dataset(),final_video_ids=["v6"])["manifest"]
    assert assign(first,final_video_ids=["v6"])["manifest"] == first
    with pytest.raises(ValueError,match="final selection"):
        assign(first,final_video_ids=["v5"])
    # A previously used train/dev video cannot be promoted into a fresh "independent" final.
    no_holdout = assign(dataset())["manifest"]
    with pytest.raises(ValueError,match="final selection"):
        assign(no_holdout,final_video_ids=["v6"])


def test_resplit_preserves_transitive_final_source_duplicate_and_candidate_groups():
    manifest = dataset(7)
    manifest["videos"][1]["provenance"]["source_id"] = manifest["videos"][0]["provenance"]["source_id"]
    manifest["videos"][2]["sha256"] = manifest["videos"][1]["sha256"]
    edges = [{"video_ids":["v2","v3"],"review_status":"candidate"}]
    first = assign(manifest,final_video_ids=["v0"],near_candidates=edges)["manifest"]
    second = assign_splits(first,eligible_video_ids=[r["video_id"] for r in first["videos"]],
                           seed=99,near_candidates=edges)["manifest"]
    assert {r["video_id"] for r in records_for(second,purpose="final_evaluation",near_candidates=edges)} == {"v0","v1","v2","v3"}
    for purpose in ("training","threshold_calibration"):
        assert not {"v0","v1","v2","v3"} & {r["video_id"] for r in records_for(second,purpose=purpose,near_candidates=edges)}
    assert assign(first,final_video_ids=["v2"],near_candidates=edges)["manifest"] == first
    with pytest.raises(ValueError,match="eligible"):
        assign_splits(first,eligible_video_ids=["v0","v1","v2","v4","v5","v6"],seed=99,near_candidates=edges)
    # Newly found near duplicates connecting an old final and old training data must fail closed.
    with pytest.raises(ValueError,match="crosses"):
        assign(first,near_candidates=edges+[{"video_ids":["v3","v4"]}])


def test_near_components_persist_when_resplit_caller_omits_candidate_sidecar():
    manifest = dataset(7)
    edges = [{"video_ids":["v0","v1"],"review_status":"candidate"}]
    first = assign(manifest,near_candidates=edges)["manifest"]
    second = assign_splits(first,eligible_video_ids=[r["video_id"] for r in first["videos"]],seed=99)["manifest"]
    rows = {r["video_id"]:r for r in second["videos"]}
    assert rows["v0"]["group_id"] == rows["v1"]["group_id"]
    assert rows["v0"]["split"] == rows["v1"]["split"]
    validate_splits(second,near_candidates=edges)


@pytest.mark.parametrize("related", [False, True])
def test_real_cli_resplit_retains_final_and_rejects_reselection_without_output(tmp_path, related):
    from fractions import Fraction
    import subprocess
    import sys
    import av
    import numpy as np
    import yaml

    sources=[]
    snapshots={}
    for n in range(4):
        path=tmp_path/f"source-{n}.mkv"
        with av.open(str(path),"w") as container:
            stream=container.add_stream("ffv1",rate=10)
            stream.width,stream.height,stream.pix_fmt=32,24,"yuv420p"
            stream.time_base=Fraction(1,10)
            stream.codec_context.time_base=Fraction(1,10)
            for i, point in enumerate((20,21,24,25)):
                image=np.random.default_rng(100*n+i).integers(0,256,(24,32,3),dtype=np.uint8)
                frame=av.VideoFrame.from_ndarray(image,format="rgb24")
                frame.pts,frame.time_base=point,Fraction(1,10)
                for packet in stream.encode(frame):container.mux(packet)
            for packet in stream.encode():container.mux(packet)
        if related and n==2:
            path.write_bytes((tmp_path/"source-1.mkv").read_bytes())
        snapshots[path]=(path.read_bytes(),path.stat().st_mtime_ns)
        sources.append({"path":path.name,"source_id":f"synthetic-source-{0 if related and n==1 else n}","group_id":f"synthetic-group-{n}",
                        "kind":"synthetic","rights":"confirmed"})
    config=tmp_path/"config.yaml"
    config.write_text(yaml.safe_dump({"dataset_version":"holdout-regression-synthetic-v1",
                                     "source_root":str(tmp_path),"sources":sources}),encoding="utf-8")
    root=Path(__file__).resolve().parents[2]
    def run(module,*args):
        return subprocess.run([sys.executable,"-m",module,*map(str,args)],cwd=root,
                              capture_output=True,text=True,timeout=30)
    imported=tmp_path/"import.json"
    process=run("ml.data.manifest","--config",config,"--output",imported)
    assert process.returncode==0,process.stderr
    bundle=json.loads(imported.read_text())
    final_id=next(r["video_id"] for r in bundle["manifest"]["videos"] if r["path"]=="source-0.mkv")
    other_id=next(r["video_id"] for r in bundle["manifest"]["videos"] if r["path"]=="source-3.mkv")
    first=tmp_path/"first.json"
    process=run("ml.data.splits","--input",imported,"--output",first,"--seed",17,"--final-video-id",final_id)
    assert process.returncode==0,process.stderr
    snapshot=first.read_bytes()
    final_ids={r["video_id"] for r in records_for(json.loads(snapshot)["manifest"],purpose="final_evaluation")}
    assert len(final_ids)==(3 if related else 1)
    for seed in (17,99):
        second=tmp_path/f"second-{seed}.json"
        process=run("ml.data.splits","--input",first,"--output",second,"--seed",seed)
        assert process.returncode==0,process.stderr
        document=json.loads(second.read_text())["manifest"]
        assert {r["video_id"] for r in records_for(document,purpose="final_evaluation")} == final_ids
        for purpose in ("training","threshold_calibration"):
            assert not final_ids & {r["video_id"] for r in records_for(document,purpose=purpose)}
    rejected=tmp_path/"reselection.json"
    process=run("ml.data.splits","--input",first,"--output",rejected,"--seed",99,"--final-video-id",other_id)
    assert process.returncode!=0 and "final selection" in process.stderr
    assert not rejected.exists() and first.read_bytes()==snapshot
    assert all((p.read_bytes(),p.stat().st_mtime_ns)==before for p,before in snapshots.items())
