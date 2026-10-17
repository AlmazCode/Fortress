"""Class masks on original PTS and overlap aggregation without crossing scenes/splits."""
from __future__ import annotations

import copy
import math

import numpy as np

from ml.data.annotations import reviewed
from ml.data.taxonomy import annotation_decision
from ml.data.scenes import temporal_windows


def labelled_windows(index: dict, scenes: dict, actions: dict, classes: list[str], **options) -> list[dict]:
    if not classes or len(classes)!=len(set(classes)):
        raise ValueError("nonempty unique ordered output classes required")
    for row in actions["records"]:
        if not isinstance(row["known_mask"],bool) or not isinstance(row["interval_complete"],bool):
            raise ValueError("explicit boolean label masks required")
        if (any(not isinstance(row[k],(int,float)) or not math.isfinite(row[k]) for k in ("start_sec","end_sec"))
                or not 0<=row["start_sec"]<row["end_sec"]):
            raise ValueError("invalid label interval")
        approved=reviewed(row)
        observed={"present":True,"absent_verified":False,"unknown":None,"unreviewed":None}.get(row["state"],"invalid")
        if observed=="invalid" or row["event_type"] not in classes:
            raise ValueError("unknown action label/class")
        expected=annotation_decision(observed,visibility=row["visibility"],reviewed=approved,
                                     interval_complete=row["interval_complete"])
        if row["review_status"]=="needs_review":expected=("unknown",False)
        if (row["state"],row["known_mask"])!=expected:
            raise ValueError("unreviewed/unknown labels cannot supervise a negative")
    windows=temporal_windows(index,scenes,**options)
    for window in windows:
        targets=[[0.0]*len(classes) for _ in window["samples"]]
        masks=[[False]*len(classes) for _ in window["samples"]]
        rows=[r for r in actions["records"] if r["video_id"]==window["video_id"] and r["scene_id"]==window["scene_id"]]
        if any(r["split"]!=window["split"] or r["source_sha256"]!=window["source_sha256"] for r in rows):
            raise ValueError("window/annotation source or partition mismatch")
        for n,sample in enumerate(window["samples"]):
            if sample is None or not sample["image_mask"]:continue
            time=sample["time"]["timestamp_sec"]
            for c,key in enumerate(classes):
                labels=[r for r in rows if r["event_type"]==key and r["known_mask"]
                        and r["start_sec"]<=time<r["end_sec"]]
                positives=any(r["state"]=="present" for r in labels)
                # An absent action of one actor does not establish global absence.
                negative=any(r["state"]=="absent_verified" and r["actor_id"] is None for r in labels)
                if positives and negative:raise ValueError("conflicting global positive/negative labels")
                if positives or negative:
                    targets[n][c]=float(positives)
                    masks[n][c]=True
        window.update(class_ids=list(classes),targets=targets,known_mask=masks,
                      source_width=index["width"],source_height=index["height"],source_rotation=index["rotation"],
                      source_path=index["path"])
    return windows


def sample_key(window: dict, sample: dict) -> tuple:
    if (sample["video_id"]!=window["video_id"] or sample["scene_id"]!=window["scene_id"]
            or sample["split"]!=window["split"] or not sample["image_mask"] or sample["time"] is None):
        raise ValueError("sample provenance/availability mismatch")
    return (window["video_id"],window["scene_id"],window["split"],sample["time"]["source_pts"])


def merge_scores(windows: list[dict], scores: list[np.ndarray], *, score_masks: list[np.ndarray]|None=None) -> list[dict]:
    if len(windows)!=len(scores) or (score_masks is not None and len(windows)!=len(score_masks)):
        raise ValueError("window/score batch mismatch")
    merged={}
    video_sources={}
    point_scenes={}
    classes=None
    for i,(window,values) in enumerate(zip(windows,scores)):
        source=(window["split"],window["source_sha256"])
        if window["video_id"] in video_sources and video_sources[window["video_id"]]!=source:
            raise ValueError("one video cannot cross source hashes or partitions")
        video_sources[window["video_id"]]=source
        values=np.asarray(values)
        if values.ndim!=2 or values.shape[0]!=len(window["samples"]):
            raise ValueError("score shape must be [T,C]")
        if not 1<=values.shape[1]<=256:raise ValueError("unsupported class count")
        if classes is None:classes=values.shape[1]
        if values.shape[1]!=classes:raise ValueError("class count changed across windows")
        mask=np.ones(values.shape,dtype=bool) if score_masks is None else np.asarray(score_masks[i])
        if mask.dtype!=np.bool_:raise ValueError("score masks must be explicit booleans")
        if mask.shape!=values.shape:raise ValueError("score mask shape mismatch")
        for n,sample in enumerate(window["samples"]):
            if sample is None or window["padding_mask"][n] or not window["image_mask"][n]:continue
            key=sample_key(window,sample)
            point=(key[0],key[3])
            if point in point_scenes and point_scenes[point]!=key[1]:
                raise ValueError("one source PTS cannot cross scenes")
            point_scenes[point]=key[1]
            valid=mask[n]
            if not np.isfinite(values[n][valid]).all():raise ValueError("non-finite observable score")
            if key not in merged:
                merged[key]={"video_id":key[0],"scene_id":key[1],"split":key[2],"source_sha256":window["source_sha256"],
                             "time":copy.deepcopy(sample["time"]),"sum":np.zeros(classes),"count":np.zeros(classes,dtype=np.int64)}
            row=merged[key]
            if row["time"]!=sample["time"] or row["source_sha256"]!=window["source_sha256"]:
                raise ValueError("same source key has incompatible timing/hash")
            row["sum"][valid]+=values[n][valid]
            row["count"][valid]+=1
    output=[]
    for key,row in sorted(merged.items()):
        known=row["count"]>0
        values=np.divide(row.pop("sum"),row["count"],out=np.zeros(classes),where=known)
        counts=row.pop("count")
        output.append({**row,"scores":[float(v) if flag else None for v,flag in zip(values,known)],
                       "score_mask":known.tolist(),"counts":counts.tolist()})
    return output
