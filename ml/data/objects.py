"""Object labels in original decoded coordinates; artifact exchange uses explicit transforms."""
from __future__ import annotations

import copy
import math

from contracts.python_ports import validate_contract
from ml.data.annotations import reviewed, nonempty, validate_header, validate_reference
from ml.data.extract_frames import box_to_original, display_transform
from ml.data.taxonomy import class_ids, VISIBILITY


def valid_box(box, width, height) -> None:
    if (not isinstance(box,list) or len(box)!=4
            or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in box)
            or not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height):
        raise ValueError("invalid/out-of-bounds original bbox_xyxy")


def original_box_to_artifact(box: list[float], transform: dict) -> list[float]:
    # D4 matrices are rigid quarter turns + translation; invert their 2x2 part.
    matrix=transform["to_original"]
    a,b,x=matrix[0]
    c,d,y=matrix[1]
    det=a*d-b*c
    if det not in (-1,1) or matrix[2]!=[0,0,1]:
        raise ValueError("unsupported artifact transform")
    points=[((d*(u-x)-b*(v-y))/det,(-c*(u-x)+a*(v-y))/det)
            for u,v in ((box[0],box[1]),(box[2],box[1]),(box[0],box[3]),(box[2],box[3]))]
    result=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
    valid_box(result,transform["output_width"],transform["output_height"])
    return result


def object_known(item: dict) -> bool:
    return reviewed(item) and item["visibility"] in ("visible","partial")


def validate_objects(document: dict, *, taxonomy: dict, manifest: dict|None=None, scenes: dict|None=None) -> None:
    validate_header(document,version_key="objects_version",expected="objects-v1",taxonomy=taxonomy,manifest=manifest)
    allowed=set(class_ids(taxonomy))
    frames,objects=set(),set()
    for frame in document["frames"]:
        frame_id=frame.get("frame_id")
        if not nonempty(frame_id) or frame_id in frames:
            raise ValueError("missing/duplicate frame ID")
        frames.add(frame_id)
        if frame.get("taxonomy_version")!=taxonomy["version"] or frame["width"]<=0 or frame["height"]<=0:
            raise ValueError("object frame taxonomy/geometry mismatch")
        time=frame["source_time"]
        artifact=frame["artifact"]
        relative=artifact["path"]
        if (not isinstance(relative,str) or not relative or relative.startswith("/") or "\\" in relative or ":" in relative
                or any(part in ("",".","..") for part in relative.split("/"))):
            raise ValueError("unsafe annotation artifact path")
        if frame["source_sha256"]!=frame["provenance"]["sha256"]:
            raise ValueError("object source provenance hash mismatch")
        transform=artifact["transform"]
        expected=display_transform({"width":frame["width"],"height":frame["height"],"rotation":time["rotation"]},
                                   transform["crop_original"])
        if (transform!=expected or transform["original_width"]!=frame["width"] or transform["original_height"]!=frame["height"]
                or (artifact["width"],artifact["height"])!=(transform["output_width"],transform["output_height"])
                or box_to_original([0,0,artifact["width"],artifact["height"]],transform)!=transform["crop_original"]):
            raise ValueError("artifact transform/geometry mismatch")
        if manifest is not None:
            if scenes is None:raise ValueError("scene context required")
            scene=validate_reference(frame,manifest,scenes)
            anchor=scene.get("frame_sources",{}).get(frame["frame_id"])
            actual={k:frame[k] for k in ("source_time","source_sha256","artifact","width","height")}
            if anchor!=actual:
                raise ValueError("object frame provenance differs from task anchor; regenerate legacy tasks")
            if (not scene["start_sec"]<=time["timestamp_sec"]<scene["end_sec"]
                    or time["source_pts"] not in scene["source_pts"]
                    or (frame["width"],frame["height"])!=(scene["width"],scene["height"])):
                raise ValueError("object frame PTS outside source scene")
        review=frame["frame_review"]
        if any(not isinstance(review.get(k),bool) for k in ("human_approved","complete")):
            raise ValueError("frame review booleans required")
        if review["status"] not in ("reviewed","unreviewed","needs_review"):
            raise ValueError("invalid frame review")
        if review["status"]=="reviewed":
            if not review["human_approved"] or not nonempty(review["reviewer"]) or not isinstance(review["complete"],bool):
                raise ValueError("frame review needs explicit human evidence")
        elif review["human_approved"] or review["complete"]:
            raise ValueError("unreviewed frame cannot claim complete gold")
        if not set(review["classes_reviewed"])<=allowed:
            raise ValueError("unknown reviewed object class")
        for item in frame["objects"]:
            if not nonempty(item.get("object_id")) or item["object_id"] in objects:
                raise ValueError("missing/duplicate object ID")
            objects.add(item["object_id"])
            if item.get("class_id") not in allowed:
                raise ValueError("unknown object class")
            valid_box(item["bbox_xyxy"],frame["width"],frame["height"])
            # COCO bbox must also be representable inside the actual image.
            original_box_to_artifact(item["bbox_xyxy"],transform)
            if item["visibility"] not in VISIBILITY or any(not isinstance(item[k],bool) for k in ("occluded","truncated")):
                raise ValueError("object visibility/flags invalid")
            if item["visibility"]=="visible" and item["occluded"]:
                raise ValueError("visible object cannot also be occluded")
            for identity in ("track_id","actor_id"):
                if item[identity] is not None and not nonempty(item[identity]):
                    raise ValueError("nullable identity must be a nonempty local reference")
            reviewed(item)
    objects_contract(document)


def objects_contract(document: dict) -> dict:
    # K/COCO view uses actual artifact dimensions; canonical source coordinates
    # and all identity/occlusion/review fields remain in the canonical sidecar.
    frames=[]
    for frame in document["frames"]:
        items=[]
        for item in frame["objects"]:
            box=original_box_to_artifact(item["bbox_xyxy"],frame["artifact"]["transform"])
            checked=item["review_status"]=="reviewed"
            items.append({"object_id":item["object_id"],"class_id":item["class_id"],
                          "bbox":[box[0],box[1],box[2]-box[0],box[3]-box[1]],"visibility":item["visibility"],
                          "review_status":"reviewed" if checked else "unreviewed",
                          "reviewer":item["reviewer"] if checked else None,"actor_id":item["actor_id"]})
        frames.append({"frame_id":frame["frame_id"],"video_id":frame["video_id"],"scene_id":frame["scene_id"],
                       "width":frame["artifact"]["width"],"height":frame["artifact"]["height"],
                       "sha256":frame["artifact"]["sha256"],"time":copy.deepcopy(frame["source_time"]),
                       "objects":items,"provenance":copy.deepcopy(frame["provenance"])})
    result={"schema_version":"1.0","dataset_version":document["dataset_version"],
            "taxonomy_version":document["taxonomy_version"],"frames":frames}
    validate_contract("objects",result)
    return result
