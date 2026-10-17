"""Re-encode annotation clips from decoded frames; preserve original PTS in sidecars."""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import shutil

import av
import numpy as np
from PIL import __version__ as pillow_version

from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import artifact_transaction, display_transform, transformed_image
from ml.data.manifest import local_source, source_hash
from ml.data.pts_index import iter_indexed_frames, time_mapping, validate_index
from ml.data.scenes import temporal_windows, validate_scenes


class BoundedFile:
    """Bound AVIO writes before disk consumption, including header seek rewrites."""
    def __init__(self, path: Path, limit: int, min_free: int):
        self.file=path.open("x+b")
        self.limit,self.min_free,self.parent=limit,min_free,path.parent

    def write(self,data):
        if self.file.tell()+len(data)>self.limit or shutil.disk_usage(self.parent).free<self.min_free+len(data):
            raise OSError("clip byte/free-disk limit")
        return self.file.write(data)

    def seek(self,offset,whence=0):
        point=self.file.seek(offset,whence)
        if not 0<=point<=self.limit:
            raise OSError("clip seek outside byte budget")
        return point

    def tell(self):return self.file.tell()
    def flush(self):return self.file.flush()
    def writable(self):return True
    def readable(self):return False
    def seekable(self):return True
    def close(self):return self.file.close()


def verify_clip(path: Path, *, expected_times: list[float], width: int, height: int) -> list[dict]:
    if not expected_times:
        raise ValueError("empty clip cannot be verified")
    rows=[]
    with av.open(str(path),format="matroska",options={"protocol_whitelist":"file","err_detect":"explode"}) as container:
        if len(container.streams.video)!=1 or container.streams.audio:
            raise ValueError("clip stream mismatch")
        stream=container.streams.video[0]
        stream.codec_context.thread_count=1
        for frame in container.decode(stream):
            if len(rows)>=len(expected_times) or (frame.width,frame.height)!=(width,height) or frame.pts is None:
                raise ValueError("clip geometry/frame count/PTS mismatch")
            actual=float(frame.pts*frame.time_base)
            if abs(actual-expected_times[len(rows)])>.0011:
                raise ValueError("encoded clip boundary/time mismatch")
            rows.append({"encoded_pts":frame.pts,"encoded_time_base":{"num":frame.time_base.numerator,"den":frame.time_base.denominator},
                         "encoded_timestamp_sec":actual})
    if len(rows)!=len(expected_times):
        raise ValueError("clip incomplete")
    return rows


