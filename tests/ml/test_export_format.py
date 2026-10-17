import copy
import json
import subprocess
import sys

import pytest
import torch

from ml.data.deduplicate import stable_hash
from ml.export import export_package, model_budget
from ml.models.encoder import file_sha256, safe_torch_load
from test_evaluation_export import export_case, cpu_threads


def export(output, case, **changes):
    options = {"taxonomy": case["taxonomy"], "thresholds": case["thresholds"], "metrics": case["metrics"],
               "versions": case["versions"], "release_version": "tiny-software-v1", **changes}
    return export_package(case["checkpoint"], output, **options)


def test_whole_model_export_hashes_versions_and_numeric_tensor_only_state(tmp_path, export_case):
    case = export_case
    report = export(tmp_path / "release", case)["data"]
    manifest = json.loads((tmp_path / "release/package.json").read_text())
    config = json.loads((tmp_path / "release/config.json").read_text())
    state = safe_torch_load(tmp_path / "release/model.pt", max_bytes=12000000)
    assert report["test_only"] and not report["production_ready"] and manifest["actual_weights"] == "None"
    assert not (tmp_path / "release/release.json").exists()
    assert config["versions"] == case["versions"] and config["training_spec"] == case["spec"].descriptor()
    assert config["preprocessing"] == json.loads((tmp_path / "release/preprocessing.json").read_text())
    assert set(manifest["files"][i]["role"] for i in range(len(manifest["files"]))) == {
        "checkpoint", "config", "taxonomy", "preprocessing", "thresholds", "metrics", "model_card", "rules", "split", "annotations"}
    for entry in manifest["files"]:
        path = tmp_path / "release" / entry["path"]
        assert file_sha256(path) == entry["sha256"] and path.stat().st_size == entry["size_bytes"]
    assert all(torch.is_tensor(v) for v in state.values())
    assert any(k.startswith("encoder.features.") for k in state) and any(k.startswith("temporal.gru.") for k in state)
    budget = report["budget"]
    assert budget["encoder_tensor_bytes"] > 3000000 and budget["gru_head_tensor_bytes"] > 2500000
    assert budget["whole_model_tensor_bytes"] == budget["encoder_tensor_bytes"] + budget["gru_head_tensor_bytes"]
    assert budget["passed"] and budget["whole_model_file_bytes"] <= 12000000
    assert budget["whole_model_file_MB"] == budget["whole_model_file_bytes"] / 1000000
    assert budget["training_checkpoint_bytes_with_optimizer"] > budget["whole_model_file_bytes"]
    assert export(tmp_path / "release", case)["data"] == report


def test_production_random_and_bad_lineage_refused_old_package_preserved(tmp_path, export_case):
    case = export_case
    export(tmp_path / "prior", case)
    original = (tmp_path / "prior/model.pt").read_bytes()
    with pytest.raises(ValueError, match="production"):
        export(tmp_path / "fake-production", case, production=True, approval={"approved": True, "reviewer": "smoke"})
    assert not (tmp_path / "fake-production").exists()
    for field, new_value in (("checkpoint_sha256", "0" * 64), ("taxonomy_sha256", "0" * 64)):
        thresholds = {**case["thresholds"], field: new_value}
        with pytest.raises(ValueError):
            export(tmp_path / field, case, thresholds=thresholds)
    taxonomy = copy.deepcopy(case["taxonomy"])
    taxonomy["classes"].reverse()
    with pytest.raises(ValueError, match="taxonomy/order"):
        export(tmp_path / "reordered", case, taxonomy=taxonomy)
    with pytest.raises(ValueError):
        export(tmp_path / "prior", case, release_version="new-version")
    assert (tmp_path / "prior/model.pt").read_bytes() == original


def test_budget_does_not_exclude_encoder_and_rejects_missing_or_non_fp32_state():
    state = {"encoder.features.weight": torch.zeros(1), "temporal.head.weight": torch.zeros(1)}
    assert not model_budget(state, 12000001, 20000000)["passed"]
    with pytest.raises(ValueError, match="whole encoder"):
        model_budget({"temporal.head.weight": torch.zeros(1)}, 10, 100)
    with pytest.raises(ValueError, match="FP32"):
        model_budget({"encoder.features.weight": torch.zeros(1, dtype=torch.float16)}, 10, 100)


def test_export_cli_actual_package(tmp_path, export_case):
    case = export_case
    for name in ("dev", "final"):
        (tmp_path / (name + ".json")).write_text(json.dumps(case[name]), encoding="utf-8")
    for module, arguments in (("ml.thresholds", ["--input", str(tmp_path / "dev.json"),
                                                "--output", str(tmp_path / "cli-thresholds.json")]),
                              ("ml.evaluate", ["--input", str(tmp_path / "final.json"),
                                               "--thresholds", str(tmp_path / "cli-thresholds.json"),
                                               "--output", str(tmp_path / "cli-metrics.json")])):
        result = subprocess.run([sys.executable, "-m", module, *arguments], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
    assert stable_hash(json.loads((tmp_path / "cli-thresholds.json").read_text())) == stable_hash(case["thresholds"])
    assert stable_hash(json.loads((tmp_path / "cli-metrics.json").read_text())) == stable_hash(case["metrics"])
    paths = {}
    for key, document in (("taxonomy", case["taxonomy"]), ("thresholds", case["thresholds"]),
                          ("metrics", case["metrics"]), ("metadata", {"versions": case["versions"], "release_version": "cli-smoke-v1"})):
        paths[key] = tmp_path / (key + ".json")
        paths[key].write_text(json.dumps(document), encoding="utf-8")
    command = [sys.executable, "-m", "ml.export", "--checkpoint", str(case["checkpoint"]),
               "--output-dir", str(tmp_path / "exported")]
    for key, path in paths.items():
        command.extend(["--" + key, str(path)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["test_only"] and (tmp_path / "exported/package.json").is_file()
