"""Explicit scene cuts and time-grid samples; proposals never imply human review."""
from __future__ import annotations

import argparse
from bisect import bisect_left
from fractions import Fraction
import json
import math
from pathlib import Path

from ml.data.deduplicate import stable_hash
from ml.data.pts_index import time_mapping, validate_index


def define_scenes(index: dict, *, cuts_sec: list[float]=(), reviewer: str|None=None) -> dict:
    validate_index(index)
    if reviewer is not None and (not isinstance(reviewer,str) or not reviewer.strip()):
        raise ValueError("reviewer identity must be nonempty")
    times=[r["timestamp_sec"] for r in index["frames"]]
    requested=list(cuts_sec)
    if requested!=sorted(set(requested)) or any(not math.isfinite(c) or not 0<c<index["duration_sec"] for c in requested):
        raise ValueError("scene cuts must be finite, unique, sorted and inside the video")
    offsets=[0]
    cut_map=[]
    for cut in requested:
        offset=bisect_left(times,cut)
        if offset>=len(times) or offset<=offsets[-1]:
            raise ValueError("scene cut has no distinct decoded boundary")
        offsets.append(offset)
        cut_map.append({"requested_sec":cut,"decoded_sec":times[offset],"source_pts":index["frames"][offset]["source_pts"]})
    offsets.append(len(times))
    rows=[]
    for start,end in zip(offsets,offsets[1:]):
        start_sec=times[start]
        end_sec=times[end] if end<len(times) else index["duration_sec"]
        scene_id=index["video_id"]+":scene-"+stable_hash({"start":index["frames"][start]["source_pts"],"end":end_sec})[:16]
        rows.append({"scene_id":scene_id,"video_id":index["video_id"],"split":index["split"],
                     "start_sec":start_sec,"end_sec":end_sec,"start_ordinal":start,"end_ordinal":end,
                     "review_status":"reviewed" if reviewer and reviewer.strip() else "unreviewed",
                     "reviewer":reviewer,"source_sha256":index["source_sha256"]})
    result={"scenes_version":"explicit-cuts-v1","index_sha256":index["index_sha256"],
            "cuts":cut_map,"scenes":rows,"limitations":[] if reviewer else
            ["Scene boundaries not reviewed; no claim that unlisted cuts are absent."]}
    result["scenes_sha256"]=stable_hash(result)
    return result


def validate_scenes(index: dict, document: dict) -> None:
    validate_index(index)
    if (document.get("scenes_version")!="explicit-cuts-v1"
            or document.get("scenes_sha256")!=stable_hash({k:v for k,v in document.items() if k!="scenes_sha256"})
            or document["index_sha256"]!=index["index_sha256"]):
        raise ValueError("scene/index version or hash mismatch")
    previous=0
    scene_ids=set()
    for row in document["scenes"]:
        if row["scene_id"] in scene_ids:
            raise ValueError("duplicate scene ID")
        scene_ids.add(row["scene_id"])
        if row["review_status"] not in ("reviewed","unreviewed") or (row["review_status"]=="reviewed" and not row["reviewer"]):
            raise ValueError("invalid scene review")
        a,b=row["start_ordinal"],row["end_ordinal"]
        if (a!=previous or not a<b<=len(index["frames"]) or row["video_id"]!=index["video_id"]
                or row["split"]!=index["split"] or row["source_sha256"]!=index["source_sha256"]
                or row["start_sec"]!=index["frames"][a]["timestamp_sec"]):
            raise ValueError("scene bounds/source/partition mismatch")
        expected=index["frames"][b]["timestamp_sec"] if b<len(index["frames"]) else index["duration_sec"]
        if row["end_sec"]!=expected:
            raise ValueError("scene end is not a decoded boundary")
        previous=b
    if previous!=len(index["frames"]):
        raise ValueError("scene coverage incomplete")


