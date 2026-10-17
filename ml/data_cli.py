"""Unified offline data preparation. Outputs are local, versioned and non-overwriting."""
from __future__ import annotations

import argparse
import importlib
from importlib.metadata import version as package_version
import json
from pathlib import Path
import sys

from contracts.python_ports import validate_contract
from ml.data.annotation_tasks import read_json
from ml.data.annotations import read_actions, validate_actions, write_actions
from ml.data.coco_io import export_coco, import_coco
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import artifact_transaction, export_frames
from ml.data.extract_clips import export_clips
from ml.data.manifest import local_source, source_hash
from ml.data.objects import object_known, validate_objects
from ml.data.pts_index import build_index
from ml.data.quality import quality_report
from ml.data.safe_archive import extract_zip
from ml.data.scenes import define_scenes
from ml.data.splits import validate_splits
from ml.data.taxonomy import load_taxonomy

DELEGATES={"inventory":"ml.preflight","import":"ml.data.manifest","split":"ml.data.splits",
           "index":"ml.data.pts_index","scenes":"ml.data.scenes","frames":"ml.data.extract_frames",
           "clips":"ml.data.extract_clips","tasks":"ml.data.annotation_tasks","taxonomy":"ml.data.taxonomy"}


def write_json_new(path: Path, document: dict) -> None:
    data=json.dumps(document,ensure_ascii=False,indent=2,allow_nan=False)
    if len(data.encode("utf-8"))>64*1024**2:raise ValueError("JSON output exceeds 64 MiB")
    with Path(path).open("x",encoding="utf-8") as output:output.write(data+"\n")


def manifest_input(path: Path) -> tuple[dict|None,dict]:
    payload=read_json(path)
    return payload.get("manifest",payload),payload.get("audit",{})


def load_context(path: Path|None, manifest: dict) -> dict:
    if path is None:return {}
    document=read_json(path)
    if document.get("task_version")!="annotation-tasks-v1" or document["source_manifest_sha256"]!=stable_hash(manifest):
        raise ValueError("task context does not match current manifest")
    return document["scene_context"]


def extract_dataset(manifest: dict, source_root: Path, video_id: str, destination: Path, *,
                    cuts_sec: list[float]=(), reviewer: str|None=None, rate: float=2,
                    crop: list[int]|None=None, max_bytes: int=2*1024**3) -> dict:
    validate_splits(manifest)
    record=next((row for row in manifest["videos"] if row["video_id"]==video_id),None)
    if record is None:raise ValueError("unknown manifest video ID")
    source=local_source(Path(source_root).resolve(strict=True),record["path"])
    if source_hash(source,2*1024**3)!=record["sha256"]:raise ValueError("source hash changed")
    config={"pipeline":"data-extract-v1","manifest_sha256":stable_hash(manifest),"video_id":video_id,
            "cuts_sec":list(cuts_sec),"reviewer":reviewer,"rate":rate,"crop":crop,
            "runtime":{name:package_version(name) for name in ("av","Pillow")}}
    def build(staging,register):
        index=build_index(source_root,record,dataset_version=manifest["dataset_version"],split_version=manifest["split_version"])
        scenes=define_scenes(index,cuts_sec=cuts_sec,reviewer=reviewer)
        used=0
        for name,doc in (("index.json",index),("scenes.json",scenes)):
            used+=register(name,json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False).encode("utf-8")+b"\n")["size_bytes"]
        frames=export_frames(source_root,index,scenes,staging/"frames",rate=rate,crop=crop,max_bytes=max_bytes-used)
        for row in frames["files"]:
            used+=register("frames/"+row["path"])["size_bytes"]
        used+=register("frames/artifacts.json")["size_bytes"]
        clips=export_clips(source_root,index,scenes,staging/"clips",rate=rate,max_bytes=max_bytes-used)
        for row in clips["files"]:used+=register("clips/"+row["path"])["size_bytes"]
        used+=register("clips/artifacts.json")["size_bytes"]
        return {"config":config,"index":"index.json","scenes":"scenes.json","frames":"frames","clips":"clips",
                "frame_count":len(frames["data"]["frames"]),"clip_count":len(clips["data"]["clips"]),"training_ready":False}
    return artifact_transaction(destination,stable_hash(config),build,max_bytes=max_bytes,min_free_bytes=64*1024**2)


