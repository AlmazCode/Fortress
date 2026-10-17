import copy
from dataclasses import replace
import json

import pytest
import torch

from ml.cache import build_cache
from ml.data.deduplicate import stable_hash
from ml.data.pts_index import build_index, iter_indexed_frames
from ml.data.scenes import define_scenes
from ml.evaluate import binary_metrics, evaluate, event_metrics, score_cache, validate_packet
from ml.models import FrozenEncoder
from ml.models.encoder import file_sha256
from ml.thresholds import calibrate
from ml.train import train
from ml.windows import labelled_windows
from test_cache_resume import cache_case
from test_pts_index import tiny_index


@pytest.fixture(scope="module", autouse=True)
def cpu_threads():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def packet_for(manifest, classes, checkpoint_sha, taxonomy_sha, split="dev_validation"):
    video = next(v for v in manifest["videos"] if v["split"] == split)
    rows = [([True, False], [.8, .2]), ([False, True], [.2, .8]),
            ([None, False], [None, .3]), ([True, None], [.7, None])]
    return {"version": "ml-evaluation-input-v1", "manifest": copy.deepcopy(manifest),
            "manifest_sha256": stable_hash(manifest), "dataset_sha256": stable_hash(manifest),
            "taxonomy_sha256": taxonomy_sha, "checkpoint_sha256": checkpoint_sha,
            "class_ids": list(classes), "split": split, "test_only": True,
            "samples": [{"id": f"sample-{n}", "video_id": video["video_id"], "scene_id": video["scene_id"],
                         "time_sec": n * .5, "targets": targets, "scores": scores}
                        for n, (targets, scores) in enumerate(rows)],
            "verdicts": [], "truth_events": [], "predicted_events": [],
            "event_protocol": {"version": "event-boundary-v1", "tolerance_sec": .5}}


@pytest.fixture(scope="module")
def export_case(tmp_path_factory):
    root = tmp_path_factory.mktemp("M3-synthetic")
    data, windows, _, _, spec, frames = cache_case(root)
    manifest = copy.deepcopy(data["manifest"])
    indexes = {}
    for partition in ("dev_validation", "independent_test"):
        index, _ = tiny_index(root, name=partition, points=(4, 6, 9, 11) if partition == "dev_validation" else (5, 7, 10, 14))
        index["split"] = partition
        row = {k: index[k] for k in ("video_id", "canonical_id", "group_id", "path", "split", "duration_sec",
                                     "width", "height", "time_base", "rotation", "vfr", "provenance")}
        row.update(scene_id=index["video_id"] + ":unsegmented", sha256=index["source_sha256"],
                   source_start_pts=index["origin_pts"], official_label=None)
        manifest["videos"].append(row)
        indexes[partition] = build_index(root, row, dataset_version=manifest["dataset_version"],
                                         split_version=manifest["split_version"])
    encoder = FrozenEncoder(test_only=True)
    metadata = encoder.descriptor()
    spec = replace(spec, dataset_sha256=stable_hash(manifest), encoder_sha256=stable_hash(metadata))
    build_cache(root / "cache", source_root=data["source_root"], spec=spec, windows=windows,
                frames=frames(), encoder=encoder, encoder_metadata=metadata)
    train(root / "cache", root / "training", spec=spec, encoder=encoder, steps=1)
    checkpoint = root / "training/checkpoint.pt"
    dev = packet_for(manifest, spec.class_ids, file_sha256(checkpoint), spec.taxonomy_sha256)
    thresholds = calibrate(dev)
    final = packet_for(manifest, spec.class_ids, file_sha256(checkpoint), spec.taxonomy_sha256, "independent_test")
    video_id = final["samples"][0]["video_id"]
    final["verdicts"] = [{"id": "v1", "video_id": video_id, "truth": True, "prediction": True},
                         {"id": "v2", "video_id": video_id, "truth": False, "prediction": False}]
    return {"root": root, "spec": spec, "manifest": manifest, "checkpoint": checkpoint, "indexes": indexes,
            "taxonomy": data["action_taxonomy"], "dev": dev, "final": final,
            "thresholds": thresholds, "metrics": evaluate(final, thresholds),
            "versions": {"dataset": "synthetic-v1", "split": manifest["split_version"],
                         "annotations": data["actions"]["annotation_version"], "rules": "unverified-v1"}}


def test_verdict_metrics_support_unknown_and_absolute_errors():
    result = binary_metrics([True, False, True, False, None, True], [True, True, False, False, True, None])
    assert [result[k] for k in ("tp", "tn", "fp", "fn", "absolute_errors")] == [1, 1, 1, 1, 2]
    assert result["accuracy"] == result["balanced_accuracy"] == result["macro_f1"] == .5
    assert result["accuracy_over_all_known"] == .4 and result["coverage"] == .8
    assert result["support"] == {"negative": 2, "positive": 3}
    assert result["unknown_truth"] == result["unknown_prediction_on_known"] == 1
    unknown = binary_metrics([None, True], [None, None])
    assert unknown["accuracy"] is None and unknown["coverage"] == 0 and unknown["fp"] == unknown["fn"] == 0
    with pytest.raises(ValueError):
        binary_metrics([0], [False])


def event(key, start, end, **changes):
    return {"id": key, "video_id": "v", "scene_id": "s", "class_id": "a", "start_sec": start,
            "end_sec": end, "known": True, **changes}


