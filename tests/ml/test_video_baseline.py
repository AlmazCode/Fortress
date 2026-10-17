"""Real IO, leakage guards and exact interrupted-training recovery for baseline."""
import copy
from dataclasses import replace
from fractions import Fraction
import json

import av
import numpy as np
import pytest
import torch

from ml.data.annotation_tasks import read_json
from ml.data.taxonomy import load_taxonomy, validate_taxonomy
from ml.data.training_package import (candidate_taxonomy, load_prepared, prepare, validate_package_inputs)
from ml.models.encoder import safe_torch_load
from ml.video_baseline import (Config, VerdictGRU, calibrate_video, input_views, metrics, normalization, quality_gate, train)


@pytest.fixture(autouse=True)
def bounded_cpu_threads():
    before = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(before)


@pytest.fixture
def tiny_package(tmp_path):
    root = tmp_path / "package"
    (root / "annotations").mkdir(parents=True)
    (root / "videos").mkdir()
    rows, actions = [], []
    split = {"videos": {"train": [], "val": [], "test": []}, "scenario_families": []}
    import hashlib
    for n in range(1, 7):
        video_id = f"video_{n:03}"
        partition = ["train", "val", "test"][(n-1)//2]
        relative = f"videos/{video_id}.mkv"
        with av.open(str(root / relative), "w") as container:
            stream = container.add_stream("ffv1", rate=2)
            stream.width, stream.height, stream.pix_fmt = 32, 24, "bgr0"
            for i in range(4):
                image = np.random.default_rng(n * 100 + i).integers(0, 256, (24, 32, 3), dtype=np.uint8)
                frame = av.VideoFrame.from_ndarray(image, format="rgb24")
                frame.pts, frame.time_base = i, Fraction(1, 2)
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        rows.append({"video_id": video_id, "video_path": relative, "source_sha256": digest,
                     "duration_sec": 2., "split": partition, "scenario_family": "family_" + str(n),
                     "verdict": "violation" if n % 2 else "no_violation", "verdict_source": "user_scenario",
                     "provenance_kind": "synthetic"})
        split["videos"][partition].append(video_id)
        split["scenario_families"].append([n])
        actions.append({"id": "event-" + str(n), "video_id": video_id, "split": partition,
                        "start_sec": 0., "end_sec": 1., "event_type": "receive_ID", "visibility": "partial",
                        "reviewed": True, "known": True, "explicit_negative": False,
                        "label_source": "synthetic_fixture", "evidence": []})
    objects = {"categories": [{"id": 3, "name": "key"}], "annotations": [], "images": []}
    for name, value in (("annotations/video_labels.json", {"videos": rows}), ("splits.json", split),
                        ("annotations/actions.json", {"annotations": actions}),
                        ("annotations/objects.coco.json", objects), ("annotations/people.coco.json", {"annotations": []})):
        (root / name).write_text(json.dumps(value), encoding="utf-8")
    return root


def test_real_import_preserves_groups_hashes_and_unreviewed_unknowns(tiny_package, tmp_path):
    before = {p.relative_to(tiny_package).as_posix(): p.read_bytes() for p in tiny_package.rglob("*") if p.is_file()}
    destination = tmp_path / "prepared"
    result = prepare(tiny_package, destination, allow_dataset_use=True)["data"]
    assert result["video_training_ready"] and not result["action_training_ready"] and not result["production_ready"]
    assert result["data_kind"] == "synthetic_or_mixed"
    assert result["object_support"][0]["active_for_detector_training"] is False
    actions = read_json(destination / "actions.json")
    assert len(actions["records"]) == 6
    assert all(r["state"] == "unreviewed" and not r["known_mask"] and not r["human_approved"] for r in actions["records"])
    assert all(r["actor_id"] is None and r["weak_source_record"]["reviewed"] for r in actions["records"])
    report, manifest = load_prepared(destination)
    assert {v["split"] for v in manifest["videos"]} == {"train", "dev_validation", "independent_test"}
    assert all(v["provenance"]["kind"] == "synthetic" for v in manifest["videos"])
    assert prepare(tiny_package, destination, allow_dataset_use=True)["data"] == report
    assert {p.relative_to(tiny_package).as_posix(): p.read_bytes() for p in tiny_package.rglob("*") if p.is_file()} == before
    source = tiny_package / manifest["videos"][0]["path"]
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="original source changed"):
        load_prepared(destination)


@pytest.mark.parametrize("defect", ["hash", "family", "membership", "video_id", "missing_label_source", "one_class_dev"])
def test_input_defects_rejected_before_decoder(tiny_package, defect):
    labels = read_json(tiny_package / "annotations/video_labels.json")
    split = read_json(tiny_package / "splits.json")
    actions = read_json(tiny_package / "annotations/actions.json")
    if defect == "hash":
        labels["videos"][2]["source_sha256"] = labels["videos"][0]["source_sha256"]
    elif defect == "family":
        labels["videos"][2]["scenario_family"] = labels["videos"][0]["scenario_family"]
    elif defect == "membership":
        split["videos"]["train"].append(split["videos"]["test"][0])
    elif defect == "video_id":
        labels["videos"][0]["video_id"] = "../../escape"
    elif defect == "missing_label_source":
        labels["videos"][0]["verdict_source"] = "model_prediction"
    else:
        for r in labels["videos"]:
            if r["split"] == "val":
                r["verdict"] = "violation"
    with pytest.raises(ValueError):
        validate_package_inputs(labels, split, actions)