def sample_scenes(index: dict, document: dict, *, rate: float=2.0,
                  max_gap_sec: float|None=None, max_samples: int=100000) -> list[dict]:
    validate_scenes(index,document)
    if not math.isfinite(rate) or not 0<rate<=120 or max_samples<=0:
        raise ValueError("invalid sampling rate/budget")
    gap=1/(2*rate) if max_gap_sec is None else max_gap_sec
    if not math.isfinite(gap) or gap<0:
        raise ValueError("invalid sample gap")
    samples=[]
    for scene in document["scenes"]:
        frames=index["frames"][scene["start_ordinal"]:scene["end_ordinal"]]
        times=[r["timestamp_sec"] for r in frames]
        count=math.ceil((scene["end_sec"]-scene["start_sec"])*rate-1e-9)
        if len(samples)+count>max_samples:
            raise ValueError("sample count budget")
        for n in range(count):
            target=scene["start_sec"]+float(Fraction(n)/Fraction(str(rate)))
            offset=bisect_left(times,target)
            choices=[i for i in (offset-1,offset) if 0<=i<len(frames)]
            selected=min(choices,key=lambda i:(abs(times[i]-target),i))
            frame=frames[selected]
            available=abs(frame["timestamp_sec"]-target)<=gap+1e-9
            samples.append({"scene_id":scene["scene_id"],"video_id":index["video_id"],"split":index["split"],
                            "sample_in_scene":n,"target_sec":target,"image_mask":available,
                            "known_mask":False,"time":time_mapping(index,frame["source_pts"]) if available else None,
                            "source_ordinal":frame["ordinal"] if available else None,
                            "reason":None if available else "no_source_frame_within_gap"})
    return samples


def temporal_windows(index: dict, document: dict, *, rate: float=2.0, size: int=32, stride: int=16,
                     max_gap_sec: float|None=None, max_samples: int=100000) -> list[dict]:
    if not isinstance(size,int) or not isinstance(stride,int) or not 1<=stride<=size<=1024:
        raise ValueError("invalid window/stride")
    samples=sample_scenes(index,document,rate=rate,max_gap_sec=max_gap_sec,max_samples=max_samples)
    result=[]
    for scene in document["scenes"]:
        rows=[row for row in samples if row["scene_id"]==scene["scene_id"]]
        start=0
        while start<len(rows):
            valid=rows[start:start+size]
            slots=valid+[None]*(size-len(valid))
            actual=[r["time"]["timestamp_sec"] for r in valid if r["time"] is not None]
            start_sec=scene["start_sec"]+start/rate
            result.append({"window_id":"window-"+stable_hash({"index":index["index_sha256"],"scene":scene["scene_id"],
                             "rate":rate,"size":size,"stride":stride,"gap":max_gap_sec,"start":start})[:24],
                           "video_id":index["video_id"],"scene_id":scene["scene_id"],"split":scene["split"],
                           "source_sha256":index["source_sha256"],"start_sec":start_sec,
                           "end_sec":min(start_sec+size/rate,scene["end_sec"]),
                           "grid_interval_complete":start_sec+size/rate<=scene["end_sec"]+1e-9,
                           "grid_coverage_sec":size/rate,"grid_first_last_span_sec":(size-1)/rate,
                           "actual_first_last_span_sec":max(actual)-min(actual) if actual else None,
                           "rate":rate,"samples":slots,"padding_mask":[r is None for r in slots],
                           "image_mask":[r is not None and r["image_mask"] for r in slots],
                           "known_mask":[False]*size})
            if start+size>=len(rows):
                break
            start+=stride
    return result


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index",required=True,type=Path)
    parser.add_argument("--cut-sec",type=float,action="append",default=[])
    parser.add_argument("--reviewer")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        index=json.loads(args.index.read_text(encoding="utf-8-sig"))
        document=define_scenes(index,cuts_sec=args.cut_sec,reviewer=args.reviewer)
        encoded=json.dumps(document,ensure_ascii=False,indent=2,allow_nan=False)
        with args.output.open("x",encoding="utf-8") as output:output.write(encoded+"\n")
    except (OSError,ValueError,TypeError,KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({"scenes":len(document["scenes"]),"reviewed":bool(args.reviewer)}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
