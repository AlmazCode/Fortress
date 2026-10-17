"""Real model fits and the grouping/calibration boundaries of small-data CV."""
import copy
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest
import torch
from torch import nn

from ml.models.encoder import safe_torch_load
from ml.small_data import (Experiment, MAX_FRAMES, WindowMIL, fit_norm, frame_selection,
                           split_folds, summarize, window_tokens, training_source, legacy_code_matches)


@pytest.fixture(autouse=True)
def single_thread():
    before = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(before)


def rows(count=16):
    rng = torch.Generator().manual_seed(19)
    return [{"video_id": f"v{i}", "source_sha256": str(i), "group_id": f"g{i//2}",
             "split": "train", "target": i % 2,
             "features": torch.randn((5+i%3, 576), generator=rng) + (i%2)*.7}
            for i in range(count)]


def experiment(tmp_path, data):
    obj = Experiment.__new__(Experiment)
    obj.directory, obj.device = tmp_path, "cpu"
    obj.plan = {"protocol_sha256": "test-protocol", "development_ids": [r["video_id"] for r in data]}
    obj.by_id = {r["video_id"]: r for r in data}
    obj.fits = tmp_path / "fits"
    obj.fits.mkdir()
    obj.prefix, obj.weights_sha = {}, "test-only"
    return obj


def test_grouped_oof_exact_coverage_and_determinism():
    data = rows()
    folds = split_folds(data, 4, 42)
    assert folds == split_folds(data, 4, 42)
    by_id = {r["video_id"]: r for r in data}
    assert sorted(v for f in folds for v in f["validation"]) == sorted(by_id)
    for fold in folds:
        assert {by_id[v]["group_id"] for v in fold["train"]}.isdisjoint({by_id[v]["group_id"] for v in fold["validation"]})
        inner = split_folds([by_id[v] for v in fold["train"]], 3, 43)
        assert not set(v for f in inner for v in f["train"]+f["validation"]) & set(fold["validation"])
    data[0]["split"] = "independent_test"
    with pytest.raises(ValueError, match="reserved"):
        split_folds(data, 4, 42)
    with pytest.raises(ValueError, match="test data"):
        fit_norm(data)


def test_duplicate_or_one_class_cannot_train_or_split():
    data = rows()
    data[1]["source_sha256"] = data[0]["source_sha256"]
    with pytest.raises(ValueError, match="duplicate"):
        split_folds(data, 4, 42)
    with pytest.raises(ValueError, match="both"):
        fit_norm([r for r in rows() if r["target"] == 1])


def test_temporal_sampling_order_and_mil_padding():
    for n in (1, 5, 64, 65, 360):
        for rng in (None, np.random.default_rng(42)):
            selected = frame_selection(n, rng=rng)
            assert len(selected) == min(n, MAX_FRAMES)
            assert all(a < b for a, b in zip(selected, selected[1:]))
            assert min(selected) >= 0 and max(selected) < n
    model = WindowMIL(.2).eval()
    values = window_tokens(torch.randn(17, 576))
    padded = torch.cat((values, torch.full((3, 1728), 1e4)))
    assert torch.allclose(model(values[None], torch.tensor([len(values)])),
                          model(padded[None], torch.tensor([len(values)])))
    assert window_tokens(torch.ones(1, 576)).shape == (1, 1728)


@pytest.mark.parametrize("arm", ["linear", "gru", "mil"])
def test_actual_fit_fits_only_training_rows_and_prediction_reload(tmp_path, arm):
    data = rows(8)
    obj = experiment(tmp_path, data)
    train_ids = [r["video_id"] for r in data[:6]]
    config = {"c": 1.} if arm == "linear" else {"epochs": 3, "lr": .001, "dropout": .2, "weight_decay": .01}
    path = obj.fit(train_ids, arm, config, 42)
    state = safe_torch_load(path)
    assert torch.equal(state["normalization"]["mean"], fit_norm(data[:6])["mean"])
    predictions = obj.predict(path, ["v6", "v7"])
    assert all(0 <= r["score"] <= 1 for r in predictions)
    before = Path(path).read_bytes()
    obj.by_id["v6"]["features"] *= 1e5
    assert obj.fit(train_ids, arm, config, 42) == path and Path(path).read_bytes() == before
    assert obj.predict(path, ["v7"]) == predictions[1:]
    obj.by_id["heldout"] = {**data[0], "video_id": "heldout", "split": "independent_test"}
    with pytest.raises(ValueError, match="development"):
        obj.fit([*train_ids, "heldout"], arm, config, 42)


