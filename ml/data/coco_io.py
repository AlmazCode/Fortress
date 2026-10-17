"""COCO bbox exchange with a required canonical metadata sidecar."""
from __future__ import annotations

import copy
import math

from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import box_to_original
from ml.data.objects import original_box_to_artifact, validate_objects
from ml.data.taxonomy import class_ids


def export_coco(document: dict, taxonomy: dict) -> tuple[dict,dict]:
    validate_objects(document,taxonomy=taxonomy)
    categories=[{"id":n+1,"name":key} for n,key in enumerate(class_ids(taxonomy))]
    by_class={row["name"]:row["id"] for row in categories}
    images,annotations,links=[],[],{}
    for image_id,frame in enumerate(document["frames"],1):
        artifact=frame["artifact"]
        images.append({"id":image_id,"file_name":artifact["path"],"width":artifact["width"],"height":artifact["height"]})
        for item in frame["objects"]:
            box=original_box_to_artifact(item["bbox_xyxy"],artifact["transform"])
            identity=len(annotations)+1
            annotations.append({"id":identity,"image_id":image_id,"category_id":by_class[item["class_id"]],
                                "bbox":[box[0],box[1],box[2]-box[0],box[3]-box[1]],
                                "area":(box[2]-box[0])*(box[3]-box[1]),"iscrowd":0})
            links[str(identity)]={"frame_id":frame["frame_id"],"object_id":item["object_id"]}
    coco={"info":{"description":"Fortress bbox exchange; canonical/unknown metadata in required sidecar",
                  "version":document["annotation_version"]},"images":images,"categories":categories,"annotations":annotations}
    sidecar={"sidecar_version":"coco-v1","canonical":copy.deepcopy(document),"links":links,
             "images":copy.deepcopy(images),"categories":copy.deepcopy(categories),
             "baseline_coco_sha256":stable_hash(coco)}
    sidecar["sidecar_sha256"]=stable_hash(sidecar)
    return coco,sidecar


def import_coco(coco: dict, sidecar: dict, taxonomy: dict, *, annotation_version: str|None=None,
                annotator: str="local-coco-import") -> dict:
    if (sidecar.get("sidecar_version")!="coco-v1"
            or sidecar.get("sidecar_sha256")!=stable_hash({k:v for k,v in sidecar.items() if k!="sidecar_sha256"})):
        raise ValueError("COCO metadata sidecar missing/corrupt")
    original=sidecar["canonical"]
    validate_objects(original,taxonomy=taxonomy)
    for table in ("images","categories"):
        ids=[row["id"] for row in coco[table]]
        if any(type(key) is not int or key<=0 for key in ids) or len(ids)!=len(set(ids)):
            raise ValueError("invalid/duplicate COCO image/category ID")
    if coco["images"]!=sidecar["images"] or coco["categories"]!=sidecar["categories"]:
        raise ValueError("COCO image/category IDs or source geometry changed")
    changed=stable_hash(coco)!=sidecar["baseline_coco_sha256"]
    if changed and (not annotation_version or annotation_version==original["annotation_version"]):
        raise ValueError("changed labels require a new annotation version")
    result=copy.deepcopy(original)
    if annotation_version:result["annotation_version"]=annotation_version
    images={row["id"]:frame for row,frame in zip(sidecar["images"],result["frames"])}
    classes={row["id"]:row["name"] for row in sidecar["categories"]}
    prior={item["object_id"]:item for frame in original["frames"] for item in frame["objects"]}
    for frame in result["frames"]:frame["objects"]=[]
    seen=set()
    for row in coco["annotations"]:
        identity=row["id"]
        if type(identity) is not int or identity<=0 or identity in seen:
            raise ValueError("invalid/duplicate COCO annotation ID")
        seen.add(identity)
        if type(row["image_id"]) is not int or type(row["category_id"]) is not int or row["image_id"] not in images or row["category_id"] not in classes:
            raise ValueError("unknown COCO image/category ID")
        frame=images[row["image_id"]]
        bbox=row["bbox"]
        if (not isinstance(bbox,list) or len(bbox)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in bbox)
                or bbox[2]<=0 or bbox[3]<=0 or isinstance(row.get("area"),bool) or not isinstance(row.get("area"),(int,float))
                or not math.isclose(row["area"],bbox[2]*bbox[3],rel_tol=1e-6,abs_tol=1e-6)
                or row.get("iscrowd",0)!=0):
            raise ValueError("invalid COCO bbox/area or unsupported crowd")
        box=box_to_original([bbox[0],bbox[1],bbox[0]+bbox[2],bbox[1]+bbox[3]],frame["artifact"]["transform"])
        link=sidecar["links"].get(str(identity))
        item=copy.deepcopy(prior[link["object_id"]]) if link else {
            "object_id":"object-"+stable_hash({"frame":frame["frame_id"],"coco_id":identity})[:24],
            "visibility":"unknown","occluded":False,"truncated":False,"track_id":None,"actor_id":None,
            "annotator":annotator,"reviewer":None,"review_status":"unreviewed","human_approved":False,
            "label_origin":"imported","proposal_id":None}
        if link and link["frame_id"]!=frame["frame_id"]:
            raise ValueError("COCO annotation moved to another source image")
        label=classes[row["category_id"]]
        item_changed=not link or item["bbox_xyxy"]!=box or item["class_id"]!=label
        if item_changed:
            item.update(review_status="unreviewed",reviewer=None,human_approved=False,label_origin="imported",annotator=annotator)
            frame["frame_review"]={"status":"unreviewed","reviewer":None,"human_approved":False,
                                   "complete":False,"classes_reviewed":[]}
        item.update(class_id=label,bbox_xyxy=box)
        extras={k:v for k,v in row.items() if k not in ("id","image_id","category_id","bbox","area","iscrowd")}
        if extras:item["coco_extra"]=copy.deepcopy(extras)
        frame["objects"].append(item)
    if changed:
        result.setdefault("history",[]).append({"previous_annotation_version":original["annotation_version"],
                    "previous_sha256":stable_hash(original),"change":"COCO import; additions/edits/deletions are unreviewed"})
        # Deletions also invalidate complete-frame negatives.
        for before,after in zip(original["frames"],result["frames"]):
            if {r["object_id"] for r in before["objects"]}!={r["object_id"] for r in after["objects"]}:
                after["frame_review"]={"status":"unreviewed","reviewer":None,"human_approved":False,
                                       "complete":False,"classes_reviewed":[]}
    validate_objects(result,taxonomy=taxonomy)
    return result
