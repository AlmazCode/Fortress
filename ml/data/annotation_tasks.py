"""Portable local task bundles. Empty proposals remain unreviewed; no annotation UI is implied."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from ml.data.annotations import validate_actions, write_actions
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import _existing, artifact_transaction
from ml.data.objects import validate_objects
from ml.data.pts_index import validate_index
from ml.data.scenes import validate_scenes
from ml.data.splits import validate_splits
from ml.data.taxonomy import class_ids, load_taxonomy


def read_json(path: Path, max_bytes: int=64*1024**2) -> dict:
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>max_bytes:raise ValueError("unsafe/oversize JSON input")
    with path.open("rb") as source:data=source.read(max_bytes+1)
    if len(data)>max_bytes:raise ValueError("JSON input grew beyond limit")
    return json.loads(data.decode("utf-8-sig"))


def scene_context(manifest: dict, pairs: list[dict]) -> dict:
    validate_splits(manifest)
    videos={r["video_id"]:r for r in manifest["videos"]}
    result={}
    for pair in pairs:
        index,document=pair["index"],pair["scenes"]
        validate_index(index)
        validate_scenes(index,document)
        video=videos.get(index["video_id"])
        if (video is None or index["source_sha256"]!=video["sha256"] or index["split"]!=video["split"]
                or index["dataset_version"]!=manifest["dataset_version"] or index["split_version"]!=manifest["split_version"]):
            raise ValueError("task index does not match current manifest/split")
        for scene in document["scenes"]:
            if scene["scene_id"] in result:raise ValueError("duplicate scene context")
            result[scene["scene_id"]]={**copy.deepcopy(scene),"width":index["width"],"height":index["height"],
                "source_pts":[r["source_pts"] for r in index["frames"][scene["start_ordinal"]:scene["end_ordinal"]]],
                "index_sha256":index["index_sha256"]}
    return result


def prepare_tasks(destination: Path, *, manifest: dict, pairs: list[dict], frame_directories: list[Path],
                  object_taxonomy: dict, action_taxonomy: dict, annotation_version: str,
                  max_bytes: int=512*1024**2) -> dict:
    if not isinstance(annotation_version,str) or not annotation_version.strip():
        raise ValueError("annotation version required")
    contexts=scene_context(manifest,pairs)
    for scene in contexts.values():scene["frame_sources"]={}
    originals=all(r["provenance"]["kind"]=="original" for r in manifest["videos"])
    provenance={"kind":"original" if originals else "synthetic","source_id":manifest["dataset_version"],"sha256":stable_hash(manifest)}
    actions={"actions_version":"actions-v1","dataset_version":manifest["dataset_version"],
             "annotation_version":annotation_version,"taxonomy_version":action_taxonomy["version"],
             "records":[],"provenance":provenance}
    objects={"objects_version":"objects-v1","dataset_version":manifest["dataset_version"],
             "annotation_version":annotation_version,"taxonomy_version":object_taxonomy["version"],"frames":[]}
    sources=[]
    for directory in frame_directories:
        report=read_json(Path(directory)/"artifacts.json")
        report=_existing(Path(directory),report["cache_key"])
        if report["data"]["config"]["kind"]!="frames-v1":raise ValueError("task input must be PNG frame extraction")
        for frame in report["data"]["frames"]:
            scene=contexts.get(frame["scene_id"])
            if scene is None or scene["index_sha256"]!=report["data"]["index_sha256"]:
                raise ValueError("task frame/index/scene mismatch")
            artifact={k:copy.deepcopy(frame[k]) for k in ("path","sha256","width","height","transform")}
            objects["frames"].append({"frame_id":frame["frame_id"],"video_id":frame["video_id"],
                "scene_id":frame["scene_id"],"split":frame["split"],"source_sha256":frame["source_sha256"],
                "source_time":copy.deepcopy(frame["time"]),"width":frame["transform"]["original_width"],
                "height":frame["transform"]["original_height"],"artifact":artifact,
                "taxonomy_version":object_taxonomy["version"],"provenance":copy.deepcopy(frame["provenance"]),
                "frame_review":{"status":"unreviewed","reviewer":None,"human_approved":False,"complete":False,"classes_reviewed":[]},
                "objects":[]})
            sources.append((Path(directory)/frame["path"],frame["path"],frame["sha256"],frame["size_bytes"]))
    for frame in objects["frames"]:
        contexts[frame["scene_id"]]["frame_sources"][frame["frame_id"]]={
            "source_time":copy.deepcopy(frame["source_time"]),"source_sha256":frame["source_sha256"],
            "artifact":copy.deepcopy(frame["artifact"]),"width":frame["width"],"height":frame["height"]}
    validate_objects(objects,taxonomy=object_taxonomy,manifest=manifest,scenes=contexts)
    validate_actions(actions,manifest=manifest,taxonomy=action_taxonomy,scenes=contexts)
    tasks={"task_version":"annotation-tasks-v1","dataset_version":manifest["dataset_version"],
           "annotation_version":annotation_version,"objects_version":object_taxonomy["version"],
           "actions_version":action_taxonomy["version"],"source_manifest_sha256":stable_hash(manifest),
           "scene_context":contexts,"tasks":[
               *[{"kind":"object_frame","frame_id":f["frame_id"],"status":"unreviewed","classes":list(class_ids(object_taxonomy))}
                 for f in objects["frames"]],
               *[{"kind":"temporal_scene","scene_id":key,"status":"unreviewed","start_sec":scene["start_sec"],
                  "end_sec":scene["end_sec"],"classes":list(class_ids(action_taxonomy,include_states=True))}
                 for key,scene in sorted(contexts.items())]],
           "annotation_ui":"not_verified","training_ready":False}
    key=stable_hash({"tasks":tasks,"objects":objects,"actions":actions})
    def build(staging,register):
        for path,relative,expected,size in sources:
            with path.open("rb") as incoming:payload=incoming.read(size+1)
            if len(payload)!=size:raise ValueError("task source image size changed")
            entry=register(relative,payload)
            if entry["sha256"]!=expected:raise ValueError("task source image hash changed")
        for name,doc in (("objects.json",objects),("actions.json",actions),("tasks.json",tasks)):
            register(name,json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False).encode("utf-8")+b"\n")
        return {"task_count":len(tasks["tasks"]),"frame_count":len(objects["frames"]),
                "training_ready":False,"annotation_ui":"not_verified"}
    return artifact_transaction(destination,key,build,max_bytes=max_bytes,min_free_bytes=64*1024**2)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--index",type=Path,required=True)
    parser.add_argument("--scenes",type=Path,required=True)
    parser.add_argument("--frames",type=Path,required=True)
    parser.add_argument("--object-taxonomy",type=Path,default=Path("ml/config/object_taxonomy.draft.json"))
    parser.add_argument("--action-taxonomy",type=Path,default=Path("ml/config/action_taxonomy.draft.json"))
    parser.add_argument("--annotation-version",required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        payload=read_json(args.manifest)
        manifest=payload.get("manifest",payload)
        report=prepare_tasks(args.output_dir,manifest=manifest,
            pairs=[{"index":read_json(args.index),"scenes":read_json(args.scenes)}],frame_directories=[args.frames],
            object_taxonomy=load_taxonomy(args.object_taxonomy),action_taxonomy=load_taxonomy(args.action_taxonomy),
            annotation_version=args.annotation_version)
    except (OSError,ValueError,TypeError,KeyError) as exc:parser.error(str(exc))
    print(json.dumps(report["data"]))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
