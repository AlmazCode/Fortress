"""Versioned local workspace crops and assistant observations; no new human gold."""
from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path

import numpy as np
from PIL import ImageEnhance
import torch

from ml import action_refinement as previous
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import display_transform, transformed_image
from ml.data.manifest import local_source, source_hash
from ml.data.pts_index import iter_indexed_frames
from ml.data.scenes import define_scenes, sample_scenes
from ml.models.encoder import FrozenEncoder, file_sha256
from ml.preprocessing import preprocess_image
from ml.video_baseline import atomic_json

VERSION = "workspace-focus-inputs-v1"
REVIEW_VERSION = "assistant-focus-review-v1"
TAXONOMY = previous.TAXONOMY + ("laptop_open", "laptop_screen_lit", "glass_door_open", "two_people_at_counter")
ROI = (0., .18, 1., .67)
BRIGHTNESS = (1., .85, 1.15)
RATE = 4.


def code_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def project_review(review):
    """Deterministic compatibility projection for the existing provenance validator."""
    document = copy.deepcopy(review)
    document["version"] = previous.VERSION
    document["taxonomy"] = list(previous.TAXONOMY)
    document["class_definitions"] = {k:document["class_definitions"][k] for k in previous.TAXONOMY}
    for video in document["videos"]:
        for obs in video["observations"]:
            obs["values"] = obs["values"][:len(previous.TAXONOMY)]
    return document


def exact_targets(observations, points, index):
    target = torch.full((len(points), len(TAXONOMY)), -1.)
    timing = {r["source_pts"]:r["timestamp_sec"] for r in index["frames"]}
    positions = {int(p):i for i,p in enumerate(points)}
    seen = set()
    for o in observations:
        pts, values = o["source_pts"], o["values"]
        if (type(pts) is not int or pts in seen or pts not in timing
                or abs(timing[pts]-o["timestamp_sec"]) > 1e-7
                or len(values) != len(TAXONOMY)
                or any(type(v) is not int or v not in (-1,0,1) for v in values)):
            raise ValueError("invalid focus observation")
        seen.add(pts)
        if pts in positions:
            target[positions[pts]] = torch.tensor(values)
    return target


def load_review(cache, overlay, compat):
    review, compatibility = read_json(overlay), read_json(compat)
    if (review["version"] != REVIEW_VERSION or review["taxonomy"] != list(TAXONOMY)
            or Path(overlay).resolve().parent != Path(compat).resolve().parent
            or project_review(review) != compatibility):
        raise ValueError("review/projection mismatch")
    document, rows, binding, stats = previous.load_inputs(cache, compat)
    development = {r["video_id"] for r in rows if r["split"] in ("train", "dev_validation")}
    if {v["video_id"] for v in review["videos"]} != development or len(review["videos"]) != len(development):
        raise ValueError("review must cover development only, exactly once")
    lookup = {v["video_id"]:v for v in review["videos"]}
    for row in rows:
        index = read_json(Path(document["prepared_dir"])/"indices"/(row["video_id"]+".json"))
        row["actions"] = exact_targets(lookup.get(row["video_id"],{}).get("observations",[]), row["source_pts"], index)
        stats[row["video_id"]]["action_known"] = int((row["actions"] >= 0).sum())
    binding.update(primary_overlay_sha256=file_sha256(overlay), compatibility_projection=stable_hash(compatibility))
    return document, rows, binding, stats, lookup


def roi_tensors(image, index, variants=True):
    displayed = transformed_image(image, display_transform(index))
    x0,y0,x1,y1 = ROI
    crop = displayed.crop((round(x0*displayed.width),round(y0*displayed.height),round(x1*displayed.width),round(y1*displayed.height)))
    return torch.stack([preprocess_image(ImageEnhance.Brightness(crop).enhance(b))["tensor"]
                        for b in (BRIGHTNESS if variants else (1.,))])


def encode_roi(source_root, index, encoder, device="cuda", variants=True):
    samples = sample_scenes(index, define_scenes(index), rate=RATE)
    selected = {s["time"]["source_pts"] for s in samples if s["image_mask"]}
    if len(selected) != len(samples) or not 1 <= len(samples) <= 720:
        raise ValueError("missing, duplicate or over-budget ROI source PTS")
    prefix, features, points, pending, pending_pts = [], [], [], [], []
    def flush():
        if not pending:
            return
        batch = torch.stack(pending).to(device)
        n, v = batch.shape[:2]
        values = encoder.features[:-2](batch.flatten(0,1))
        result = encoder.features[-2:](values[::v]).mean((-2,-1))
        prefix.extend(values.reshape(n,v,96,7,7).cpu().numpy())
        features.extend(result.cpu().numpy())
        points.extend(pending_pts)
        pending.clear(); pending_pts.clear()
    with torch.inference_mode():
        for timing, frame in iter_indexed_frames(Path(source_root), index):
            if timing["source_pts"] in selected:
                pending.append(roi_tensors(frame.to_image(),index,variants))
                pending_pts.append(timing["source_pts"])
                if len(pending) == 16:
                    flush()
        flush()
    if len(points) != len(selected):
        raise ValueError("missing decoded ROI frames")
    return {"features":np.asarray(features,dtype=np.float32), "prefix":np.asarray(prefix,dtype=np.float32),
            "source_pts":np.asarray(points,dtype=np.int64)}


