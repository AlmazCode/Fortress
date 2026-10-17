import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from ml.cache import CacheSpec, load_cache
from ml.cli import main, smoke_pipeline
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256
from ml.train import train
from ml.models import FrozenEncoder


def command(*arguments):
    result = subprocess.run([sys.executable, "-m", "ml.cli", *map(str, arguments)], capture_output=True,
                            text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    root = tmp_path_factory.mktemp("M-CLI") / "tiny"
    summary = command("smoke", "--output-dir", root)
    assert summary["optimizer_total_steps"] == 2 and summary["resumed"]
    assert summary["calibration_partition"] == "dev_validation" and summary["evaluation_partition"] == "independent_test"
    assert not summary["production_ready"] and not summary["data_ready"] and summary["verdict_metrics"] is None
    assert summary["timeline_coverage"] == "none" and summary["budget"]["passed"]
    return root


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_actual_cpu_cli_cache_train_resume_score_calibrate_evaluate_export_import_and_switch(tmp_path, pipeline):
    root = pipeline
    manifest = read(root / "manifest.json")["manifest"]
    train_id = next(row["video_id"] for row in manifest["videos"] if row["split"] == "train")
    index_path = next(path for path in root.glob("index-*.json") if read(path)["video_id"] == train_id)
    scene_path = root / index_path.name.replace("index-", "scenes-")
    class_args = [arg for key in read(root / "cache-train/cache.json")["spec"]["class_ids"] for arg in ("--class", key)]
    cache = tmp_path / "cache"
    command("cache", "--manifest", root / "manifest.json", "--source-root", root / "sources", "--tasks", root / "tasks/tasks.json",
            "--objects", root / "tasks/objects.json", "--actions", root / "artificial-actions.json", "--asset-root", root / "tasks",
            "--object-taxonomy", root / "object-taxonomy.json", "--action-taxonomy", root / "action-taxonomy.json",
            "--index", index_path, "--scenes", scene_path, "--partition", "train", "--test-only", "--output-dir", cache, *class_args)
    assert read(cache / "cache.json")["spec"] == read(root / "cache-train/cache.json")["spec"]
    config = Path(__file__).resolve().parents[2] / "ml/config/train.example.yaml"
    command("train", "--cache", cache, "--output-dir", tmp_path / "first", "--steps", "1", "--smoke", "--config", config)
    command("resume", "--cache", cache, "--output-dir", tmp_path / "resumed", "--steps", "2", "--smoke",
                "--resume", tmp_path / "first/checkpoint.pt", "--config", config)
    checkpoint = tmp_path / "resumed/checkpoint.pt"
    for partition, target in (("dev_validation", "dev"), ("independent_test", "final")):
        command("evaluate", "--cache", root / ("cache-" + partition), "--checkpoint", checkpoint,
                "--manifest", root / "manifest.json", "--output", tmp_path / (target + ".json"))
    command("thresholds", "--input", tmp_path / "dev.json", "--output", tmp_path / "thresholds.json")
    command("evaluate", "--input", tmp_path / "final.json", "--thresholds", tmp_path / "thresholds.json",
            "--output", tmp_path / "metrics.json")
    command("export", "--checkpoint", checkpoint, "--taxonomy", root / "action-taxonomy.json",
            "--thresholds", tmp_path / "thresholds.json", "--metrics", tmp_path / "metrics.json",
            "--metadata", root / "export-metadata.json", "--output-dir", tmp_path / "exported")
    command("import", "--package", tmp_path / "exported", "--output-dir", tmp_path / "imported", "--allow-test")
    pointer = tmp_path / "active.json"
    command("activate", "--package", tmp_path / "exported", "--pointer", pointer, "--allow-test")
    command("activate", "--package", tmp_path / "imported", "--pointer", pointer, "--allow-test")
    command("rollback", "--pointer", pointer, "--allow-test")
    assert read(pointer)["active"]["path"] == str((tmp_path / "exported").resolve())
    source = root / "sources" / manifest["videos"][0]["path"]
    result = command("infer", "--package", tmp_path / "imported", "--video", source, "--output", tmp_path / "timeline.json", "--allow-test")
    assert result["readiness"]["status"] == "not_ready" and result["result"]["coverage"] == "none"
    denied = subprocess.run([sys.executable, "-m", "ml.cli", "import", "--package", str(tmp_path / "exported"),
                             "--output-dir", str(tmp_path / "production-denied"), "--manifest-sha256",
                             file_sha256(tmp_path / "exported/package.json")], capture_output=True, text=True, timeout=60)
    assert denied.returncode == 1 and not (tmp_path / "production-denied").exists()


def test_bound_readiness_tampering_is_rejected_and_previous_smoke_generation_reuses(pipeline, tmp_path):
    root = tmp_path / "cache"
    shutil.copytree(pipeline / "cache-train", root)
    document = read(root / "cache.json")
    spec = CacheSpec.from_dict(document["spec"])
    assert not document["readiness_binding"]["report"]["data_ready"]
    document["readiness_binding"]["report"]["data_ready"] = True
    (root / "cache.json").write_text(json.dumps(document), encoding="utf-8")
    marker = read(root / "artifacts.json")
    for entry in marker["files"]:
        if entry["path"] == "cache.json":
            entry.update(sha256=file_sha256(root / "cache.json"), size_bytes=(root / "cache.json").stat().st_size)
    marker["total_bytes"] = sum(row["size_bytes"] for row in marker["files"])
    marker["metadata_sha256"] = stable_hash({k: v for k, v in marker.items() if k != "metadata_sha256"})
    (root / "artifacts.json").write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ValueError, match="binding"):
        load_cache(root, spec)
    original = (pipeline / "artifacts.json").read_bytes()
    assert smoke_pipeline(pipeline)["data"]["production_ready"] is False
    assert (pipeline / "artifacts.json").read_bytes() == original
    loaded = read(pipeline / "cache-train/cache.json")
    spec = CacheSpec.from_dict(loaded["spec"])
    with pytest.raises(ValueError, match="future training"):
        train(pipeline / "cache-train", tmp_path / "real-denied", spec=spec, encoder=FrozenEncoder(test_only=True),
              smoke=False, allow_real_training=True, readiness={"data_ready": True}, source_root=pipeline / "sources")


def test_all_command_help_and_resume_requires_previous_checkpoint(capsys):
    for name in ("data", "preflight", "cache", "train", "resume", "evaluate", "thresholds", "export", "import", "activate", "rollback", "infer", "smoke"):
        try:
            result = main([name, "--help"])
        except SystemExit as result:
            assert result.code == 0
        else:
            assert result == 0
    assert "--output-dir" in capsys.readouterr().out
    with pytest.raises(SystemExit) as result:
        main(["resume", "--cache", "unused"])
    assert result.value.code == 2
