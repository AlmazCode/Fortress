import copy
import json
import shutil

import pytest
import torch

from contracts.python_ports import ModelNotReady, validate_contract
from ml.export import export_package
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256, safe_torch_load
from ml.release import ReleaseManager, import_package, load_package
from test_evaluation_export import export_case, cpu_threads


@pytest.fixture(scope="module")
def software_package(tmp_path_factory, export_case):
    root = tmp_path_factory.mktemp("M4-package") / "package"
    case = export_case
    export_package(case["checkpoint"], root, taxonomy=case["taxonomy"], thresholds=case["thresholds"],
                   metrics=case["metrics"], versions=case["versions"], release_version="software-M4-v1")
    return root


def rewrite(root, filename, document=None):
    if document is not None:
        (root / filename).write_text(json.dumps(document), encoding="utf-8")
    manifest = json.loads((root / "package.json").read_text())
    for entry in manifest["files"]:
        if entry["path"] == filename:
            entry.update(sha256=file_sha256(root / filename), size_bytes=(root / filename).stat().st_size)
    (root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_missing_arbitrary_and_test_packages_refuse_production(tmp_path, software_package):
    manager = ReleaseManager()
    assert manager.readiness()["status"] == "not_ready" and not manager.readiness()["trained"]
    for path in (tmp_path / "absent", software_package):
        with pytest.raises(ModelNotReady):
            manager.load(path)
    (tmp_path / "best.pt").write_bytes(b"not a release")
    with pytest.raises(ModelNotReady):
        manager.load(tmp_path / "best.pt")
    assert manager.readiness()["status"] == "not_ready"


def test_explicit_test_loader_validates_complete_state_and_still_is_not_ready(software_package):
    loaded = load_package(software_package, allow_test=True)
    assert loaded.test_only and not loaded.model.training and all(not p.requires_grad for p in loaded.model.parameters())
    assert loaded.config["architecture"]["feature_dim"] == 576
    manager = ReleaseManager(allow_test=True)
    manager.load(software_package)
    readiness = manager.readiness()
    assert readiness["status"] == "not_ready" and readiness["test_only"] and not readiness["validated"]
    # Use K's containing diagnostics fixture to check the exact Model definition.
    from jsonschema import Draft202012Validator
    schema = json.loads((__import__("pathlib").Path(__file__).parents[2] / "contracts/diagnostics.schema.json").read_text())
    Draft202012Validator(schema["$defs"]["Model"]).validate(readiness)
    with pytest.raises(ModelNotReady, match="taxonomy"):
        load_package(software_package, allow_test=True, expected_taxonomy="unknown-version")
    with pytest.raises(ModelNotReady, match="rules"):
        load_package(software_package, allow_test=True, expected_rules="unknown-version")
    with pytest.raises(ModelNotReady, match="manifest SHA"):
        load_package(software_package, allow_test=True, expected_manifest_sha256="0" * 64)


@pytest.mark.parametrize("change", ["hash", "missing", "extra", "traversal", "preprocessing", "taxonomy", "shape", "dev", "dev-source", "provenance"])
def test_corruption_and_semantic_mismatches_rejected_with_old_snapshot_intact(tmp_path, software_package, change):
    root = tmp_path / "changed"
    shutil.copytree(software_package, root)
    manager = ReleaseManager(allow_test=True)
    manager.load(software_package)
    previous = manager.snapshot()
    if change == "hash":
        (root / "model.pt").write_bytes(b"corrupt")
    elif change == "missing":
        (root / "taxonomy.json").unlink()
    elif change == "extra":
        (root / "payload.py").write_text("raise RuntimeError('never execute')")
    elif change == "traversal":
        document = json.loads((root / "package.json").read_text())
        document["files"][0]["path"] = "../model.pt"
        rewrite(root, "package.json", document)
    elif change in ("preprocessing", "provenance"):
        document = json.loads((root / "config.json").read_text())
        if change == "preprocessing":
            document["preprocessing"]["version"] = "unimplemented-v2"
        else:
            document["test_only"] = False
        rewrite(root, "config.json", document)
    elif change == "taxonomy":
        document = json.loads((root / "taxonomy.json").read_text(encoding="utf-8"))
        document["classes"].reverse()
        rewrite(root, "taxonomy.json", document)
    elif change == "shape":
        state = {k: v.clone() for k, v in safe_torch_load(root / "model.pt").items()}
        state["temporal.head.weight"] = torch.zeros(1, 256)
        torch.save(state, root / "model.pt")
        rewrite(root, "model.pt")
    elif change == "dev":
        document = json.loads((root / "thresholds.json").read_text())
        document["selected_on"] = "independent_test"
        rewrite(root, "thresholds.json", document)
    else:
        document = json.loads((root / "thresholds.json").read_text())
        metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
        document["dev_video_ids"] = [next(r["video_id"] for r in metrics["split_manifest"]["videos"] if r["split"] == "train")]
        rewrite(root, "thresholds.json", document)
        metrics["thresholds_sha256"] = stable_hash(document)
        rewrite(root, "metrics.json", metrics)
    with pytest.raises(ModelNotReady):
        manager.load(root)
    assert manager.snapshot() is previous and not manager.readiness()["trained"]


def test_atomic_import_activation_failure_restart_and_rollback(tmp_path, software_package, monkeypatch):
    import ml.release as module
    first, second = tmp_path / "first", tmp_path / "second"
    report = import_package(software_package, first, allow_test=True)
    assert report["data"]["test_only"] and not report["data"]["production_ready"]
    import_package(software_package, second, allow_test=True)
    manager = ReleaseManager(allow_test=True)
    pointer = tmp_path / "active.json"
    manager.load(first, pointer=pointer)
    original, old = pointer.read_bytes(), manager.snapshot()
    replacement = module.os.replace
    def fail(*args):
        raise OSError("injected atomic replace failure")
    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(OSError, match="injected"):
        manager.load(second, pointer=pointer)
    assert manager.snapshot() is old and pointer.read_bytes() == original
    monkeypatch.setattr(module.os, "replace", replacement)
    manager.load(second, pointer=pointer)
    restarted = ReleaseManager(allow_test=True)
    restarted.restore_pointer(pointer)
    assert restarted.snapshot().directory == second.resolve()
    # A separate process must retain the previous path, rather than overwrite it with null.
    history = json.loads(pointer.read_text())
    assert history["previous"]["path"] == str(first.resolve())
    restarted.restore_pointer(pointer, previous=True)
    assert restarted.snapshot().directory == first.resolve()
    restarted.restore_pointer(pointer, previous=True)
    assert restarted.snapshot().directory == second.resolve() and first.is_dir()
    assert import_package(software_package, first, allow_test=True) == report
