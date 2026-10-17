"""Canonical interval annotations, explicit unknown masks, and local JSONL/CSV exchange."""
from __future__ import annotations

import copy
import csv
import io
import json
import math
from pathlib import Path

from contracts.python_ports import validate_contract
from ml.data.splits import validate_splits
from ml.data.taxonomy import annotation_decision, class_ids, validate_taxonomy


def nonempty(value) -> bool:
    return isinstance(value,str) and bool(value.strip())


def reviewed(item: dict) -> bool:
    status=item.get("review_status")
    if status not in ("reviewed","unreviewed","needs_review") or item.get("label_origin") not in ("manual","imported","pseudo"):
        raise ValueError("invalid review status/label origin")
    if not nonempty(item.get("annotator")) or not isinstance(item.get("human_approved"),bool):
        raise ValueError("annotator and explicit human approval required")
    if status=="reviewed":
        if not nonempty(item.get("reviewer")) or not item["human_approved"] or item["label_origin"]=="pseudo":
            raise ValueError("reviewed labels need human reviewer/approval; pseudo is not gold")
        return True
    if item["human_approved"] or item.get("reviewer") is not None:
        raise ValueError("unresolved review cannot claim human approval")
    return False


def validate_header(document: dict, *, version_key: str, expected: str, taxonomy: dict,
                    manifest: dict|None=None) -> None:
    validate_taxonomy(taxonomy)
    if (document.get(version_key)!=expected or document.get("taxonomy_version")!=taxonomy["version"]
            or not nonempty(document.get("dataset_version")) or not nonempty(document.get("annotation_version"))):
        raise ValueError("annotation/taxonomy version mismatch")
    if manifest is not None:
        validate_splits(manifest)
        if document["dataset_version"]!=manifest["dataset_version"]:
            raise ValueError("annotation dataset version mismatch")


def validate_reference(item: dict, manifest: dict, scenes: dict) -> dict:
    videos={r["video_id"]:r for r in manifest["videos"]}
    video=videos.get(item.get("video_id"))
    scene=scenes.get(item.get("scene_id"))
    if (video is None or scene is None or scene["video_id"]!=video["video_id"]
            or item.get("source_sha256")!=video["sha256"] or item.get("split")!=video["split"]
            or scene["source_sha256"]!=video["sha256"] or scene["split"]!=video["split"]):
        raise ValueError("annotation source/scene/hash/partition mismatch")
    return scene


def actions_contract(document: dict) -> dict:
    records=[]
    for row in document["records"]:
        checked=row["review_status"]=="reviewed"
        records.append({"video_id":row["video_id"],"scene_id":row["scene_id"],
                        "interval":{"start_sec":row["start_sec"],"end_sec":row["end_sec"],"scene_id":row["scene_id"]},
                        "class_id":row["event_type"],"state":row["state"],"visibility":row["visibility"],
                        "actor_id":row["actor_id"],"relations":copy.deepcopy(row["relations"]),
                        "review_status":"reviewed" if checked else "unreviewed",
                        "reviewer":row["reviewer"] if checked else None,"valid":row["known_mask"]})
    result={"schema_version":"1.0","annotation_version":document["annotation_version"],
            "dataset_version":document["dataset_version"],"taxonomy_version":document["taxonomy_version"],
            "records":records,"provenance":copy.deepcopy(document["provenance"])}
    validate_contract("annotations",result)
    return result


