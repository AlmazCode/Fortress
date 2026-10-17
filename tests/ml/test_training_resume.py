from dataclasses import replace
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest
import torch

from ml.cache import build_cache
from ml.data.deduplicate import stable_hash
from ml.models import FrozenEncoder
from ml.models.encoder import file_sha256, safe_torch_load
from ml.train import TrainConfig, train
from test_cache_resume import cache_case


@pytest.fixture(scope="module", autouse=True)
def cpu_threads():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def training_case(root, *, unknown=False):
    data, windows, _, _, spec, frames = cache_case(root)
    if unknown:
        windows = copy.deepcopy(windows)
        for window in windows:
            window["known_mask"] = [[False] * len(spec.class_ids) for _ in window["samples"]]
    encoder = FrozenEncoder(test_only=True)
    metadata = encoder.descriptor()
    spec = replace(spec, encoder_sha256=stable_hash(metadata), windows_sha256=stable_hash(windows))
    directory = root / "cache"
    build_cache(directory, source_root=data["source_root"], spec=spec, windows=windows, frames=frames(),
                encoder=encoder, encoder_metadata=metadata)
    return directory, spec


@pytest.fixture(scope="module")
def actual_cache(tmp_path_factory):
    return training_case(tmp_path_factory.mktemp("actual-mobile-features"))


def run(directory, output, spec, **kwargs):
    return train(directory, output, spec=spec, encoder=FrozenEncoder(test_only=True), **kwargs)


def test_cpu_adamw_and_resume_equal_uninterrupted_and_keep_previous_immutable(tmp_path, actual_cache):
    directory, spec = actual_cache
    full = run(directory, tmp_path / "full", spec, steps=2)
    part = run(directory, tmp_path / "part", spec, steps=1)
    old_sha = file_sha256(tmp_path / "part" / "checkpoint.pt")
    resumed = run(directory, tmp_path / "resumed", spec, steps=2, resume=tmp_path / "part" / "checkpoint.pt")
    a, b = [safe_torch_load(tmp_path / name / "checkpoint.pt") for name in ("full", "resumed")]
    assert a["losses"] == b["losses"] and len(a["losses"]) == 2
    assert all(torch.equal(a["model"][k], b["model"][k]) for k in a["model"])
    assert a["order"] == b["order"] and a["cursor"] == b["cursor"]
    assert file_sha256(tmp_path / "part" / "checkpoint.pt") == old_sha
    assert full["data"]["completed_steps"] == 2 and part["data"]["completed_steps"] == 1
    assert resumed["data"]["resumed"] and resumed["data"]["frozen_encoder_unchanged"]
    assert not resumed["data"]["trained"] and not resumed["data"]["production_ready"]
    assert set(a["optimizer"]["state"])  # Actual Adam moments, not a simulated checkpoint.
    assert run(directory, tmp_path / "full", spec, steps=2) == full
    with pytest.raises(ValueError):
        run(directory, tmp_path / "full", spec, steps=1)


def test_all_unknown_creates_no_optimizer_step_or_fake_negative(tmp_path):
    directory, spec = training_case(tmp_path, unknown=True)
    result = run(directory, tmp_path / "unknown", spec)
    checkpoint = safe_torch_load(tmp_path / "unknown" / "checkpoint.pt")
    assert result["data"]["all_unknown"] and result["data"]["completed_steps"] == 0
    assert checkpoint["losses"] == [] and checkpoint["optimizer"]["state"] == {}


def test_resume_mismatches_rejected_before_new_output(tmp_path, actual_cache):
    directory, spec = actual_cache
    run(directory, tmp_path / "part", spec, steps=1)
    resume = tmp_path / "part" / "checkpoint.pt"
    with pytest.raises(ValueError, match="resume"):
        run(directory, tmp_path / "changed", spec, resume=resume, config=TrainConfig(seed=43))
    assert not (tmp_path / "changed").exists()
    for field in ("annotation_sha256", "taxonomy_sha256", "dataset_sha256", "split_sha256"):
        with pytest.raises(ValueError):
            run(directory, tmp_path / field, replace(spec, **{field: "0" * 64}), resume=resume)
    with pytest.raises(ValueError):
        run(directory, tmp_path / "classes", replace(spec, class_ids=tuple(reversed(spec.class_ids))), resume=resume)


def test_smoke_and_training_gates(tmp_path, actual_cache):
    directory, spec = actual_cache
    with pytest.raises(ValueError, match="tiny"):
        run(directory, tmp_path / "too-long", spec, steps=5)
    with pytest.raises(ValueError, match="future training"):
        run(directory, tmp_path / "full-denied", spec, smoke=False, allow_real_training=True,
            readiness={"data_ready": True, "dataset_revision": spec.dataset_sha256})
    with pytest.raises(ValueError):
        run(directory, tmp_path / "dev-denied", replace(spec, partition="dev_validation"))


class ForbiddenObject:
    def __reduce__(self):
        return eval, ("__import__('builtins').print('FORBIDDEN_CHECKPOINT_EXECUTED')",)


def test_tensor_only_loader_refuses_executable_globals_legacy_and_limits(tmp_path, capsys):
    dangerous = tmp_path / "object.pt"
    torch.save({"object": ForbiddenObject()}, dangerous)
    with pytest.raises(ValueError, match="unsupported tensor"):
        safe_torch_load(dangerous)
    assert "FORBIDDEN_CHECKPOINT_EXECUTED" not in capsys.readouterr().out
    legacy = tmp_path / "legacy.pt"
    torch.save({"tensor": torch.zeros(1)}, legacy, _use_new_zipfile_serialization=False)
    with pytest.raises(ValueError):
        safe_torch_load(legacy)
    valid = tmp_path / "tensor.pt"
    torch.save({"tensor": torch.zeros(2)}, valid)
    with pytest.raises(ValueError, match="byte budget|bounded"):
        safe_torch_load(valid, max_bytes=20)
    with pytest.raises(ValueError, match="SHA"):
        safe_torch_load(valid, expected_sha256="0" * 64)
    for name, value in (("nan", torch.tensor(float("nan"))), ("dtype", torch.zeros(2, dtype=torch.float64))):
        path = tmp_path / (name + ".pt")
        torch.save({"tensor": value}, path)
        with pytest.raises(ValueError):
            safe_torch_load(path)


def test_actual_cli_cpu_checkpoint_and_resume(tmp_path, actual_cache):
    directory, _ = actual_cache
    for name, extra in (("first", ["--steps", "1"]), ("second", ["--steps", "2", "--resume",
                        str(tmp_path / "first" / "checkpoint.pt")])):
        result = subprocess.run([sys.executable, "-m", "ml.train", "--cache", str(directory),
                                 "--output-dir", str(tmp_path / name), "--smoke", *extra],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["test_only"] and not report["production_ready"]
    assert json.loads((tmp_path / "second" / "training_report.json").read_text())["completed_steps"] == 2
