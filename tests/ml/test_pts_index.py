import copy
from fractions import Fraction

import av
import numpy as np
import pytest

from contracts.python_ports import validate_contract
from ml.data.deduplicate import stable_hash
from ml.data.manifest import ProbeLimits, SourceRejected, build_manifest, probe_video
from ml.data.pts_index import build_index, iter_indexed_frames, time_mapping, validate_index
from ml.data.scenes import define_scenes, sample_scenes, temporal_windows, validate_scenes
from ml.data.splits import assign_splits


def tiny_index(root, *, points=(4,5,7,8), rotation=0, name="tiny"):
    path=root/(name+(".mp4" if rotation else ".mkv"))
    with av.open(str(path),"w") as container:
        stream=container.add_stream("mpeg4" if rotation else "ffv1",rate=2)
        stream.width,stream.height,stream.pix_fmt=32,24,"yuv420p"
        stream.time_base=Fraction(1,2)
        stream.codec_context.time_base=Fraction(1,2)
        if rotation:stream.set_display_rotation(rotation)
        for i,point in enumerate(points):
            data=np.random.default_rng(i).integers(0,256,(24,32,3),dtype=np.uint8)
            frame=av.VideoFrame.from_ndarray(data,format="rgb24")
            frame.pts,frame.time_base=point,Fraction(1,2)
            for packet in stream.encode(frame):container.mux(packet)
        for packet in stream.encode():container.mux(packet)
    bundle=build_manifest(root,[{"path":path.name,"source_id":name,"group_id":name,"kind":"synthetic","rights":"confirmed"}],
                          dataset_version="D4-tiny-synthetic-v1")
    manifest=bundle["manifest"]
    record=manifest["videos"][0]
    manifest=assign_splits(manifest,eligible_video_ids=[record["video_id"]],seed=17)["manifest"]
    return build_index(root,manifest["videos"][0],dataset_version=manifest["dataset_version"],
                       split_version=manifest["split_version"]),path


def test_stored_video_name_keeps_index_hash_and_decode_limits(tmp_path):
    index, path = tiny_index(tmp_path, rotation=90)
    stored = path.with_suffix(".video")
    path.rename(stored)
    index["path"] = stored.name
    index["index_sha256"] = stable_hash({k: v for k, v in index.items() if k != "index_sha256"})
    decoded = list(iter_indexed_frames(tmp_path, index))
    assert [row["source_pts"] for row, _ in decoded] == [row["source_pts"] for row in index["frames"]]
    assert [int(frame.rotation) % 360 for _, frame in decoded] == [90] * len(decoded)
    for decode in (lambda: probe_video(stored, limits=ProbeLimits(max_frames=1)),
                   lambda: list(iter_indexed_frames(tmp_path, index, limits=ProbeLimits(max_frames=1)))):
        with pytest.raises(SourceRejected, match="budget"):
            decode()
    stored.write_bytes(stored.read_bytes() + b"changed")
    with pytest.raises(SourceRejected, match="hash"):
        list(iter_indexed_frames(tmp_path, index))


def test_vfr_nonzero_pts_roundtrip_and_actual_K_time_mapping(tmp_path):
    index,path=tiny_index(tmp_path)
    before=(path.read_bytes(),path.stat().st_mtime_ns)
    assert index["vfr"] is True and index["origin_pts"]==2000
    assert [r["timestamp_sec"] for r in index["frames"]]==[0,.5,1.5,2]
    scene=define_scenes(index)["scenes"][0]
    row=index["frames"][2]
    mapping=time_mapping(index,row["source_pts"])
    assert mapping["source_pts"]==3500 and mapping["timestamp_sec"]==1.5
    validate_contract("objects",{"schema_version":"1.0","dataset_version":index["dataset_version"],
        "taxonomy_version":"draft","frames":[{"frame_id":"tiny-frame","video_id":index["video_id"],
        "scene_id":scene["scene_id"],"width":32,"height":24,"sha256":index["source_sha256"],
        "time":mapping,"objects":[],"provenance":index["provenance"]}]})
    assert len(list(iter_indexed_frames(tmp_path,index)))==4
    assert (path.read_bytes(),path.stat().st_mtime_ns)==before


