import json
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import zipfile

import av
import numpy as np
import pytest
import yaml

from contracts.python_ports import validate_contract
from ml.data_cli import data_report, extract_dataset
from ml.data.annotation_tasks import read_json
from ml.data.taxonomy import load_taxonomy

ROOT=Path(__file__).resolve().parents[2]


def run(*args,expected=0):
    process=subprocess.run([sys.executable,"-m","ml.data_cli",*map(str,args)],cwd=ROOT,
                           capture_output=True,text=True,timeout=45)
    assert process.returncode==expected,(process.stdout,process.stderr)
    return process


def synthetic_sources(root):
    root.mkdir()
    sources=[]
    snapshots={}
    for n in range(4):
        path=root/f"source-{n}.mkv"
        with av.open(str(path),"w") as container:
            stream=container.add_stream("ffv1",rate=10)
            stream.width,stream.height,stream.pix_fmt=32,24,"yuv420p"
            stream.time_base=Fraction(1,10)
            stream.codec_context.time_base=Fraction(1,10)
            for i,point in enumerate((20,21,24,25)):
                image=np.random.default_rng(n*100+i).integers(0,256,(24,32,3),dtype=np.uint8)
                frame=av.VideoFrame.from_ndarray(image,format="rgb24")
                frame.pts,frame.time_base=point,Fraction(1,10)
                for packet in stream.encode(frame):container.mux(packet)
            for packet in stream.encode():container.mux(packet)
        snapshots[path]=(path.read_bytes(),path.stat().st_mtime_ns)
        sources.append({"path":path.name,"source_id":f"synthetic-{n}","group_id":f"synthetic-group-{n}",
                        "kind":"synthetic","rights":"confirmed"})
    return sources,snapshots


def test_unified_real_cli_pipeline_keeps_provenance_and_closed_real_training_gate(tmp_path):
    source=tmp_path/"originals"
    sources,before=synthetic_sources(source)
    config=tmp_path/"data.yaml"
    config.write_text(yaml.safe_dump({"source_root":str(source),"dataset_version":"unified-tiny-synthetic-v1",
                                     "sources":sources}),encoding="utf-8")
    imported=tmp_path/"import.json"
    run("import","--config",config,"--output",imported)
    manifest=read_json(imported)["manifest"]
    final_id=manifest["videos"][-1]["video_id"]
    split=tmp_path/"split.json"
    run("split","--input",imported,"--output",split,"--seed",17,"--final-video-id",final_id)
    assigned=read_json(split)["manifest"]
    video=next(r for r in assigned["videos"] if r["split"]=="train")
    extracted=tmp_path/"extracted"
    args=("extract","--manifest",split,"--source-root",source,"--video-id",video["video_id"],
          "--cut-sec",.26,"--crop",2,4,30,22,"--output-dir",extracted)
    run(*args)
    marker=(extracted/"artifacts.json").read_bytes()
    run(*args)
    assert (extracted/"artifacts.json").read_bytes()==marker
    index=read_json(extracted/"index.json")
    assert index["origin_pts"]==2000 and index["vfr"] is True
    tasks=tmp_path/"tasks"
    run("tasks","--manifest",split,"--index",extracted/"index.json","--scenes",extracted/"scenes.json",
        "--frames",extracted/"frames","--annotation-version","unified-labels-v1","--output-dir",tasks)
    context=tasks/"tasks.json"
    common=("--manifest",split,"--context",context)
    exchange=tmp_path/"coco"
    run("annotation-export",*common,"--objects",tasks/"objects.json","--format","coco","--output-dir",exchange)
    objects=tmp_path/"objects-roundtrip.json"
    run("annotation-import",*common,"--input",exchange/"coco.json","--sidecar",exchange/"sidecar.json",
        "--format","coco","--output",objects)
    assert read_json(objects)==read_json(tasks/"objects.json")
    for format in ("jsonl","csv"):
        path=tmp_path/("actions."+format)
        run("annotation-export",*common,"--actions",tasks/"actions.json","--format",format,"--output",path)
        actions=tmp_path/("actions-"+format+".json")
        run("annotation-import",*common,"--input",path,"--format",format,"--output",actions)
        assert read_json(actions)==read_json(tasks/"actions.json")
    qa_args=(*common,"--objects",objects,"--actions",actions,"--source-root",source,"--asset-root",tasks)
    run("validate",*qa_args)
    run("validate",*qa_args,"--require-data-ready",expected=1)
    report=tmp_path/"readiness.json"
    run("report",*qa_args,"--output",report)
    document=read_json(report)
    validate_contract("dataset_readiness",document["contract"])
    assert document["tools_ready"] is True and document["validation_passed"] is True
    assert document["data_missing"] is True and document["annotation_missing"] is True
    assert document["data_ready"] is False and document["training_ready"] is False
    assert document["qa"]["sources_verified"] is True and document["qa"]["assets_verified"] is True
    assert document["qa"]["annotation_records"]==0 and document["qa"]["unknown_rate"] is None
    assert all((p.read_bytes(),p.stat().st_mtime_ns)==snapshot for p,snapshot in before.items())
    # The unified dispatcher retains the D3 regression protection on re-split.
    repeated=tmp_path/"repeated.json"
    run("split","--input",split,"--output",repeated,"--seed",99)
    assert next(r for r in read_json(repeated)["manifest"]["videos"] if r["video_id"]==final_id)["split"]=="independent_test"
    # Parent extraction completion hashes every nested image/clip, not only index/scenes.
    first_png=next((extracted/"frames").glob("*.png"))
    first_png.write_bytes(b"corrupt")
    run(*args,expected=2)