def data_report(*, manifest: dict|None, source_audit: dict, objects: dict|None, actions: dict|None,
                contexts: dict, object_taxonomy: dict, action_taxonomy: dict,
                asset_root: Path|None=None, source_root: Path|None=None, readiness_evidence: dict|None=None) -> dict:
    label_files_present=objects is not None or actions is not None
    if manifest is None:
        qa={"valid":False,"errors":[],"real_data":False,"annotation_records":0,"sources_verified":False,
            "assets_verified":False,"rights_confirmed":False,"object_annotations_ready":False,
            "temporal_annotations_ready":False,"data_ready":False,"training_ready":False,"dataset_revision":None,
            "limitations":["No valid source manifest; data_missing."]}
        version="missing"
        provenance={"kind":"synthetic","source_id":"missing-data-report","sha256":stable_hash({"manifest":None})}
    else:
        version=manifest["dataset_version"]
        provenance={"kind":"original" if all(r["provenance"]["kind"]=="original" for r in manifest["videos"]) else "synthetic",
                    "source_id":version,"sha256":stable_hash(manifest)}
        if objects is None:
            objects={"objects_version":"objects-v1","dataset_version":version,"annotation_version":"unreviewed-template-v1",
                     "taxonomy_version":object_taxonomy["version"],"frames":[]}
        if actions is None:
            actions={"actions_version":"actions-v1","dataset_version":version,"annotation_version":"unreviewed-template-v1",
                     "taxonomy_version":action_taxonomy["version"],"records":[],"provenance":provenance}
        qa=quality_report(manifest=manifest,objects=objects,actions=actions,object_taxonomy=object_taxonomy,
                          action_taxonomy=action_taxonomy,scenes=contexts,source_audit=source_audit,
                          asset_root=asset_root,source_root=source_root,readiness_evidence=readiness_evidence)
    checks=[{"name":"data_validation","status":"passed" if qa["valid"] else "failed",
             "detail":"Manifest/annotation/geometry/source validation; see QA errors."},
            {"name":"real_sources","status":"passed" if qa.get("real_data") and qa.get("sources_verified") else "failed",
             "detail":"Original sources and actual local SHA-256 are required; synthetic verifies code only."},
            {"name":"rights","status":"passed" if qa.get("rights_confirmed") else "unknown",
             "detail":"Source audit must explicitly confirm rights for active originals."},
            {"name":"reviewed_temporal_data","status":"passed" if qa.get("temporal_annotations_ready") else "failed",
             "detail":"Reviewed taxonomy/scenes/labels and independent final evidence required."}]
    ready=qa.get("data_ready",False) and all(c["status"]=="passed" for c in checks)
    contract={"schema_version":"1.0","dataset_version":version,"state":"ready" if ready else "blocked",
              "checks":checks,"limitations":[] if ready else qa["limitations"],"provenance":provenance}
    validate_contract("dataset_readiness",contract)
    return {"report_version":"data-readiness-v1","tools_ready":True,
            "tools_ready_scope":"Local data modules/taxonomies/schema loaded; dataset/runtime gates reported separately.",
            "validation_passed":qa["valid"],"data_missing":not bool(manifest and any(
                r["provenance"]["kind"]=="original" for r in manifest["videos"])),
            "annotation_files_present":label_files_present,
            "annotation_missing":not qa.get("annotation_records",0) if qa["valid"] else (None if label_files_present else True),
            "annotation_review":"unverified" if not qa.get("data_ready") else "human_asserted",
            "object_annotations_ready":qa.get("object_annotations_ready",False),
            "temporal_annotations_ready":qa.get("temporal_annotations_ready",False),"data_ready":bool(ready),
            "training_ready":False,"runtime_preflight":"separate command; not run by report",
            "qa":qa,"contract":contract}


def _common(parser):
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--context",type=Path,help="tasks.json from the matching annotation bundle")
    parser.add_argument("--objects",type=Path)
    parser.add_argument("--actions",type=Path)
    parser.add_argument("--object-taxonomy",type=Path,default=Path("ml/config/object_taxonomy.draft.json"))
    parser.add_argument("--action-taxonomy",type=Path,default=Path("ml/config/action_taxonomy.draft.json"))


