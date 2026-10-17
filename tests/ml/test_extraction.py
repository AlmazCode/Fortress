import copy
import json
from pathlib import Path
import shutil

import pytest
from PIL import Image

from ml.data.deduplicate import stable_hash
from ml.data.extract_clips import export_clips, verify_clip
from ml.data.extract_frames import box_to_original, display_transform, export_frames
from ml.data.scenes import define_scenes
from test_pts_index import tiny_index


@pytest.mark.parametrize("rotation",[0,90,180,270])
def test_real_rotation_crop_and_reversible_original_boxes(tmp_path,rotation):
    index,path=tiny_index(tmp_path,rotation=rotation)
    before=(path.read_bytes(),path.stat().st_mtime_ns)
    scenes=define_scenes(index)
    transform=display_transform(index,[2,4,30,22])
    assert box_to_original([0,0,transform["output_width"],transform["output_height"]],transform)==[2,4,30,22]
    report=export_frames(tmp_path,index,scenes,tmp_path/"frames",crop=[2,4,30,22])
    assert report["data"]["frames"]
    for row in report["data"]["frames"]:
        with Image.open(tmp_path/"frames"/row["path"]) as image:
            assert image.size==(transform["output_width"],transform["output_height"])
        assert row["transform"]==transform and row["time"]["rotation"]==rotation
        assert row["source_sha256"]==index["source_sha256"]
    assert (path.read_bytes(),path.stat().st_mtime_ns)==before


def test_frames_are_reproducible_reuse_verified_bytes_and_reject_corruption(tmp_path):
    index,path=tiny_index(tmp_path)
    scenes=define_scenes(index)
    first=export_frames(tmp_path,index,scenes,tmp_path/"frames-a")
    assert export_frames(tmp_path,index,scenes,tmp_path/"frames-a")==first
    second=export_frames(tmp_path,index,scenes,tmp_path/"frames-b")
    assert first==second
    with pytest.raises(ValueError,match="byte limit"):
        export_frames(tmp_path,index,scenes,tmp_path/"frames-b",max_bytes=100)
    artifact=tmp_path/"frames-a"/first["files"][0]["path"]
    artifact.write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        export_frames(tmp_path,index,scenes,tmp_path/"frames-a")
    path.write_bytes(b"changed source")
    with pytest.raises(ValueError,match="hash"):
        export_frames(tmp_path,index,scenes,tmp_path/"frames-b")


def test_clips_reencode_actual_boundaries_without_crossing_scene_and_repeat(tmp_path):
    index,path=tiny_index(tmp_path,rotation=90)
    before=(path.read_bytes(),path.stat().st_mtime_ns)
    scenes=define_scenes(index,cuts_sec=[1.2])
    first=export_clips(tmp_path,index,scenes,tmp_path/"clips-a")
    assert len(first["data"]["clips"])==2
    for row in first["data"]["clips"]:
        assert row["status"]=="encoded_verified"
        assert row["first_decoded_source_sec"]>=row["requested_start_sec"]
        assert row["last_decoded_source_sec"]<row["requested_end_sec"]
        assert row["mapping"][0]["encoded_timestamp_sec"]==0
        assert all(p["source_time"]["rotation"]==90 for p in row["mapping"])
        scene=next(s for s in scenes["scenes"] if s["scene_id"]==row["window"]["scene_id"])
        assert scene["start_sec"]<=row["first_decoded_source_sec"]<=row["last_decoded_source_sec"]<scene["end_sec"]
    assert export_clips(tmp_path,index,scenes,tmp_path/"clips-a")==first
    second=export_clips(tmp_path,index,scenes,tmp_path/"clips-b")
    assert first==second
    clip=tmp_path/"clips-a"/first["files"][0]["path"]
    clip.write_bytes(clip.read_bytes()[:8])
    with pytest.raises(ValueError):
        verify_clip(clip,expected_times=[0],width=24,height=32)
    assert (path.read_bytes(),path.stat().st_mtime_ns)==before


@pytest.mark.parametrize("kind",["frames","clips"])
def test_disk_byte_decode_budgets_leave_no_partial_output(tmp_path,monkeypatch,kind):
    index,_=tiny_index(tmp_path)
    scenes=define_scenes(index)
    export=export_frames if kind=="frames" else export_clips
    with pytest.raises((OSError,ValueError)):
        export(tmp_path,index,scenes,tmp_path/"too-small",max_bytes=100,min_free_bytes=0)
    assert not (tmp_path/"too-small").exists()
    assert not list(tmp_path.glob(".fortress-extract-*"))
    if kind=="clips":
        with pytest.raises(ValueError,match="decode-work"):
            export(tmp_path,index,scenes,tmp_path/"too-much",max_decode_work_frames=1)
    monkeypatch.setattr(shutil,"disk_usage",lambda p:shutil._ntuple_diskusage(100,100,0))
    with pytest.raises(OSError,match="disk"):
        export(tmp_path,index,scenes,tmp_path/"no-space")
    assert not (tmp_path/"no-space").exists()


def test_output_config_change_is_not_silently_reused(tmp_path):
    index,_=tiny_index(tmp_path)
    scenes=define_scenes(index)
    export_frames(tmp_path,index,scenes,tmp_path/"output")
    with pytest.raises(ValueError,match="key"):
        export_frames(tmp_path,index,scenes,tmp_path/"output",rate=4)
    marker=tmp_path/"output/artifacts.json"
    report=json.loads(marker.read_text())
    report["data"]["frames"][0]["split"]="independent_test"
    marker.write_text(json.dumps(report))
    with pytest.raises(ValueError,match="metadata"):
        export_frames(tmp_path,index,scenes,tmp_path/"output")