def test_real_suffix_finetuning_changes_weights_without_mutating_template(tmp_path):
    data = rows(4)
    obj = experiment(tmp_path, data)
    obj.suffix_template = nn.Sequential(nn.Conv2d(2, 576, 1))
    original = copy.deepcopy(obj.suffix_template.state_dict())
    obj.prefix = {r["video_id"]: {name: torch.randn(len(r["features"]), 3, 2, 2, 2)
                                for name in ("base", "dark", "bright")} for r in data}
    obj.prefix_marker = {"entries": {r["video_id"]: {"sha256": "synthetic"} for r in data}}
    config = {"epochs": 2, "lr": .001, "dropout": .2, "weight_decay": .01,
              "adapt_epochs": 2, "backbone_lr": .001, "head_lr": .001}
    fitted = obj.fit([r["video_id"] for r in data], "finetune", config, 42)
    state = safe_torch_load(fitted)
    assert any(not torch.equal(v, state["suffix"][k]) for k, v in original.items())
    assert all(torch.equal(v, obj.suffix_template.state_dict()[k]) for k, v in original.items())
    assert all(torch.isfinite(v).all() for v in state["suffix"].values())
    assert len(obj.predict(fitted, [r["video_id"] for r in data])) == 4


def test_inner_selection_sees_only_inner_validation_and_uses_its_threshold(tmp_path):
    obj = experiment(tmp_path, rows(8))
    obj.plan.update({"grid": {"linear": [{"c": .1}, {"c": 1.}]}, "selection_seed": 42})
    folds = split_folds(rows(8), 2, 42)
    calls = []

    def fit(ids, arm, config, seed):
        return (set(ids), config["c"])

    def predict(fitted, ids):
        assert fitted[0].isdisjoint(ids)
        calls.append(list(ids))
        return [{"video_id": v, "truth": bool(obj.by_id[v]["target"]),
                 "score": (.61 if obj.by_id[v]["target"] else .60) if fitted[1] == 1 else .5} for v in ids]

    obj.fit, obj.predict = fit, predict
    choices, selected = obj.select(folds)
    assert selected["config"]["c"] == 1.
    assert .60 < selected["threshold"] < .61
    assert selected["metrics"]["accuracy"] == 1.
    assert len(calls) == 4 and choices["linear"] == selected
    assert summarize([{**r, "threshold": selected["threshold"]} for r in selected["oof"]])["accuracy"] == 1.


def test_training_fingerprint_allows_inference_patch_but_rejects_model_or_grid_change(tmp_path):
    import ml.small_data as module
    from ml.data.deduplicate import stable_hash
    current = Path(module.__file__).read_text(encoding="utf-8")
    inference_patch = current.replace('"scene_id": "raw-unreviewed"', '"scene_id": "raw-diagnostic"')
    assert inference_patch != current and training_source(current) == training_source(inference_patch)
    assert training_source(current) == training_source(current.replace('\n', '\r\n'))
    changed_training = current.replace('MAX_FRAMES = 64', 'MAX_FRAMES = 32')
    assert training_source(current) != training_source(changed_training)
    names = ("small_data.py", "video_baseline.py", "models/encoder.py", "preprocessing.py")
    base = Path(module.__file__).parent
    payload = {name: (inference_patch.encode() if name == "small_data.py" else (base/name).read_bytes()) for name in names}
    def write_snapshot():
        with zipfile.ZipFile(tmp_path/'source_snapshot.zip', 'w') as archive:
            for name, data in payload.items(): archive.writestr('ml/'+name, data)
        return stable_hash({name: hashlib.sha256(data).hexdigest() for name, data in payload.items()})
    expected = write_snapshot()
    assert legacy_code_matches(tmp_path, expected)
    assert not legacy_code_matches(tmp_path, '0'*64)
    payload['small_data.py'] = changed_training.encode()
    assert not legacy_code_matches(tmp_path, write_snapshot())


def test_raw_inference_passes_strict_manifest_without_model_only_fields(tmp_path, monkeypatch):
    import ml.small_data as module
    from contracts.python_ports import validate_contract
    from ml.models.encoder import file_sha256
    model = tmp_path/'fit.pt'; model.write_bytes(b'checkpoint-hash-fixture')
    decision = {'fit':str(model),'fit_sha256':file_sha256(model)}
    (tmp_path/'frozen_decision.json').write_text(json.dumps(decision),encoding='utf-8')
    complete = {'decision_sha256':file_sha256(tmp_path/'frozen_decision.json')}
    (tmp_path/'complete.json').write_text(json.dumps(complete),encoding='utf-8')
    source = tmp_path/'sample.mov'; source.write_bytes(b'local-source-hash-fixture')
    monkeypatch.setattr(module, 'Experiment', lambda *a, **k: object())
    monkeypatch.setattr(module, 'probe_video', lambda _: ({'duration_sec':1.,'width':32,'height':24,
                        'rotation':0,'source_start_pts':0,'time_base':{'num':1,'den':2},'vfr':False}, {}))
    class ManifestPassed(Exception): pass
    def boundary(root, row, **kwargs):
        validate_contract('manifest', {'schema_version':'1.0','dataset_version':'raw-inference-v1',
                          'split_version':'not-training','videos':[row]})
        assert 'source_sha256' not in row and 'target' not in row
        raise ManifestPassed
    monkeypatch.setattr(module,'build_index',boundary)
    with pytest.raises(ManifestPassed):
        module.infer_video(tmp_path,source,weights=model,weights_sha256='unused',device='cpu')
