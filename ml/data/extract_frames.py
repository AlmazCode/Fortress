"""Transactional PNG export and reversible corner-coordinate transforms."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import tempfile

from PIL import Image, __version__ as pillow_version
import av

from ml.data.deduplicate import stable_hash
from ml.data.manifest import local_source, source_hash
from ml.data.pts_index import iter_indexed_frames, time_mapping, validate_index
from ml.data.scenes import sample_scenes, validate_scenes


def display_transform(index: dict, crop: list[int]|None=None) -> dict:
    width,height=index["width"],index["height"]
    box=list(crop) if crop is not None else [0,0,width,height]
    if (len(box)!=4 or any(not isinstance(v,int) or isinstance(v,bool) for v in box)
            or not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height):
        raise ValueError("crop must be integer xyxy within original decoded coordinates")
    x,y,x2,y2=box
    w,h=x2-x,y2-y
    rotation=index["rotation"]
    matrices={0:[[1,0,x],[0,1,y],[0,0,1]],
              90:[[0,-1,x+w],[1,0,y],[0,0,1]],
              180:[[-1,0,x+w],[0,-1,y+h],[0,0,1]],
              270:[[0,1,x],[-1,0,y+h],[0,0,1]]}
    if rotation not in matrices:
        raise ValueError("unsupported rotation")
    return {"coordinate_convention":"pixel_edges_xyxy","crop_original":box,"rotation_ccw":rotation,
            "to_original":matrices[rotation],"output_width":h if rotation%180 else w,
            "output_height":w if rotation%180 else h,"original_width":width,"original_height":height}


def transformed_image(image: Image.Image, transform: dict) -> Image.Image:
    result=image.convert("RGB").crop(tuple(transform["crop_original"]))
    transposes={90:Image.Transpose.ROTATE_90,180:Image.Transpose.ROTATE_180,270:Image.Transpose.ROTATE_270}
    if transform["rotation_ccw"]:
        result=result.transpose(transposes[transform["rotation_ccw"]])
    return result


def box_to_original(box: list[float], transform: dict) -> list[float]:
    if (len(box)!=4 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in box)
            or not 0<=box[0]<box[2]<=transform["output_width"]
            or not 0<=box[1]<box[3]<=transform["output_height"]):
        raise ValueError("box outside artifact")
    matrix=transform["to_original"]
    points=[(matrix[0][0]*x+matrix[0][1]*y+matrix[0][2],
             matrix[1][0]*x+matrix[1][1]*y+matrix[1][2])
            for x,y in ((box[0],box[1]),(box[2],box[1]),(box[0],box[3]),(box[2],box[3]))]
    return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]


def _existing(destination: Path, key: str) -> dict:
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("artifact destination is not a normal directory")
    marker=destination/"artifacts.json"
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size>32*1024**2:
        raise ValueError("artifact completion marker missing/unsafe")
    report=json.loads(marker.read_text(encoding="utf-8"))
    if report.get("cache_key")!=key or report.get("metadata_sha256")!=stable_hash({k:v for k,v in report.items() if k!="metadata_sha256"}):
        raise ValueError("artifact key/metadata mismatch; choose a new output directory")
    paths=[]
    for entry in report["files"]:
        path=local_source(destination,entry["path"])
        if source_hash(path,entry["size_bytes"])!=entry["sha256"] or path.stat().st_size!=entry["size_bytes"]:
            raise ValueError("artifact bytes changed; choose a new output directory")
        paths.append(entry["path"])
    if len(paths)!=len(set(paths)):
        raise ValueError("duplicate artifact paths")
    return report


def artifact_transaction(destination: Path, key: str, builder, *, max_bytes: int, min_free_bytes: int) -> dict:
    destination=Path(destination)
    parent=destination.parent.resolve(strict=True)
    target=parent/destination.name
    if max_bytes<=0 or min_free_bytes<0 or destination.name in ("",".",".."):
        raise ValueError("invalid output limits/path")
    if target.exists() or target.is_symlink():
        existing=_existing(target,key)
        if existing["total_bytes"]+(target/"artifacts.json").stat().st_size>max_bytes:
            raise ValueError("existing artifacts exceed requested byte limit")
        return existing
    if shutil.disk_usage(parent).free<min_free_bytes:
        raise OSError("insufficient free disk before extraction")
    staging=Path(tempfile.mkdtemp(prefix=".fortress-extract-",dir=parent))
    files=[]
    total=0

    def register(relative: str, payload: bytes|None=None):
        nonlocal total
        if "/" in relative or "\\" in relative or relative in ("",".","..","artifacts.json"):
            raise ValueError("artifact filename must be a generated basename")
        path=staging/relative
        size=len(payload) if payload is not None else path.stat().st_size
        additional=size if payload is not None else 0
        if total+size>max_bytes or shutil.disk_usage(parent).free<min_free_bytes+additional:
            raise OSError("extraction byte/free-disk limit")
        if payload is not None:
            with path.open("xb") as output:output.write(payload)
        digest=source_hash(path,max_bytes)
        total+=size
        entry={"path":relative,"size_bytes":size,"sha256":digest}
        files.append(entry)
        return entry

    try:
        data=builder(staging,register)
        report={"artifact_version":"extraction-v1","cache_key":key,"files":files,
                "total_bytes":total,"data":data}
        report["metadata_sha256"]=stable_hash(report)
        encoded=json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False).encode("utf-8")+b"\n"
        if total+len(encoded)>max_bytes or shutil.disk_usage(parent).free<min_free_bytes+len(encoded):
            raise OSError("metadata byte/free-disk limit")
        (staging/"artifacts.json").write_bytes(encoded)
        if target.exists() or target.is_symlink():
            raise FileExistsError("output appeared during extraction")
        staging.rename(target)
        staging=None
        return report
    finally:
        if staging is not None:
            resolved=staging.resolve()
            if resolved.parent!=parent or not resolved.name.startswith(".fortress-extract-"):
                raise RuntimeError("unsafe extraction staging cleanup")
            shutil.rmtree(resolved)


def export_frames(root: Path, index: dict, scenes: dict, destination: Path, *, rate: float=2.0,
                  crop: list[int]|None=None, max_gap_sec: float|None=None, max_frames: int=5000,
                  max_bytes: int=512*1024**2, min_free_bytes: int=64*1024**2) -> dict:
    validate_index(index)
    validate_scenes(index,scenes)
    source=local_source(Path(root).resolve(strict=True),index["path"])
    if source_hash(source,index["limits"]["max_source_bytes"])!=index["source_sha256"]:
        raise ValueError("source hash changed")
    transform=display_transform(index,crop)
    samples=sample_scenes(index,scenes,rate=rate,max_gap_sec=max_gap_sec,max_samples=max_frames*4)
    wanted={(row["scene_id"],row["source_ordinal"]) for row in samples if row["image_mask"]}
    if len(wanted)>max_frames:
        raise ValueError("export frame count limit")
    config={"kind":"frames-v1","index":index["index_sha256"],"scenes":scenes["scenes_sha256"],
            "rate":rate,"gap":max_gap_sec,"transform":transform,"png_compression":6,
            "pillow":pillow_version,"av":av.__version__}
    key=stable_hash(config)

    def build(staging,register):
        frames=[]
        by_ordinal={}
        for scene_id,ordinal in wanted:
            by_ordinal.setdefault(ordinal,[]).append(scene_id)
        for row,frame in iter_indexed_frames(root,index):
            if row["ordinal"] not in by_ordinal:
                continue
            image=transformed_image(frame.to_image(),transform)
            output=io.BytesIO()
            image.save(output,format="PNG",compress_level=6)
            for scene_id in sorted(by_ordinal[row["ordinal"]]):
                frame_id="frame-"+stable_hash({"config":key,"scene":scene_id,"pts":row["source_pts"]})[:24]
                entry=register(frame_id+".png",output.getvalue())
                frames.append({"frame_id":frame_id,"video_id":index["video_id"],"scene_id":scene_id,
                               "split":index["split"],"source_sha256":index["source_sha256"],
                               "source_ordinal":row["ordinal"],"time":time_mapping(index,row["source_pts"]),
                               "width":image.width,"height":image.height,"transform":transform,
                               "provenance":index["provenance"],**entry})
        if len(frames)!=len(wanted):
            raise ValueError("decoded export frame count mismatch")
        return {"config":config,"index_sha256":index["index_sha256"],"frames":frames,"samples":samples,
                "dataset_version":index["dataset_version"],"split_version":index["split_version"],
                "training_ready":False,"limitations":["Unreviewed labels remain unknown.",
                    "Sampling rate does not guarantee visibility of fast transfers/small objects.",
                    "Crops are spatial evidence, not temporal sequences."]}
    return artifact_transaction(destination,key,build,max_bytes=max_bytes,min_free_bytes=min_free_bytes)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index",required=True,type=Path)
    parser.add_argument("--scenes",required=True,type=Path)
    parser.add_argument("--source-root",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--rate",type=float,default=2)
    parser.add_argument("--crop",nargs=4,type=int)
    parser.add_argument("--max-bytes",type=int,default=512*1024**2)
    args=parser.parse_args(argv)
    try:
        index=json.loads(args.index.read_text(encoding="utf-8-sig"))
        scenes=json.loads(args.scenes.read_text(encoding="utf-8-sig"))
        report=export_frames(args.source_root,index,scenes,args.output_dir,rate=args.rate,crop=args.crop,max_bytes=args.max_bytes)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({"frames":len(report["data"]["frames"]),"bytes":report["total_bytes"],"training_ready":False}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
