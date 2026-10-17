import copy
import asyncio
from fractions import Fraction
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import av
import numpy as np
import pytest
import torch

from contracts.python_ports import ModelNotReady, validate_contract
from ml.data.scenes import define_scenes
from ml.inference import InferenceFailed, TimelineAdapter
from ml.intervals import timeline_from_scores
from ml.release import ReleaseManager
from test_release_loader import software_package, export_case, cpu_threads
from test_pts_index import tiny_index


def backend_io_on_windows(validator, monkeypatch):
    """Adapt POSIX directory sync/pipe polling only; media/storage logic stays real.

    Linux runs the unmodified backend, including fsync and its bounded pipe reader.
    Windows cannot fsync directories or select subprocess pipes. This tiny-fixture
    adapter does not verify those deployment properties; it runs real ffprobe.
    """
    if os.name != "nt":
        return
    import backend.app.storage as storage_module
    monkeypatch.setattr(storage_module, "os", SimpleNamespace(
        replace=os.replace, O_RDONLY=os.O_RDONLY, open=lambda *args: -1,
        fsync=lambda descriptor: os.fsync(descriptor) if descriptor != -1 else None,
        close=lambda descriptor: None))

    def run(arguments, *, deadline, max_output):
        result = subprocess.run([validator.ffprobe, "-v", "error", "-max_alloc", "67108864",
                                 "-threads", str(validator.cpu_threads), "-protocol_whitelist", "file",
                                 "-err_detect", "explode", *arguments], stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=max(.001, deadline - time.monotonic()))
        assert result.returncode == 0 and not result.stderr, result.stderr
        assert len(result.stdout) <= max_output
        return json.loads(result.stdout)
    monkeypatch.setattr(validator, "_run", run)


@pytest.mark.parametrize("container_name,rotation,points", [
    ("mp4", 0, tuple(range(10))), ("mov", 90, (20, 21, 24, 25))])
def test_backend_promoted_video_uses_actual_container_through_inference(
        tmp_path, software_package, monkeypatch, container_name, rotation, points):
    from fastapi import UploadFile
    from backend.app.storage import LocalStorage
    from backend.app.video import VideoValidator

    source = tmp_path / ("source." + container_name)
    with av.open(str(source), "w", format=container_name) as container:
        stream = container.add_stream("libx264", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        stream.codec_context.thread_count = 1
        stream.time_base = stream.codec_context.time_base = Fraction(1, 10)
        if rotation:
            stream.set_display_rotation(rotation)
        for i, point in enumerate(points):
            pixels = np.random.default_rng(i).integers(0, 256, (48, 64, 3), dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts, frame.time_base = point, Fraction(1, 10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    before = source.read_bytes(), source.stat().st_mtime_ns
    storage = LocalStorage(tmp_path / "runtime")
    validator = VideoValidator(ffprobe=os.environ.get("FORTRESS_TEST_FFPROBE", "ffprobe"))
    backend_io_on_windows(validator, monkeypatch)
    staged = asyncio.run(storage.spool(UploadFile(io.BytesIO(before[0]), filename="client.mp4"),
                                      deadline_monotonic=time.monotonic() + 30))
    validated = validator.validate(staged.path, size_bytes=staged.size_bytes,
                                   deadline_monotonic=time.monotonic() + 30)
    promoted = storage.promote(staged.path)
    assert promoted.parent == storage.originals and promoted.suffix == ".video"
    assert len(promoted.stem) == 32 and not staged.path.exists()
    validated_again = validator.validate(promoted, size_bytes=staged.size_bytes,
                                         deadline_monotonic=time.monotonic() + 30)
    assert validated_again.video == validated.video
    assert validated_again.sha256 == staged.sha256 == hashlib.sha256(before[0]).hexdigest()
    assert validated.video.rotation == rotation and validated.video.vfr == (container_name == "mov")
    stored_before = promoted.read_bytes(), promoted.stat().st_mtime_ns
    manager = ReleaseManager(allow_test=True)
    manager.load(software_package)
    adapter = TimelineAdapter(manager, allow_test=True)
    original_result = adapter.infer(source, deadline_monotonic=time.monotonic() + 30)
    result = adapter.infer(promoted, deadline_monotonic=time.monotonic() + 30)
    assert result["coverage"] == original_result["coverage"] == "none" and result["findings"] == []
    assert result["observations"] and all(not row["known_mask"] for row in result["observations"])
    assert [(row["interval"]["start_sec"], row["interval"]["end_sec"], row["state"])
            for row in result["observations"]] == [
        (row["interval"]["start_sec"], row["interval"]["end_sec"], row["state"])
        for row in original_result["observations"]]
    validate_contract("events", result)
    if container_name == "mp4":
        output = tmp_path / "cli-timeline.json"
        command = subprocess.run([sys.executable, "-m", "ml.cli", "infer", "--package", str(software_package),
                                  "--video", str(promoted), "--output", str(output), "--allow-test"],
                                 capture_output=True, text=True, timeout=60,
                                 env={**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        assert command.returncode == 0, command.stderr
        assert json.loads(output.read_text(encoding="utf-8")) == result
        readiness = json.loads(command.stdout)["readiness"]
        assert readiness["status"] == "not_ready" and readiness["test_only"] is True
    with pytest.raises(ModelNotReady, match="production"):
        TimelineAdapter(manager).infer(promoted, deadline_monotonic=time.monotonic() + 30)
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert (promoted.read_bytes(), promoted.stat().st_mtime_ns) == stored_before


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
    for name in ("corrupt.mkv", "corrupt.video"):
        corrupt = tmp_path / name
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