def test_event_maximum_one_to_one_matching_tolerance_and_scene_isolation():
    truth = [event("t0", 1, 2), event("t1", 1.8, 2.8)]
    actual = [event("a", 1.4, 2.4), event("b", .7, 1.7), event("wrong-scene", 1, 2, scene_id="other")]
    result = event_metrics(truth, actual)
    assert result["tp"] == 2 and result["fp"] == 1 and result["fn"] == 0
    assert result["precision"] == pytest.approx(2 / 3) and result["f1"] == pytest.approx(.8)
    assert event_metrics([event("t", 1, 2)], [event("p", 1.5, 2.5)])["tp"] == 1
    assert event_metrics([event("t", 1, 2)], [event("p", 1.5001, 2.5)])["tp"] == 0
    assert event_metrics([event("u", 1, 2, known=False)], [])["fn"] == 0


def test_dev_only_calibration_and_final_metrics_are_separate(export_case):
    case = export_case
    assert set(case["thresholds"]["values"].values()) == {.5}
    result = evaluate(case["final"], case["thresholds"])
    assert result["verdict_metrics"]["accuracy"] == 1 and result["test_only"]
    assert not result["real_targets_evaluated"] and result["validation_status"] == "not_validated"
    no_verdicts = evaluate(case["dev"], case["thresholds"])
    assert no_verdicts["verdict_metrics"] is None
    for split in ("train", "independent_test"):
        candidate = packet_for(case["manifest"], case["spec"].class_ids, case["dev"]["checkpoint_sha256"],
                               case["spec"].taxonomy_sha256, split)
        with pytest.raises(ValueError, match="only on dev"):
            calibrate(candidate)


def test_uncalibrated_class_stays_unknown_and_tolerance_is_fixed(export_case):
    packet = copy.deepcopy(export_case["dev"])
    for row in packet["samples"]:
        row["targets"][0] = True
    thresholds = calibrate(packet)
    assert thresholds["values"][packet["class_ids"][0]] is None
    assert evaluate(packet, thresholds)["action_sample_metrics"][packet["class_ids"][0]]["coverage"] == 0
    packet["event_protocol"]["tolerance_sec"] = .6
    with pytest.raises(ValueError, match="protocol"):
        evaluate(packet, thresholds)


def test_leakage_unknown_types_duplicate_points_and_source_partition_rejected(export_case):
    case = export_case
    leaked = copy.deepcopy(case["dev"])
    leaked["manifest"]["videos"][1]["group_id"] = leaked["manifest"]["videos"][0]["group_id"]
    leaked["manifest_sha256"] = stable_hash(leaked["manifest"])
    with pytest.raises(ValueError, match="crosses"):
        calibrate(leaked)
    for mode in ("point", "split", "score", "type", "real"):
        packet = copy.deepcopy(case["dev"])
        if mode == "point":
            packet["samples"].append(copy.deepcopy(packet["samples"][0]))
        elif mode == "split":
            packet["samples"][0]["video_id"] = case["manifest"]["videos"][0]["video_id"]
        elif mode == "score":
            packet["samples"][0]["scores"][0] = float("nan")
        elif mode == "type":
            packet["samples"][0]["targets"][0] = 1
        else:
            packet["test_only"] = False
        with pytest.raises(ValueError):
            validate_packet(packet)


def test_actual_checkpoint_scores_from_frozen_feature_cache(export_case):
    case = export_case
    packet = score_cache(case["root"] / "cache", case["checkpoint"], case["manifest"])
    assert packet["split"] == "train" and packet["test_only"] and packet["verdicts"] == []
    assert packet["samples"] and all(0 <= score <= 1 for row in packet["samples"] for score in row["scores"])
    assert any(target is None for row in packet["samples"] for target in row["targets"])
    changed = copy.deepcopy(case["manifest"])
    changed["dataset_version"] += "-changed"
    with pytest.raises(ValueError, match="manifest differs"):
        score_cache(case["root"] / "cache", case["checkpoint"], changed)


def test_actual_separate_dev_cache_uses_training_lineage_without_training_on_dev(tmp_path, export_case):
    case = export_case
    index = case["indexes"]["dev_validation"]
    scenes = define_scenes(index)
    windows = labelled_windows(index, scenes, {"records": []}, list(case["spec"].class_ids))
    encoder = FrozenEncoder(test_only=True)
    spec = replace(case["spec"], partition="dev_validation", windows_sha256=stable_hash(windows),
                   source_sha256=stable_hash({w["video_id"]: w["source_sha256"] for w in windows}))
    def frames():
        for row, frame in iter_indexed_frames(case["root"], index):
            yield (index["video_id"], scenes["scenes"][0]["scene_id"], index["split"], row["source_pts"]), frame.to_image(), 0
    build_cache(tmp_path / "dev-cache", source_root=case["root"], spec=spec, windows=windows,
                frames=frames(), encoder=encoder, encoder_metadata=encoder.descriptor())
    packet = score_cache(tmp_path / "dev-cache", case["checkpoint"], case["manifest"])
    assert packet["split"] == "dev_validation" and all(v is None for row in packet["samples"] for v in row["targets"])
    assert all(v is None for v in calibrate(packet)["values"].values())
    with pytest.raises(ValueError, match="only train"):
        train(tmp_path / "dev-cache", tmp_path / "forbidden", spec=spec, encoder=encoder)