def test_unified_inventory_real_cpu_and_safe_archive_dispatch(tmp_path):
    source=tmp_path/"originals"
    sources,before=synthetic_sources(source)
    inventory=tmp_path/"inventory.json"
    run("inventory","--project-root",ROOT,"--data-root",source,"--self-test","--output",inventory)
    report=read_json(inventory)
    assert report["self_test"]["feature_shape"]==[1,576] and report["self_test"]["status"]=="passed"
    assert report["readiness"]["training_ready"] is False
    archive=tmp_path/"data.zip"
    with zipfile.ZipFile(archive,"w") as output:output.writestr("nested/data.txt",b"source bytes")
    run("unpack","--input",archive,"--output-dir",tmp_path/"unpacked")
    assert (tmp_path/"unpacked/nested/data.txt").read_bytes()==b"source bytes"
    with zipfile.ZipFile(tmp_path/"escape.zip","w") as output:output.writestr("../escaped",b"bad")
    run("unpack","--input",tmp_path/"escape.zip","--output-dir",tmp_path/"rejected",expected=2)
    assert not (tmp_path/"rejected").exists()
    assert all((p.read_bytes(),p.stat().st_mtime_ns)==snapshot for p,snapshot in before.items())


def test_empty_manifest_report_and_extraction_budget_fail_without_published_output(tmp_path):
    source=tmp_path/"empty"
    source.mkdir()
    config=tmp_path/"empty.yaml"
    config.write_text(yaml.safe_dump({"source_root":str(source),"dataset_version":"empty-synthetic-v1","sources":[]}))
    imported=tmp_path/"empty.json"
    run("import","--config",config,"--output",imported)
    output=tmp_path/"empty-report.json"
    run("report","--manifest",imported,"--output",output)
    report=read_json(output)
    assert report["tools_ready"] is True and report["data_missing"] is True and report["training_ready"] is False
    validate_contract("dataset_readiness",report["contract"])
    from test_annotations import sample_documents
    data=sample_documents(tmp_path)
    with pytest.raises((ValueError,OSError)):
        extract_dataset(data["manifest"],tmp_path,data["index"]["video_id"],tmp_path/"small",max_bytes=100)
    assert not (tmp_path/"small").exists()
    assert not list(tmp_path.glob(".fortress-extract-*"))


def test_invalid_annotations_remain_present_but_unverified(tmp_path):
    from test_annotations import sample_documents
    data=sample_documents(tmp_path)
    report=data_report(manifest=data["manifest"],source_audit={},objects={},actions=None,
        contexts=data["contexts"],object_taxonomy=data["object_taxonomy"],action_taxonomy=data["action_taxonomy"])
    assert report["validation_passed"] is False and report["annotation_files_present"] is True
    assert report["annotation_missing"] is None and report["data_ready"] is False


def test_observed_readiness_snapshot_is_valid_and_explicitly_synthetic_not_ready():
    report=read_json(ROOT/"docs/model/DATA_READINESS.json")
    validate_contract("dataset_readiness",report["contract"])
    assert report["tools_ready"] is True and report["validation_passed"] is True
    assert report["contract"]["provenance"]["kind"]=="synthetic"
    assert report["data_ready"] is False and report["training_ready"] is False
