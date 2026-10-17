"""D1: read-only inventory, honest gates and an actual tiny CPU feature check."""
import hashlib
import json
from pathlib import Path

import pytest

from ml.preflight import (build_report, cpu_self_test, inspect_file, main,
                          material_inventory, material_kind, runtime_info, scan_root, sha256_file)

def test_inventory_records_original_bytes_without_mutation(tmp_path):
    video=tmp_path/"clip.MOV"
    video.write_bytes(b"not decoded in D1")
    before=video.stat().st_mtime_ns
    item=inspect_file(video, role="video", source="synthetic test")
    assert item["sha256"]==hashlib.sha256(b"not decoded in D1").hexdigest()
    assert item["kind"]=="video" and item["content_validation"]=="not_run"
    assert item["rights"]=="unknown" and item["review_status"]=="unverified"
    assert video.read_bytes()==b"not decoded in D1" and video.stat().st_mtime_ns==before
    assert inspect_file(tmp_path/"missing",role="appendix",source="test")["state"]=="missing"

def test_hash_and_scan_limits_fail_closed(tmp_path):
    (tmp_path/"a.bin").write_bytes(b"abcd")
    (tmp_path/"b.bin").write_bytes(b"efgh")
    with pytest.raises(ValueError, match="limit"):
        sha256_file(tmp_path/"a.bin",max_bytes=3)
    assert scan_root(tmp_path,role="test",max_files=1)["issues"]==["file_count_limit"]
    assert scan_root(tmp_path,role="test",max_bytes=3)["issues"]==["total_hash_byte_limit"]

def test_annotation_tooling_is_explicitly_excluded_not_counted_as_data(tmp_path):
    tooling=tmp_path/".annotation_env";tooling.mkdir()
    (tooling/"dependency.json").write_text("{}")
    (tmp_path/"events_to_review.csv").write_text("header")
    scan=scan_root(tmp_path,role="annotation_assets")
    assert scan["skipped_directories"]==[".annotation_env"]
    assert len(scan["files"])==1
    assert len(scan_root(tooling,role="explicit_tooling")["files"])==1

def test_images_metadata_and_weights_are_not_temporal_labels_or_release(tmp_path):
    media=tmp_path/"media";media.mkdir()
    for name in ("photo.jpg","events_to_review.csv","objects_coco_empty.json","best.pt"):
        (media/name).write_bytes(b"synthetic placeholder")
    inventory=material_inventory(tmp_path,data_roots=(media,))
    assert inventory["counts"]=={"model_weight":1,"annotation_or_metadata":2,"image":1}
    report=build_report(tmp_path,data_roots=(media,))
    assert report["readiness"]["data_missing"]
    assert report["readiness"]["training_ready"] is False
    assert report["readiness"]["annotation_review"]=="unverified"
    assert report["readiness"]["annotation_files_present"]
    assert report["readiness"]["annotation_missing"] is None
    assert "license_unknown" in report["readiness"]["reasons"]
    assert report["self_test"]["status"]=="not_run"

def test_restricted_rights_are_not_reported_as_unknown_or_training_ready(tmp_path):
    report=build_report(tmp_path,rights="restricted")
    assert report["readiness"]["license_state"]=="restricted"
    assert report["readiness"]["license_unknown"] is False
    assert "license_restricted" in report["readiness"]["reasons"]
    assert report["readiness"]["training_ready"] is False

def test_project_contracts_are_hashed_and_unknown_materials_stay_missing():
    root=Path(__file__).resolve().parents[2]
    inventory=material_inventory(root)
    contracts=[r for r in inventory["materials"] if r["role"]=="contract"]
    assert len(contracts)==6 and all(r["sha256"] for r in contracts)
    assert all(r["state"]=="available" for r in contracts)
    assert all(r["state"]=="missing" for r in inventory["materials"]
               if r["role"] in ("training_appendix","case_coverage_appendix"))

def test_cpu_self_test_uses_real_mobilenet_without_download(monkeypatch):
    import torch
    import torchvision
    called=[]
    original=torchvision.models.mobilenet_v3_small
    def builder(*,weights,**kwargs):
        assert weights is None
        called.append(weights)
        return original(weights=weights,**kwargs)
    monkeypatch.setattr(torchvision.models,"mobilenet_v3_small",builder)
    smoke=cpu_self_test()
    assert smoke["status"]=="passed" and smoke["feature_shape"]==[1,576]
    assert smoke["test_only"] and called==[None]

def test_missing_runtime_fails_self_test_honestly(monkeypatch):
    import ml.preflight as preflight
    def missing(name):
        raise ImportError("synthetic unavailable runtime")
    monkeypatch.setattr(preflight.importlib,"import_module",missing)
    assert cpu_self_test()["status"]=="failed"

def test_runtime_and_cli_report_are_observed_and_do_not_overwrite(tmp_path):
    runtime=runtime_info()
    assert runtime["python_3_11"] and runtime["packages"]["torch"]
    assert runtime["memory"]["total_ram_bytes"] is None or runtime["memory"]["total_ram_bytes"]>0
    output=tmp_path/"report.json"
    assert main(["--project-root",str(tmp_path),"--output",str(output)])==0
    report=json.loads(output.read_text(encoding="utf-8"))
    assert report["readiness"]["training_ready"] is False
    with pytest.raises(FileExistsError):
        main(["--project-root",str(tmp_path),"--output",str(output)])