def build(cache, output, weights, weights_sha256, device="cuda"):
    from ml.video_baseline import load_feature_cache
    document, rows = load_feature_cache(cache)
    if weights_sha256 != document["encoder"]["weights_sha256"]:
        raise ValueError("encoder differs from baseline")
    output = Path(output); output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4)
    encoder = FrozenEncoder(weights_path=weights, weights_sha256=weights_sha256).to(device).eval()
    prepared = Path(document["prepared_dir"])
    source_root = read_json(prepared/"readiness.json")["source_root"]
    entries = []
    for row in rows:
        if row["split"] == "independent_test":
            continue
        index = read_json(prepared/"indices"/(row["video_id"]+".json"))
        arrays = encode_roi(source_root,index,encoder,device)
        with np.load(local_source(Path(cache),row["path"]),allow_pickle=False) as old:
            if not set(old["source_pts"].tolist()) <= set(arrays["source_pts"].tolist()):
                raise ValueError("2fps is not exact subset of 4fps")
        path = output/(row["video_id"]+".npz")
        np.savez(path,**arrays)
        entries.append({k:row[k] for k in ("video_id","split","group_id","source_sha256","target")} |
                       {"path":path.name,"sha256":file_sha256(path),"frames":len(arrays["features"])})
        print(f'ROI cached {row["video_id"]}: {len(arrays["features"])} source frames',flush=True)
    marker = {"version":VERSION,"base_cache_sha256":stable_hash(document),"input_code_sha256":code_hash(),
              "roi":ROI,"rate":RATE,"brightness":BRIGHTNESS,"encoder_sha256":weights_sha256,
              "encoder_weights":str(Path(weights).resolve()),"entries":entries,"production_ready":False}
    atomic_json(output/"inputs.json",marker)
    return marker


def load(cache, overlay, compat, focus):
    document, rows, binding, stats, reviews = load_review(cache,overlay,compat)
    marker = read_json(Path(focus)/"inputs.json")
    development = {r["video_id"] for r in rows if r["split"] in ("train","dev_validation")}
    if (marker["version"] != VERSION or marker["base_cache_sha256"] != stable_hash(document)
            or marker["input_code_sha256"] != code_hash() or marker["roi"] != list(ROI)
            or marker["brightness"] != list(BRIGHTNESS) or marker["rate"] != RATE
            or {e["video_id"] for e in marker["entries"]} != development or len(marker["entries"]) != len(development)):
        raise ValueError("ROI input binding mismatch")
    by_id = {r["video_id"]:r for r in rows}
    for entry in marker["entries"]:
        row = by_id[entry["video_id"]]
        if any(row[k] != entry[k] for k in ("split","group_id","source_sha256","target")):
            raise ValueError("ROI label/source mismatch")
        path = local_source(Path(focus),entry["path"])
        if file_sha256(path) != entry["sha256"]:
            raise ValueError("ROI bytes changed")
        with np.load(path,allow_pickle=False) as a:
            if set(a.files) != {"features","prefix","source_pts"}:
                raise ValueError("unsupported ROI arrays")
            f,p,pts = a["features"],a["prefix"],a["source_pts"]
            n=entry["frames"]
            if (not 1<=n<=720 or f.shape!=(n,576) or p.shape!=(n,3,96,7,7) or pts.shape!=(n,)
                    or f.dtype!=np.float32 or p.dtype!=np.float32 or pts.dtype!=np.int64
                    or not np.isfinite(f).all() or not np.isfinite(p).all() or not np.all(np.diff(pts)>0)):
                raise ValueError("invalid ROI numeric arrays")
            index = read_json(Path(document["prepared_dir"])/"indices"/(row["video_id"]+".json"))
            expected = [s["time"]["source_pts"] for s in sample_scenes(index,define_scenes(index),rate=RATE)]
            if pts.tolist()!=expected:
                raise ValueError("ROI PTS lineage changed")
            positions = {int(v):i for i,v in enumerate(pts)}
            indices = torch.tensor([positions[int(v)] for v in row["source_pts"]])
            obj = torch.full((n,len(previous.OBJECT_IDS)),-1.)
            obj[indices] = row["objects"]
            row.update(roi_features=torch.from_numpy(f.copy()),prefix=torch.from_numpy(p.copy()),roi_pts=pts.copy(),
                       roi_actions=exact_targets(reviews[row["video_id"]]["observations"],pts,index),roi_objects=obj,roi2_indices=indices)
    binding["focus_inputs_sha256"] = stable_hash(marker)
    return document, rows, binding, stats, marker


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("cache","output","weights"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--weights-sha256",required=True)
    a=p.parse_args()
    build(a.cache,a.output,a.weights,a.weights_sha256)
