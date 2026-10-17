import copy
import time

import pytest
import torch

from contracts.python_ports import ModelNotReady, validate_contract
from ml.data.scenes import define_scenes
from ml.inference import InferenceFailed, TimelineAdapter
from ml.intervals import timeline_from_scores
from ml.release import ReleaseManager
from test_release_loader import software_package, export_case, cpu_threads
from test_pts_index import tiny_index


def test_unknown_observability_is_not_invented_and_absence_requires_complete_interval():
    scenes = {"scenes": [{"scene_id": "s1", "start_sec": 0., "end_sec": 1.},
                          {"scene_id": "s2", "start_sec": 1., "end_sec": 2.}]}
    points = [{"video_id": "v", "scene_id": scene, "time": {"timestamp_sec": timestamp, "valid": True},
               "scores": [score]} for scene, timestamp, score in (("s1", 0., .9), ("s1", .5, .1), ("s2", 1.5, .9))]
    options = {"video_id": "v", "class_ids": ["a"], "thresholds": {"a": .5}, "model_version": "test",
               "preprocessing_version": "letterbox-imagenet-v1"}
    unknown = timeline_from_scores(points, scenes, **options)
    assert unknown["coverage"] == "none" and all(not r["known_mask"] and r["actor_id"] is None for r in unknown["observations"])
    def visible(point, key):
        return {"visibility": "visible", "interval_complete": False}
    partial = timeline_from_scores(points, scenes, visibility_provider=visible, **options)
    assert partial["coverage"] == "partial" and any(r["state"] == "present" for r in partial["observations"])
    assert not any(r["state"] == "absent_verified" for r in partial["observations"])
    complete = timeline_from_scores(points, scenes, visibility_provider=lambda *a: {"visibility": "visible", "interval_complete": True}, **options)
    assert any(r["state"] == "absent_verified" for r in complete["observations"])
    assert all(r["interval"]["end_sec"] <= (1. if r["interval"]["scene_id"] == "s1" else 2.) for r in complete["observations"])
    assert any(r["interval"]["start_sec"] == 1. and r["state"] == "unknown" for r in complete["observations"])
    assert all(not relation["known"] for r in complete["observations"] for relation in r["relations"])
    validate_contract("events", complete)


def test_actual_raw_pts_inference_scene_windows_masks_and_job_isolation(tmp_path, software_package):
    manager = ReleaseManager(allow_test=True)
    manager.load(software_package)
    index, path = tiny_index(tmp_path, rotation=90)
    scenes = define_scenes(index, cuts_sec=[1.2])
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    adapter = TimelineAdapter(manager, allow_test=True)
    first = adapter.infer_indexed(tmp_path, index, scenes, deadline_monotonic=time.monotonic() + 30)
    second = adapter.infer_indexed(tmp_path, index, scenes, deadline_monotonic=time.monotonic() + 30)
    assert first == second and first["coverage"] == "none" and first["findings"] == []
    assert {r["interval"]["scene_id"] for r in first["observations"]} == {r["scene_id"] for r in scenes["scenes"]}
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    validate_contract("events", first)
    with pytest.raises(ModelNotReady, match="production"):
        TimelineAdapter(manager).infer(path, deadline_monotonic=time.monotonic() + 30)
    # The raw-path port decodes a local source without adding it to any training split.
    result = adapter.infer(path, deadline_monotonic=time.monotonic() + 30)
    assert result["coverage"] == "none"


def test_deadline_corrupt_decode_source_change_and_inference_failure_are_failed(tmp_path, software_package, monkeypatch):
    manager = ReleaseManager(allow_test=True)
    manager.load(software_package)
    adapter = TimelineAdapter(manager, allow_test=True)
    index, path = tiny_index(tmp_path)
    scenes = define_scenes(index)
    for deadline in (time.monotonic() - 1, float("nan")):
        with pytest.raises(InferenceFailed, match="deadline"):
            adapter.infer(path, deadline_monotonic=deadline)
    corrupt = tmp_path / "corrupt.mkv"
    corrupt.write_bytes(b"not a video")
    with pytest.raises(InferenceFailed):
        adapter.infer(corrupt, deadline_monotonic=time.monotonic() + 30)
    original = manager.snapshot().model.encoder.forward
    def oom(*args, **kwargs):
        raise RuntimeError("injected tiny inference OOM")
    monkeypatch.setattr(manager.snapshot().model.encoder, "forward", oom)
    with pytest.raises(InferenceFailed, match="RuntimeError"):
        adapter.infer_indexed(tmp_path, index, scenes, deadline_monotonic=time.monotonic() + 30)
    monkeypatch.setattr(manager.snapshot().model.encoder, "forward", original)
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(InferenceFailed):
        adapter.infer_indexed(tmp_path, index, scenes, deadline_monotonic=time.monotonic() + 30)