def export_clips(root: Path, index: dict, scenes: dict, destination: Path, *, rate: float=2,
                 size: int=32, stride: int=16, max_clips: int=100, max_encoded_frames: int=200000,
                 max_decode_work_frames: int=2000000, max_bytes: int=1024**3,
                 min_free_bytes: int=64*1024**2) -> dict:
    validate_index(index)
    validate_scenes(index,scenes)
    source=local_source(Path(root).resolve(strict=True),index["path"])
    if source_hash(source,index["limits"]["max_source_bytes"])!=index["source_sha256"]:
        raise ValueError("source hash changed")
    windows=temporal_windows(index,scenes,rate=rate,size=size,stride=stride)
    if len(windows)>max_clips or len(windows)*len(index["frames"])>max_decode_work_frames:
        raise ValueError("clip/decode-work count limit")
    selections={}
    for window in windows:
        selections[window["window_id"]]=[row for row in index["frames"]
            if window["start_sec"]-1e-9<=row["timestamp_sec"]<window["end_sec"]-1e-9]
    if sum(map(len,selections.values()))>max_encoded_frames:
        raise ValueError("encoded frame count limit")
    transform=display_transform(index)
    config={"kind":"clips-v1","index":index["index_sha256"],"scenes":scenes["scenes_sha256"],
            "rate":rate,"size":size,"stride":stride,"codec":"ffv1","pixel_format":"bgr0",
            "container":"matroska","bitexact":True,"av":av.__version__,"pillow":pillow_version,
            "transform":transform,"encoded_timing_tolerance_sec":.0011}
    key=stable_hash(config)

    def build(staging,register):
        clips=[]
        used=0
        for window in windows:
            selected=selections[window["window_id"]]
            if not selected:
                clips.append({"window":window,"status":"no_frames","reason":"no_decoded_pts_in_interval"})
                continue
            clip_id="clip-"+stable_hash({"config":key,"window":window["window_id"]})[:24]
            relative=clip_id+".mkv"
            path=staging/relative
            wanted={row["ordinal"] for row in selected}
            relative_times=[row["timestamp_sec"]-selected[0]["timestamp_sec"] for row in selected]
            duration_by_pts={}
            for i,row in enumerate(selected):
                end=selected[i+1]["timestamp_sec"] if i+1<len(selected) else window["end_sec"]
                duration_by_pts[round(relative_times[i]*1e6)]=max(1,round((end-row["timestamp_sec"])*1e6))
            handle=BoundedFile(path,max_bytes-used,min_free_bytes)
            written=0
            try:
                with av.open(handle,mode="w",format="matroska",options={"fflags":"+bitexact"}) as output:
                    stream=output.add_stream("ffv1",rate=Fraction(str(rate)))
                    stream.width,stream.height=transform["output_width"],transform["output_height"]
                    stream.pix_fmt="bgr0"
                    stream.time_base=Fraction(1,1000000)
                    stream.codec_context.time_base=Fraction(1,1000000)
                    stream.codec_context.thread_count=1
                    for row,frame in iter_indexed_frames(root,index):
                        if row["ordinal"] not in wanted:continue
                        image=transformed_image(frame.to_image(),transform)
                        encoded=av.VideoFrame.from_ndarray(np.asarray(image),format="rgb24")
                        encoded.pts=round((row["timestamp_sec"]-selected[0]["timestamp_sec"])*1e6)
                        encoded.time_base=Fraction(1,1000000)
                        for packet in stream.encode(encoded):
                            packet.duration=duration_by_pts.get(packet.pts,1)
                            output.mux(packet)
                        written+=1
                    for packet in stream.encode():
                        packet.duration=duration_by_pts.get(packet.pts,1)
                        output.mux(packet)
            finally:
                handle.close()
            if written!=len(selected):
                raise ValueError("clip source count mismatch")
            decoded=verify_clip(path,expected_times=relative_times,width=stream.width,height=stream.height)
            mapping=[{"source_time":time_mapping(index,row["source_pts"]),**encoded}
                     for row,encoded in zip(selected,decoded)]
            entry=register(relative)
            used+=entry["size_bytes"]
            clips.append({"clip_id":clip_id,"window":window,"status":"encoded_verified",
                          "requested_start_sec":window["start_sec"],"requested_end_sec":window["end_sec"],
                          "first_decoded_source_sec":selected[0]["timestamp_sec"],
                          "last_decoded_source_sec":selected[-1]["timestamp_sec"],"frame_count":len(selected),
                          "source_sha256":index["source_sha256"],"transform":transform,"mapping":mapping,
                          "provenance":index["provenance"],**entry})
        return {"config":config,"dataset_version":index["dataset_version"],"split_version":index["split_version"],
                "clips":clips,"training_ready":False,"limitations":[
                    "Re-encoded video timing is quantized by Matroska; original PTS remain exact in mapping.",
                    "No stream-copy/keyframe seek is used; requested and decoded boundaries are recorded separately.",
                    "Window image/known/padding masks are separate; unreviewed observations remain unknown.",
                    "Scene boundaries require human review; clips do not establish labelled temporal data."]}
    return artifact_transaction(destination,key,build,max_bytes=max_bytes,min_free_bytes=min_free_bytes)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index",required=True,type=Path)
    parser.add_argument("--scenes",required=True,type=Path)
    parser.add_argument("--source-root",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--rate",type=float,default=2)
    parser.add_argument("--size",type=int,default=32)
    parser.add_argument("--stride",type=int,default=16)
    parser.add_argument("--max-bytes",type=int,default=1024**3)
    args=parser.parse_args(argv)
    try:
        index=json.loads(args.index.read_text(encoding="utf-8-sig"))
        scenes=json.loads(args.scenes.read_text(encoding="utf-8-sig"))
        report=export_clips(args.source_root,index,scenes,args.output_dir,rate=args.rate,size=args.size,
                            stride=args.stride,max_bytes=args.max_bytes)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({"clips":len(report["data"]["clips"]),"bytes":report["total_bytes"],"training_ready":False}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