def main(argv=None) -> int:
    argv=list(sys.argv[1:] if argv is None else argv)
    root=argparse.ArgumentParser(description=__doc__)
    custom=("unpack","extract","annotation-import","annotation-export","validate","report")
    root.add_argument("command",nargs="?",choices=[*DELEGATES,*custom])
    if not argv or argv[0] in ("-h","--help"):
        root.print_help()
        return 0
    command,*arguments=argv
    if command in DELEGATES:
        return importlib.import_module(DELEGATES[command]).main(arguments)
    if command not in custom:root.error("unknown data command")
    parser=argparse.ArgumentParser(prog=f"python -m ml.data_cli {command}")
    if command=="unpack":
        parser.add_argument("--input",type=Path,required=True)
        parser.add_argument("--output-dir",type=Path,required=True)
    elif command=="extract":
        parser.add_argument("--manifest",type=Path,required=True)
        parser.add_argument("--source-root",type=Path,required=True)
        parser.add_argument("--video-id",required=True)
        parser.add_argument("--output-dir",type=Path,required=True)
        parser.add_argument("--cut-sec",type=float,action="append",default=[])
        parser.add_argument("--reviewer")
        parser.add_argument("--rate",type=float,default=2)
        parser.add_argument("--crop",nargs=4,type=int)
        parser.add_argument("--max-bytes",type=int,default=2*1024**3)
    else:
        _common(parser)
        if command in ("annotation-import","annotation-export"):
            parser.add_argument("--format",choices=["coco","jsonl","csv"],required=True)
            parser.add_argument("--input",type=Path)
            parser.add_argument("--sidecar",type=Path)
            parser.add_argument("--annotation-version")
            parser.add_argument("--output",type=Path)
            parser.add_argument("--output-dir",type=Path)
        else:
            parser.add_argument("--source-root",type=Path)
            parser.add_argument("--asset-root",type=Path)
            parser.add_argument("--readiness-evidence",type=Path)
            parser.add_argument("--output",type=Path)
            parser.add_argument("--require-data-ready",action="store_true")
    args=parser.parse_args(arguments)
    try:
        if command=="unpack":
            result=extract_zip(args.input,args.output_dir)
            print(json.dumps({"entries":result["entries"],"bytes":result["size_bytes"],"executed":False}))
            return 0
        manifest,audit=manifest_input(args.manifest)
        if command=="extract":
            if manifest is None:raise ValueError("data_missing: no valid source manifest")
            result=extract_dataset(manifest,args.source_root,args.video_id,args.output_dir,cuts_sec=args.cut_sec,
                                   reviewer=args.reviewer,rate=args.rate,crop=args.crop,max_bytes=args.max_bytes)
            print(json.dumps(result["data"]))
            return 0
        ot,at=load_taxonomy(args.object_taxonomy),load_taxonomy(args.action_taxonomy)
        contexts=load_context(args.context,manifest) if manifest is not None else {}
        objects=read_json(args.objects) if args.objects else None
        actions=read_json(args.actions) if args.actions else None
        if command in ("validate","report"):
            result=data_report(manifest=manifest,source_audit=audit,objects=objects,actions=actions,contexts=contexts,
                               object_taxonomy=ot,action_taxonomy=at,source_root=args.source_root,asset_root=args.asset_root,
                               readiness_evidence=read_json(args.readiness_evidence) if args.readiness_evidence else None)
            if args.output:write_json_new(args.output,result)
            printed=result if command=="report" and not args.output else {k:result[k] for k in (
                "tools_ready","validation_passed","data_missing","annotation_missing","data_ready","training_ready")}
            print(json.dumps(printed,ensure_ascii=False))
            if command=="validate" and not result["validation_passed"]:return 1
            return 1 if args.require_data_ready and not result["data_ready"] else 0
        if manifest is None:raise ValueError("data_missing: annotation IO needs a valid source manifest")
        if objects is not None:validate_objects(objects,taxonomy=ot,manifest=manifest,scenes=contexts)
        entities={item[key] for frame in (objects or {}).get("frames",[]) for item in frame["objects"] if object_known(item)
                  for key in ("track_id","actor_id") if item[key] is not None}
        if command=="annotation-import":
            if args.input is None or args.output is None:raise ValueError("--input and --output required")
            if args.format=="coco":
                if args.sidecar is None:raise ValueError("COCO import requires --sidecar")
                result=import_coco(read_json(args.input),read_json(args.sidecar),ot,annotation_version=args.annotation_version)
                validate_objects(result,taxonomy=ot,manifest=manifest,scenes=contexts)
            else:
                result=read_actions(args.input,format=args.format)
                validate_actions(result,manifest=manifest,taxonomy=at,scenes=contexts,known_entities=entities)
            write_json_new(args.output,result)
        elif args.format=="coco":
            if objects is None or args.output_dir is None:raise ValueError("COCO export requires --objects and --output-dir")
            validate_objects(objects,taxonomy=ot,manifest=manifest,scenes=contexts)
            coco,sidecar=export_coco(objects,ot)
            def build(staging,register):
                for name,doc in (("coco.json",coco),("sidecar.json",sidecar)):
                    register(name,json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False).encode()+b"\n")
                return {"format":"coco","images":len(coco["images"]),"annotations":len(coco["annotations"])}
            artifact_transaction(args.output_dir,stable_hash({"coco":coco,"sidecar":sidecar}),build,
                                 max_bytes=64*1024**2,min_free_bytes=64*1024**2)
        else:
            if actions is None or args.output is None:raise ValueError("action export requires --actions and --output")
            validate_actions(actions,manifest=manifest,taxonomy=at,scenes=contexts,known_entities=entities)
            write_actions(actions,args.output,format=args.format)
        print(json.dumps({"format":args.format,"status":"validated_local_exchange","training_ready":False}))
        return 0
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        parser.error(str(exc))


if __name__=="__main__":
    raise SystemExit(main())
