"""Annotation QA: measured coverage and honest readiness, never model accuracy."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image

from ml.data.annotations import validate_actions
from ml.data.deduplicate import stable_hash
from ml.data.manifest import local_source, source_hash
from ml.data.objects import object_known, validate_objects
from ml.data.splits import validate_splits
from ml.data.taxonomy import class_ids


def quality_report(*, manifest: dict, objects: dict, actions: dict, object_taxonomy: dict,
                   action_taxonomy: dict, scenes: dict, source_audit: dict|None=None,
                   asset_root: Path|None=None, source_root: Path|None=None,
                   readiness_evidence: dict|None=None, small_side_pixels: int=16) -> dict:
    errors=[]
    if type(small_side_pixels) is not int or small_side_pixels<=0:
        raise ValueError("positive small-object diagnostic size required")
    try:
        validate_splits(manifest)
        validate_objects(objects,taxonomy=object_taxonomy,manifest=manifest,scenes=scenes)
        entities={item[key] for frame in objects["frames"] for item in frame["objects"]
                  if object_known(item) for key in ("track_id","actor_id") if item[key] is not None}
        validate_actions(actions,manifest=manifest,taxonomy=action_taxonomy,scenes=scenes,known_entities=entities)
    except (ValueError,KeyError,TypeError) as exc:
        errors.append(str(exc))
    try:revision=stable_hash({"manifest":manifest,"objects":objects,"actions":actions,"scenes":scenes,
                             "object_taxonomy":object_taxonomy,"action_taxonomy":action_taxonomy})
    except (TypeError,ValueError):revision=None
    if errors:
        return {"qa_version":"annotations-qa-v1","dataset_revision":revision,"valid":False,"errors":errors,
                "object_annotations_ready":False,"temporal_annotations_ready":False,
                "data_ready":False,"training_ready":False,"limitations":["Invalid labels/split must be corrected."]}
    classes={key:Counter(records=0,reviewed_observable=0,unknown_or_unreviewed=0)
             for key in (*class_ids(object_taxonomy),*class_ids(action_taxonomy,include_states=True))}
    videos={row["video_id"]:Counter() for row in manifest["videos"]}
    keys=[]
    unknown=total=disagreement=known_objects=known_actions=0
    for frame in objects["frames"]:
        for item in frame["objects"]:
            good=object_known(item)
            known_objects+=good
            total+=1
            unknown+=not good
            disagreement+=item["review_status"]=="needs_review"
            box=item["bbox_xyxy"]
            counter=classes[item["class_id"]]
            counter.update({"records":1,"reviewed_observable":int(good),"unknown_or_unreviewed":int(not good),
                            "occluded":int(item["occluded"]),"truncated":int(item["truncated"]),
                            "small_box":int(min(box[2]-box[0],box[3]-box[1])<small_side_pixels)})
            videos[frame["video_id"]]["object_records"]+=1
            keys.append(("object",frame["video_id"],frame["source_time"]["source_pts"],item["class_id"],tuple(box),item["track_id"]))
    for row in actions["records"]:
        good=row["known_mask"]
        known_actions+=good
        total+=1
        unknown+=not good
        disagreement+=row["review_status"]=="needs_review"
        classes[row["event_type"]].update({"records":1,"reviewed_observable":int(good),
                                         "unknown_or_unreviewed":int(not good),row["state"]:1})
        videos[row["video_id"]]["action_records"]+=1
        keys.append(("action",row["video_id"],row["scene_id"],row["event_type"],row["start_sec"],row["end_sec"],row["state"],row["actor_id"]))
    duplicates=sum(count-1 for count in Counter(keys).values() if count>1)
    asset_verified=asset_root is not None
    if asset_root is not None:
        try:
            for frame in objects["frames"]:
                artifact=frame["artifact"]
                path=local_source(Path(asset_root).resolve(strict=True),artifact["path"])
                if source_hash(path,64*1024**2)!=artifact["sha256"]:raise ValueError("annotation image hash mismatch")
                with Image.open(path) as image:
                    image.load()
                    if image.size!=(artifact["width"],artifact["height"]):raise ValueError("annotation image geometry mismatch")
        except (OSError,ValueError) as exc:
            errors.append(str(exc))
            asset_verified=False
    source_verified=source_root is not None
    if source_root is not None:
        try:
            for video in manifest["videos"]:
                path=local_source(Path(source_root).resolve(strict=True),video["path"])
                if source_hash(path,2*1024**3)!=video["sha256"]:raise ValueError("original source hash mismatch")
        except (OSError,ValueError) as exc:
            errors.append(str(exc))
            source_verified=False
    active=[row for row in manifest["videos"] if row["split"]!="excluded"]
    audit={row.get("video_id"):row for row in (source_audit or {}).get("sources",[])}
    rights=bool(active) and all(audit.get(row["video_id"],{}).get("rights")=="confirmed"
                              and audit.get(row["video_id"],{}).get("sha256")==row["sha256"] for row in active)
    real=bool(active) and all(row["provenance"]["kind"]=="original" for row in active)
    evidence=readiness_evidence or {}
    independence=(evidence.get("manifest_sha256")==stable_hash(manifest) and
                  isinstance(evidence.get("reviewer"),str) and bool(evidence["reviewer"].strip()) and
                  evidence.get("final_viewpoint_independent") is True and evidence.get("previously_unseen") is True)
    partitions={row["split"] for row in active}
    complete_frames=bool(objects["frames"]) and all(f["frame_review"]["status"]=="reviewed"
        and f["frame_review"]["human_approved"] and f["frame_review"]["complete"]
        and set(f["frame_review"]["classes_reviewed"])==set(class_ids(object_taxonomy)) for f in objects["frames"])
    object_videos={frame["video_id"] for frame in objects["frames"]}
    temporal_videos={row["video_id"] for row in actions["records"] if row["known_mask"]}
    active_ids={row["video_id"] for row in active}
    scenes_reviewed=bool(scenes) and all(s["review_status"]=="reviewed" and s["reviewer"] for s in scenes.values())
    shared=(not errors and not duplicates and not disagreement and rights and real and source_verified
            and independence and {"train","dev_validation","independent_test"}<=partitions)
    object_ready=bool(shared and asset_verified and complete_frames and known_objects and active_ids<=object_videos
                      and object_taxonomy["status"]=="reviewed")
    temporal_ready=bool(shared and scenes_reviewed and known_actions and active_ids<=temporal_videos and action_taxonomy["status"]=="reviewed"
                        and all(row["review_status"]=="reviewed" for row in actions["records"]))
    by_case={f"C{n:02d}":{"annotation_records":0,"normative_status":"unknown"} for n in range(1,16)}
    for taxonomy in (object_taxonomy,action_taxonomy):
        for item in taxonomy["classes"]+taxonomy["states"]:
            for case in item["case_refs"]:by_case[case]["annotation_records"]+=classes[item["id"]]["records"]
    reasons=[]
    for ok,reason in ((real,"No all-original real dataset verified."),(rights,"Rights/source audit unconfirmed."),
        (source_verified,"Original file hashes not verified."),(asset_verified,"Image pixels/hashes not verified."),
        (independence,"Human evidence for independent, previously unseen final is absent."),
        (scenes_reviewed,"Scene review incomplete."),(object_ready,"Object annotation gate closed."),
        (temporal_ready,"Temporal annotation gate closed.")):
        if not ok:reasons.append(reason)
    if duplicates:reasons.append("Duplicate annotations require review.")
    if disagreement:reasons.append("Disagreements remain needs_review.")
    return {"qa_version":"annotations-qa-v1","dataset_revision":revision,"valid":not errors,"errors":errors,
            "per_class":{k:dict(v) for k,v in classes.items()},"per_case":by_case,
            "per_video":{k:dict(v) for k,v in videos.items()},"annotation_records":total,
            "unknown_rate":unknown/total if total else None,"disagreement_count":disagreement,
            "duplicate_annotation_count":duplicates,"small_side_diagnostic_pixels":small_side_pixels,
            "small_object_recognition_limit":"not measured","assets_verified":asset_verified,"sources_verified":source_verified,
            "rights_confirmed":rights,"real_data":real,"independence":"human_asserted" if independence else "unverified",
            "object_annotations_ready":object_ready,"temporal_annotations_ready":temporal_ready,
            "data_ready":temporal_ready,"training_ready":False,
            "training_gate_reason":"Data QA does not verify runtime, local encoder weights or authorize training.",
            "limitations":reasons}
