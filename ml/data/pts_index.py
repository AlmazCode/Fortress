"""Source PTS index. Only decoded timing is authoritative; nominal FPS is unused."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from fractions import Fraction
import json
from pathlib import Path
import time

from contracts.python_ports import validate_contract
from ml.data.deduplicate import stable_hash
from ml.data.manifest import (ProbeLimits, SourceRejected, local_source, open_local_video,
                              probe_video, source_hash)


def time_mapping(index: dict, point: int) -> dict:
    tb = index["time_base"]
    return {"source_pts":point, "origin_pts":index["origin_pts"], "time_base":dict(tb),
            "timestamp_sec":float((point-index["origin_pts"])*Fraction(tb["num"],tb["den"])),
            "rotation":index["rotation"], "valid":True}


def validate_index(index: dict) -> None:
    if index.get("index_version") != "pts-v1" or index.get("index_sha256") != stable_hash({k:v for k,v in index.items() if k!="index_sha256"}):
        raise ValueError("PTS index version/hash mismatch")
    rows = index["frames"]
    if not rows or index["split"] not in ("train","dev_validation","independent_test","excluded"):
        raise ValueError("empty index or unknown partition")
    tb = Fraction(index["time_base"]["num"],index["time_base"]["den"])
    if tb <= 0 or rows[0]["source_pts"] != index["origin_pts"]:
        raise ValueError("invalid PTS origin/time base")
    previous = None
    for ordinal, row in enumerate(rows):
        point = row["source_pts"]
        if row["ordinal"] != ordinal or not isinstance(point,int) or (previous is not None and point<=previous):
            raise ValueError("invalid source PTS order")
        expected = float((point-index["origin_pts"])*tb)
        if abs(expected-row["timestamp_sec"]) > 1e-9 or not 0<=expected<index["duration_sec"]:
            raise ValueError("PTS timestamp disagrees")
        previous = point


def iter_indexed_frames(root: Path, index: dict, *, limits: ProbeLimits | None = None):
    """Fully exhaust this iterator to verify all timing and the post-decode hash."""
    validate_index(index)
    limits = limits or ProbeLimits(**index["limits"])
    path = local_source(Path(root).resolve(strict=True),index["path"])
    if source_hash(path,limits.max_source_bytes) != index["source_sha256"]:
        raise SourceRejected("source_hash_changed")
    started, pixels, count = time.monotonic(), 0, 0
    tb = Fraction(index["time_base"]["num"],index["time_base"]["den"])
    with open_local_video(path) as container:
        if len(container.streams.video)!=1:
            raise SourceRejected("expected_one_video_stream")
        stream=container.streams.video[0]
        stream.codec_context.thread_count=1
        for frame in container.decode(stream):
            pixels += frame.width*frame.height
            if (count>=limits.max_frames or time.monotonic()-started>limits.max_decode_seconds
                    or frame.width*frame.height>limits.max_frame_pixels or pixels>limits.max_decoded_pixels):
                raise SourceRejected("decode_budget")
            if frame.pts is None or not frame.time_base or count>=len(index["frames"]):
                raise SourceRejected("missing_or_changed_pts")
            point=Fraction(frame.pts)*frame.time_base/tb
            if (point.denominator!=1 or int(point)!=index["frames"][count]["source_pts"]
                    or (frame.width,frame.height)!=(index["width"],index["height"])):
                raise SourceRejected("decode_disagrees_with_index")
            yield index["frames"][count],frame
            count+=1
    if count!=len(index["frames"]) or source_hash(path,limits.max_source_bytes)!=index["source_sha256"]:
        raise SourceRejected("source_or_frame_count_changed")


def build_index(root: Path, record: dict, *, dataset_version: str, split_version: str,
                limits: ProbeLimits=ProbeLimits()) -> dict:
    validate_contract("manifest",{"schema_version":"1.0","dataset_version":dataset_version,
                                 "split_version":split_version,"videos":[record]})
    path=local_source(Path(root).resolve(strict=True),record["path"])
    if source_hash(path,limits.max_source_bytes)!=record["sha256"]:
        raise SourceRejected("source_hash_changed")
    metadata,audit=probe_video(path,limits=limits)
    for field in ("width","height","rotation","source_start_pts","time_base","vfr"):
        if metadata[field]!=record[field]:
            raise SourceRejected("manifest_metadata_changed")
    if abs(metadata["duration_sec"]-record["duration_sec"])>1e-6:
        raise SourceRejected("manifest_duration_changed")
    tb=Fraction(record["time_base"]["num"],record["time_base"]["den"])
    rows=[]
    started,pixels=time.monotonic(),0
    with open_local_video(path) as container:
        stream=container.streams.video[0]
        stream.codec_context.thread_count=1
        for frame in container.decode(stream):
            pixels+=frame.width*frame.height
            if (len(rows)>=limits.max_frames or time.monotonic()-started>limits.max_decode_seconds
                    or pixels>limits.max_decoded_pixels or frame.width*frame.height>limits.max_frame_pixels):
                raise SourceRejected("decode_budget")
            if frame.pts is None or not frame.time_base:
                raise SourceRejected("missing_pts")
            point=Fraction(frame.pts)*frame.time_base/tb
            if point.denominator!=1:
                raise SourceRejected("incompatible_pts")
            point=int(point)
            rows.append({"ordinal":len(rows),"source_pts":point,
                         "timestamp_sec":float((point-record["source_start_pts"])*tb)})
    if (stable_hash([r["source_pts"] for r in rows])!=audit["pts_sha256"]
            or source_hash(path,limits.max_source_bytes)!=record["sha256"]):
        raise SourceRejected("source_changed_during_index")
    index={"index_version":"pts-v1","video_id":record["video_id"],"path":record["path"],
           "source_sha256":record["sha256"],"origin_pts":record["source_start_pts"],
           **{k:record[k] for k in ("time_base","width","height","rotation","duration_sec","vfr","split",
                                    "canonical_id","group_id","provenance")},
           "dataset_version":dataset_version,"split_version":split_version,
           "limits":asdict(limits),"frames":rows}
    index["index_sha256"]=stable_hash(index)
    validate_index(index)
    return index


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True,help="K manifest or import/split bundle")
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--video-id",required=True)
    parser.add_argument("--output",type=Path,required=True,help="new local index JSON")
    args=parser.parse_args(argv)
    try:
        document=json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        manifest=document.get("manifest",document)
        validate_contract("manifest",manifest)
        record=next(r for r in manifest["videos"] if r["video_id"]==args.video_id)
        result=build_index(args.source_root,record,dataset_version=manifest["dataset_version"],
                           split_version=manifest["split_version"])
        encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        with args.output.open("x",encoding="utf-8") as output:
            output.write(encoded+"\n")
    except (OSError,ValueError,TypeError,KeyError,StopIteration) as exc:
        parser.error(str(exc))
    print(json.dumps({"frames":len(result["frames"]),"origin_pts":result["origin_pts"],
                      "vfr":result["vfr"],"training_ready":False}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