def test_scene_cuts_snap_to_decoded_pts_and_samples_do_not_cross_boundary(tmp_path):
    index,_=tiny_index(tmp_path)
    scenes=define_scenes(index,cuts_sec=[1.2])
    assert scenes["cuts"][0]["decoded_sec"]==1.5
    assert [(s["start_sec"],s["end_sec"]) for s in scenes["scenes"]]==[(0,1.5),(1.5,2.5)]
    for window in temporal_windows(index,scenes):
        scene=next(s for s in scenes["scenes"] if s["scene_id"]==window["scene_id"])
        assert scene["start_sec"]<=window["start_sec"]<window["end_sec"]<=scene["end_sec"]
        assert all(s is None or s["scene_id"]==scene["scene_id"] for s in window["samples"])
    rows=sample_scenes(index,scenes)
    unavailable=next(r for r in rows if r["target_sec"]==1)
    assert unavailable["image_mask"] is False and unavailable["known_mask"] is False
    assert unavailable["time"] is None


def test_window_coverage_span_stride_and_tail_masks_are_distinct(tmp_path):
    index,_=tiny_index(tmp_path,points=tuple(range(4,44)))
    windows=temporal_windows(index,define_scenes(index))
    assert [w["start_sec"] for w in windows]==[0,8]
    assert all(w["grid_coverage_sec"]==16 and w["grid_first_last_span_sec"]==15.5 for w in windows)
    assert windows[0]["actual_first_last_span_sec"]==15.5
    assert sum(windows[0]["padding_mask"])==0 and windows[0]["grid_interval_complete"] is True
    assert sum(windows[1]["padding_mask"])==8 and windows[1]["grid_interval_complete"] is False
    assert all(not any(w["known_mask"]) for w in windows)


def test_hash_partition_review_and_sampling_limits_fail_closed(tmp_path):
    index,path=tiny_index(tmp_path)
    with pytest.raises(ValueError,match="budget"):
        sample_scenes(index,define_scenes(index),rate=120,max_samples=1)
    changed=copy.deepcopy(define_scenes(index))
    changed["scenes"][0]["split"]="independent_test"
    changed["scenes_sha256"]=stable_hash({k:v for k,v in changed.items() if k!="scenes_sha256"})
    with pytest.raises(ValueError,match="partition"):
        validate_scenes(index,changed)
    with pytest.raises(ValueError,match="reviewer"):
        define_scenes(index,reviewer=" ")
    bad=copy.deepcopy(index)
    bad["frames"][0]["source_pts"]=None
    bad["index_sha256"]=stable_hash({k:v for k,v in bad.items() if k!="index_sha256"})
    with pytest.raises(ValueError):
        validate_index(bad)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError,match="hash"):
        list(iter_indexed_frames(tmp_path,index))


def test_decode_limit_and_missing_pts_are_not_fabricated(tmp_path,monkeypatch):
    index,path=tiny_index(tmp_path)
    with pytest.raises(SourceRejected,match="budget"):
        list(iter_indexed_frames(tmp_path,index,limits=ProbeLimits(max_frames=1)))
    original=av.open
    class LostClock:
        def __init__(self,container):self.container=container
        def __enter__(self):return self
        def __exit__(self,*args):self.container.close()
        @property
        def streams(self):return self.container.streams
        def decode(self,stream):
            for frame in self.container.decode(stream):
                frame.pts=None
                yield frame
    monkeypatch.setattr(av,"open",lambda *args,**kwargs:LostClock(original(*args,**kwargs)))
    with pytest.raises(SourceRejected,match="pts"):
        list(iter_indexed_frames(tmp_path,index))