def test_new_action_candidate_has_no_invented_case_route():
    from pathlib import Path
    base = load_taxonomy(Path(__file__).parents[2] / "ml/config/action_taxonomy.draft.json")
    taxonomy, mapping = candidate_taxonomy({"annotations": [{"event_type": "receive_ID"}]}, base)
    assert mapping["receive_ID"] == "action.receive_id"
    candidate = next(r for r in taxonomy["classes"] if r["id"] == "action.receive_id")
    assert candidate["case_refs"] == [] and candidate["case_mapping_status"] == "unmapped"
    validate_taxonomy(taxonomy, previous=base)
    taxonomy.update(status="reviewed", reviewer="test_reviewer")
    with pytest.raises(ValueError, match="missing case_refs"):
        validate_taxonomy(taxonomy)
    with pytest.raises(ValueError, match="collide"):
        candidate_taxonomy({"annotations": [{"event_type": "receive-ID"}, {"event_type": "receive_ID"}]}, base)


def test_padding_has_no_effect_and_normalization_rejects_nontrain():
    torch.set_num_threads(1)
    torch.manual_seed(1)
    model = VerdictGRU(dropout=0).eval()
    values = torch.randn(2, 7, 576)
    lengths = torch.tensor([3, 7])
    expected = model(values, lengths)
    values[0, 3:] = 10000
    assert torch.equal(model(values, lengths), expected)
    with pytest.raises(ValueError, match="train videos only"):
        normalization([{"split": "dev_validation", "features": torch.ones(2, 576)}])


def test_views_are_versioned_fixed_shape_and_use_display_rotation():
    from PIL import Image
    image = Image.fromarray(np.random.default_rng(4).integers(0, 256, (80, 40, 3), dtype=np.uint8))
    global_view = input_views(image, 90, "global")
    crops = input_views(image, 90, "three_crop")
    assert global_view.shape == (1, 3, 224, 224) and crops.shape == (3, 3, 224, 224)
    assert torch.equal(global_view[0], crops[0]) and torch.isfinite(crops).all()
    assert not torch.equal(crops[1], crops[2])
    with pytest.raises(ValueError, match="view mode"):
        input_views(image, 0, "undefined")


def test_thresholds_and_quality_do_not_turn_internal_scores_into_independent_80():
    rows = [{"truth": False, "score": .1}, {"truth": True, "score": .9}]
    with pytest.raises(ValueError, match="development only"):
        calibrate_video(rows, partition="independent_test")
    threshold = calibrate_video(rows, partition="dev_validation")
    result = metrics(rows, threshold)
    assert result["accuracy"] == 1
    assert quality_gate(result, independent_external_test=False) == {
        "target": .8, "internal_target_reached": True, "independent_80_confirmed": False, "production_ready": False,
        "reason": "An internal camera holdout cannot establish independent/generalization quality or event/rules readiness."}


def test_calibration_does_not_miss_narrow_development_score_separation():
    rows = [{"truth": False, "score": .4627288}, {"truth": True, "score": .4717599},
            {"truth": True, "score": .4660068}, {"truth": False, "score": .4579346}]
    threshold = calibrate_video(rows, partition="dev_validation")
    assert .4627288 < threshold < .4660068
    assert metrics(rows, threshold)["accuracy"] == 1.
    assert not quality_gate(metrics(rows, threshold), independent_external_test=False)["independent_80_confirmed"]


def toy_cache():
    rows = []
    for n in range(8):
        partition = "train" if n < 4 else "dev_validation" if n < 6 else "independent_test"
        generator = torch.Generator().manual_seed(n)
        rows.append({"video_id": f"v{n}", "split": partition, "target": n % 2,
                     "features": torch.randn(4 + n % 3, 576, generator=generator) * .05 + n % 2})
    return {"prepared_dir": "test-fixture", "format": "isolated-numeric-test"}, rows


def test_real_optimizer_resume_equals_uninterrupted_and_never_scores_test(monkeypatch, tmp_path):
    import ml.video_baseline as module
    document, rows = toy_cache()
    monkeypatch.setattr(module, "load_feature_cache", lambda path: (document, copy.deepcopy(rows)))
    monkeypatch.setattr(module, "load_prepared", lambda path: None)
    seen = []
    original = module.scores

    def guarded(model, selected, *args):
        assert all(r["split"] != "independent_test" for r in selected)
        seen.extend(r["video_id"] for r in selected)
        return original(model, selected, *args)

    monkeypatch.setattr(module, "scores", guarded)
    config = Config(epochs=4, device="cpu", cpu_threads=1, patience=10)
    complete = train("unused", tmp_path / "complete", config=config)
    train("unused", tmp_path / "first", config=config, stop_after_epochs=2)
    resumed = train("unused", tmp_path / "resumed", config=config, resume=tmp_path / "first/last.pt")
    a, b = [safe_torch_load(tmp_path / name / "last.pt") for name in ("complete", "resumed")]
    assert a["completed_epochs"] == b["completed_epochs"] == 4
    assert a["history"] == b["history"]
    assert all(torch.equal(a["model"][key], b["model"][key]) for key in a["model"])
    assert resumed["resumed"] and not complete["test_evaluated"] and not resumed["test_evaluated"]
    assert complete["dev_metrics"] == resumed["dev_metrics"]
    assert not complete["production_ready"] and not complete["event_localization_trained"]
    assert set(seen) == {"v0", "v1", "v2", "v3", "v4", "v5"}
    with pytest.raises(ValueError, match="mismatch"):
        train("unused", tmp_path / "bad_resume", config=replace(config, dropout=.2), resume=tmp_path / "first/last.pt")
    assert not (tmp_path / "bad_resume").exists()


@pytest.mark.parametrize("changes", [{"batch_size": 0}, {"learning_rate": float("nan")}, {"dropout": 1}, {"epochs": -1}])
def test_invalid_config_rejected(changes):
    with pytest.raises(ValueError):
        Config(**changes)
