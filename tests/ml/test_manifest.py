from fractions import Fraction
import hashlib
import json

import av
import numpy as np
import pytest

from contracts.python_ports import validate_contract
from ml.data.manifest import ProbeLimits, SourceRejected, build_manifest, local_source, main, probe_video


def make_video(path, points=(20, 21, 24, 25)):
    with av.open(str(path), "w") as container:
        stream = container.add_stream("ffv1", rate=10)
        stream.width, stream.height, stream.pix_fmt = 32, 24, "yuv420p"
        stream.time_base = Fraction(1, 10)
        stream.codec_context.time_base = Fraction(1, 10)
        for i, point in enumerate(points):
            image = np.random.default_rng(i).integers(0, 256, (24,32,3), dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            frame.pts, frame.time_base = point, Fraction(1, 10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def spec(path, **changes):
    return {"path": path, "source_id": path, "group_id": "session-a", "kind": "synthetic",
            "rights": "confirmed", **changes}


def test_real_decode_pts_metadata_hashes_and_originals_unchanged(tmp_path):
    path = make_video(tmp_path/"vfr.mkv")
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    bundle = build_manifest(tmp_path, [spec("vfr.mkv")], dataset_version="tiny-synthetic-v1")
    validate_contract("manifest", bundle["manifest"])
    row = bundle["manifest"]["videos"][0]
    assert row["vfr"] is True and row["source_start_pts"] == 2000
    assert row["time_base"] == {"num":1, "den":1000}
    assert row["duration_sec"] == pytest.approx(.6)
    assert (row["width"], row["height"], row["rotation"]) == (32,24,0)
    assert row["sha256"] == hashlib.sha256(before[0]).hexdigest()
    audit = bundle["audit"]["sources"][0]
    assert audit["availability"] == "available" and audit["decode"]["decoded_frames"] == 4
    assert row["split"] == "excluded" and bundle["audit"]["training_ready"] is False
    assert row["official_label"] is None
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_cfr_uses_observed_pts_not_filename_or_nominal_fps(tmp_path):
    path = make_video(tmp_path/"variable_name.mkv", points=(0,1,2,3))
    metadata, details = probe_video(path)
    assert metadata["vfr"] is False
    assert metadata["duration_sec"] == pytest.approx(.4)
    assert details["last_source_pts"] == 300


def test_container_detection_keeps_playlist_demuxers_disabled(tmp_path):
    make_video(tmp_path / "segment.mkv")
    playlist = tmp_path / "looks-local.video"
    playlist.write_text("ffconcat version 1.0\nfile segment.mkv\n", encoding="utf-8")
    # This is a decodable playlist if unrestricted autodetection is enabled.
    with av.open(str(playlist), options={"protocol_whitelist": "file"}) as container:
        assert len(list(container.decode(video=0))) == 4
    before = playlist.read_bytes(), playlist.stat().st_mtime_ns
    bundle = build_manifest(tmp_path, [spec(playlist.name)], dataset_version="playlist-must-not-decode")
    assert bundle["manifest"] is None
    assert bundle["audit"]["sources"][0]["availability"] == "quarantined"
    assert (playlist.read_bytes(), playlist.stat().st_mtime_ns) == before


@pytest.mark.parametrize("flipped", [False, True])
def test_actual_container_rotation_and_unsupported_reflection(tmp_path, flipped):
    path = tmp_path/"rotated.mp4"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 32, 24, "yuv420p"
        stream.set_display_rotation(90, hflip=flipped)
        for i in range(3):
            frame = av.VideoFrame.from_ndarray(np.zeros((24,32,3),dtype=np.uint8),format="rgb24")
            frame.pts, frame.time_base = i, Fraction(1,10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    if flipped:
        with pytest.raises(SourceRejected, match="transform"):
            probe_video(path)
    else:
        metadata, _ = probe_video(path)
        assert metadata["rotation"] == 90 and (metadata["width"],metadata["height"]) == (32,24)


def test_corrupt_missing_and_over_budget_sources_quarantine_without_valid_rows(tmp_path):
    (tmp_path/"bad.mp4").write_bytes(b"not a video")
    make_video(tmp_path/"long.mkv")
    sources = [spec("bad.mp4"), spec("missing.mp4"), spec("long.mkv")]
    bundle = build_manifest(tmp_path, sources, dataset_version="bad-v1", limits=ProbeLimits(max_frames=1))
    assert bundle["manifest"] is None
    rows = {r["path"]:r for r in bundle["audit"]["sources"]}
    assert rows["bad.mp4"]["availability"] == "quarantined" and rows["bad.mp4"]["sha256"]
    assert rows["missing.mp4"]["quarantine_reason"] == "source_missing"
    assert rows["long.mkv"]["quarantine_reason"] == "decode_budget"
    assert bundle["audit"]["data_state"] == "data_not_ready"
    assert (tmp_path/"bad.mp4").read_bytes() == b"not a video"


def test_unknown_rights_and_source_groups_never_eligible(tmp_path):
    make_video(tmp_path/"tiny.mkv")
    bundle = build_manifest(tmp_path, [spec("tiny.mkv", rights="unknown", group_id=None, source_id=None)],
                            dataset_version="unverified")
    row = bundle["audit"]["sources"][0]
    assert row["availability"] == "available" and row["eligible_for_split"] is False
    assert set(row["identity_missing"]) == {"group_id","source_id"}
    assert bundle["audit"]["training_ready"] is False


@pytest.mark.parametrize("name", ["../outside.mp4", "/absolute", "C:/video.mp4", "a\\b.mp4", "a//b.mp4"])
def test_import_path_cannot_escape_source_root(tmp_path, name):
    with pytest.raises(SourceRejected):
        local_source(tmp_path, name)


def test_byte_pixel_source_count_limits_and_empty_dataset(tmp_path):
    path = make_video(tmp_path/"tiny.mkv")
    for limits in (ProbeLimits(max_source_bytes=10), ProbeLimits(max_frame_pixels=10)):
        result = build_manifest(tmp_path, [spec(path.name)], dataset_version="limits", limits=limits)
        assert result["manifest"] is None
        assert result["audit"]["sources"][0]["availability"] == "quarantined"
    with pytest.raises(ValueError, match="count"):
        build_manifest(tmp_path, [spec("a"), spec("b")], dataset_version="limits", limits=ProbeLimits(max_sources=1))
    empty = build_manifest(tmp_path, [], dataset_version="empty")
    assert empty["manifest"] is None and empty["audit"]["data_state"] == "data_not_ready"


def test_read_only_cli_outputs_new_bundle_and_does_not_overwrite(tmp_path, capsys):
    import yaml
    path = make_video(tmp_path/"tiny.mkv")
    config = tmp_path/"local.yaml"
    config.write_text(yaml.safe_dump({"dataset_version":"tiny-cli","source_root":str(tmp_path),
                                     "sources":[spec(path.name)]}), encoding="utf-8")
    output = tmp_path/"import.json"
    assert main(["--config",str(config),"--output",str(output)]) == 0
    assert json.loads(output.read_text())["manifest"]["videos"]
    before = output.read_bytes()
    with pytest.raises(SystemExit):
        main(["--config",str(config),"--output",str(output)])
    assert output.read_bytes() == before