def validate_actions(document: dict, *, manifest: dict, taxonomy: dict, scenes: dict,
                     known_entities: set[str]=frozenset()) -> None:
    validate_header(document,version_key="actions_version",expected="actions-v1",taxonomy=taxonomy,manifest=manifest)
    allowed=set(class_ids(taxonomy,include_states=True))
    ids=set()
    known=[]
    for row in document["records"]:
        identity=row.get("annotation_id")
        if not nonempty(identity) or identity in ids:
            raise ValueError("missing/duplicate annotation ID")
        ids.add(identity)
        scene=validate_reference(row,manifest,scenes)
        if row.get("taxonomy_version")!=taxonomy["version"] or row.get("event_type") not in allowed:
            raise ValueError("unknown action/state taxonomy class")
        a,b=row.get("start_sec"),row.get("end_sec")
        if (any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (a,b))
                or not scene["start_sec"]<=a<b<=scene["end_sec"]):
            raise ValueError("action interval outside scene or empty")
        approved=reviewed(row)
        if not isinstance(row.get("interval_complete"),bool):
            raise ValueError("explicit interval completeness required")
        observed={"present":True,"absent_verified":False,"unknown":None,"unreviewed":None}.get(row.get("state"),"invalid")
        if observed=="invalid":
            raise ValueError("unknown label state")
        expected=annotation_decision(observed,visibility=row["visibility"],reviewed=approved,
                                     interval_complete=row["interval_complete"])
        if row["review_status"]=="needs_review":
            expected=("unknown",False)
        if (row["state"],row.get("known_mask"))!=expected or not isinstance(row.get("known_mask"),bool):
            raise ValueError("state/known mask violates visibility/review/completeness")
        actor=row.get("actor_id")
        if actor is not None and (not nonempty(actor) or actor not in known_entities):
            raise ValueError("actor identity has no verified entity link")
        for relation in row["relations"]:
            if relation.get("known") and (relation.get("subject_id") not in known_entities or relation.get("object_id") not in known_entities):
                raise ValueError("known relation endpoints are unverified")
        if row["known_mask"]:
            for prior in known:
                same=(row["scene_id"]==prior["scene_id"] and row["event_type"]==prior["event_type"]
                      and (row["actor_id"] is None or prior["actor_id"] is None or row["actor_id"]==prior["actor_id"]))
                if (same and row["state"]!=prior["state"]
                        and max(a,prior["start_sec"])<min(b,prior["end_sec"])):
                    raise ValueError("conflicting reviewed positive and negative intervals")
            known.append(row)
    actions_contract(document)


CSV_FIELDS=("annotation_id","video_id","scene_id","start_sec","end_sec","event_type")


def write_actions(document: dict, path: Path, *, format: str="jsonl", max_bytes: int=64*1024**2) -> None:
    header={k:v for k,v in document.items() if k!="records"}
    if format=="jsonl":
        text="\n".join(json.dumps(row,ensure_ascii=False,allow_nan=False) for row in
                       [{"record_type":"header","metadata":header}]+
                       [{"record_type":"annotation","record":r} for r in document["records"]])+"\n"
    elif format=="csv":
        stream=io.StringIO(newline="")
        writer=csv.DictWriter(stream,fieldnames=[*CSV_FIELDS,"extra_json"])
        writer.writeheader()
        writer.writerow({**{k:"" for k in CSV_FIELDS},"extra_json":json.dumps({"header":header},ensure_ascii=False,allow_nan=False)})
        for row in document["records"]:
            writer.writerow({**{k:row[k] for k in CSV_FIELDS},
                "extra_json":json.dumps({k:v for k,v in row.items() if k not in CSV_FIELDS},ensure_ascii=False,allow_nan=False)})
        text=stream.getvalue()
    else:
        raise ValueError("unsupported annotation format")
    if len(text.encode("utf-8"))>max_bytes:
        raise ValueError("annotation byte limit")
    with Path(path).open("x",encoding="utf-8",newline="") as output:output.write(text)


def read_actions(path: Path, *, format: str="jsonl", max_bytes: int=64*1024**2, max_records: int=100000) -> dict:
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>max_bytes:
        raise ValueError("unsafe/oversize annotation input")
    with path.open("rb") as incoming:data=incoming.read(max_bytes+1)
    if len(data)>max_bytes:raise ValueError("annotation input grew beyond limit")
    text=data.decode("utf-8-sig")
    if format=="jsonl":
        lines=text.splitlines()
        if not lines or len(lines)>max_records+1:
            raise ValueError("annotation count limit or missing header")
        first=json.loads(lines[0])
        if first.get("record_type")!="header":
            raise ValueError("canonical JSONL header required")
        document=first["metadata"]
        records=[]
        for line in lines[1:]:
            item=json.loads(line)
            if item.get("record_type")!="annotation":raise ValueError("unknown JSONL record")
            records.append(item["record"])
    elif format=="csv":
        reader=csv.DictReader(io.StringIO(text,newline=""))
        if reader.fieldnames!=[*CSV_FIELDS,"extra_json"]:
            raise ValueError("canonical interval CSV columns required")
        first=next(reader,None)
        if first is None or any(first[k] for k in CSV_FIELDS):
            raise ValueError("canonical CSV metadata row required")
        document=json.loads(first["extra_json"])["header"]
        records=[]
        for row in reader:
            if len(records)>=max_records:raise ValueError("annotation count limit")
            extra=json.loads(row["extra_json"])
            if set(extra)&set(CSV_FIELDS):raise ValueError("CSV metadata overrides core fields")
            records.append({**extra,**{k:float(row[k]) if k in ("start_sec","end_sec") else row[k] for k in CSV_FIELDS}})
    else:
        raise ValueError("unsupported annotation format")
    if "records" in document:raise ValueError("header must not contain records")
    return {**document,"records":records}
