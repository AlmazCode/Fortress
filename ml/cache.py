"""Provenance-addressed numeric feature caches. Pickle is never used for cache IO."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import math
from fractions import Fraction
from pathlib import Path
import re
import zipfile

import numpy as np
import torch

from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import _existing, artifact_transaction
from ml.data.manifest import local_source, source_hash
from ml.preprocessing import PreprocessConfig, preprocess_image
from ml.windows import sample_key


@dataclass(frozen=True)
class CacheSpec:
    source_sha256: str
    dataset_sha256: str
    split_sha256: str
    annotation_sha256: str
    taxonomy_sha256: str
    encoder_sha256: str
    preprocessing_sha256: str
    config_sha256: str
    windows_sha256: str
    class_ids: tuple[str,...]
    partition: str
    test_only: bool = True
    version: str = "feature-cache-v1"

    def __post_init__(self):
        if any(not isinstance(v,str) or re.fullmatch("[a-f0-9]{64}",v) is None
               for k,v in asdict(self).items() if k.endswith("_sha256")):
            raise ValueError("cache inputs require full SHA-256")
        if (self.version!="feature-cache-v1" or self.partition not in ("train","dev_validation","independent_test")
                or type(self.test_only) is not bool or not isinstance(self.class_ids,tuple) or not 1<=len(self.class_ids)<=256
                or len(self.class_ids)!=len(set(self.class_ids)) or any(not isinstance(c,str) or not c for c in self.class_ids)):
            raise ValueError("invalid cache version/partition/classes/provenance")

    def descriptor(self):return {**asdict(self),"class_ids":list(self.class_ids)}

    def key(self):return stable_hash(self.descriptor())

    @classmethod
    def from_dict(cls,value):return cls(**{**value,"class_ids":tuple(value["class_ids"])})


def encoder_fingerprint(encoder: torch.nn.Module, *, max_bytes: int=64*1024**2) -> str:
    if not isinstance(encoder,torch.nn.Module):raise ValueError("cache encoder must be an explicit torch module")
    state=encoder.state_dict()
    if not state:raise ValueError("encoder has no fingerprintable tensor state")
    digest=hashlib.sha256()
    total=0
    for name,tensor in sorted(state.items()):
        if not isinstance(tensor,torch.Tensor) or tensor.dtype not in (torch.float32,torch.int64,torch.int32,torch.bool):
            raise ValueError("unsupported encoder tensor dtype")
        total+=tensor.numel()*tensor.element_size()
        if total>max_bytes:raise ValueError("encoder byte budget")
        value=tensor.detach().cpu().contiguous()
        if value.is_floating_point() and not bool(torch.isfinite(value).all()):
            raise ValueError("non-finite encoder state")
        digest.update(stable_hash({"name":name,"shape":list(value.shape),"dtype":str(value.dtype)}).encode("ascii"))
        digest.update(value.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def _validate_windows(windows: list[dict], spec: CacheSpec) -> set[tuple]:
    if not windows or len(windows)>2048 or stable_hash(windows)!=spec.windows_sha256:
        raise ValueError("empty/oversize/changed window manifest")
    ids=set()
    sources={}
    wanted=set()
    mappings={}
    for window in windows:
        size=len(window["samples"])
        if (not 1<=size<=1024 or not isinstance(window["window_id"],str)
                or not re.fullmatch("window-[a-f0-9]{24}",window["window_id"])
                or window["window_id"] in ids or window["split"]!=spec.partition
                or any(type(window[k]) is not int or window[k]<=0 for k in ("source_width","source_height"))
                or window["source_width"]*window["source_height"]>16777216
                or window["source_rotation"] not in (0,90,180,270)):
            raise ValueError("window ID/size/partition mismatch")
        ids.add(window["window_id"])
        if tuple(window["class_ids"])!=tuple(spec.class_ids):
            raise ValueError("cache output class order mismatch")
        if window["video_id"] in sources and sources[window["video_id"]]!=window["source_sha256"]:
            raise ValueError("video source hash changed across windows")
        sources[window["video_id"]]=window["source_sha256"]
        targets=np.asarray(window["targets"])
        known=np.asarray(window["known_mask"])
        image=np.asarray(window["image_mask"])
        padding=np.asarray(window["padding_mask"])
        if (targets.shape!=(size,len(spec.class_ids)) or known.shape!=targets.shape
                or image.shape!=(size,) or padding.shape!=(size,) or known.dtype!=np.bool_
                or image.dtype!=np.bool_ or padding.dtype!=np.bool_
                or not np.issubdtype(targets.dtype,np.number) or not np.isfinite(targets).all()
                or not np.isin(targets,(0,1)).all() or (known & (~image[:,None] | padding[:,None])).any()):
            raise ValueError("invalid feature/target/image/padding masks")
        for n,sample in enumerate(window["samples"]):
            if sample is None:
                if not padding[n] or image[n]:raise ValueError("missing sample must be padded")
            elif image[n]:
                if padding[n]:raise ValueError("padded sample cannot have an image")
                key=sample_key(window,sample)
                mapping=sample["time"]
                tb=mapping["time_base"]
                if (set(tb)!={"num","den"} or type(tb["num"]) is not int or type(tb["den"]) is not int or min(tb.values())<=0
                        or type(mapping["source_pts"]) is not int or type(mapping["origin_pts"]) is not int
                        or isinstance(mapping["timestamp_sec"],bool) or not isinstance(mapping["timestamp_sec"],(int,float))
                        or mapping["timestamp_sec"]<0
                        or mapping["valid"] is not True or mapping["rotation"]!=window["source_rotation"]
                        or not math.isclose(float((mapping["source_pts"]-mapping["origin_pts"])*Fraction(tb["num"],tb["den"])),
                                            mapping["timestamp_sec"],abs_tol=1e-6)):
                    raise ValueError("invalid cache source time mapping")
                if key in mappings and mappings[key]!=mapping:raise ValueError("inconsistent PTS mapping across windows")
                mappings[key]=mapping
                wanted.add(key)
    if stable_hash(sources)!=spec.source_sha256:raise ValueError("source fingerprint mismatch")
    if len(wanted)>100000:raise ValueError("unique source-frame budget")
    return wanted


def _verify_sources(source_root: Path, windows: list[dict]) -> None:
    sources={}
    for window in windows:
        value=(window["source_path"],window["source_sha256"])
        prior=sources.setdefault(window["video_id"],value)
        if prior!=value:raise ValueError("inconsistent source path/hash across windows")
    root=Path(source_root).resolve(strict=True)
    for path,expected in sources.values():
        actual=local_source(root,path)
        if source_hash(actual,2*1024**3)!=expected:
            raise ValueError("original source hash changed; rebuild manifest before cache")


def build_cache(destination: Path, *, source_root: Path, spec: CacheSpec, windows: list[dict], frames,
                encoder: torch.nn.Module, encoder_metadata: dict,
                config: PreprocessConfig=PreprocessConfig(), max_bytes: int=2*1024**3,
                readiness_binding: dict|None=None) -> dict:
    wanted=_validate_windows(windows,spec)
    validate_data_binding(readiness_binding,spec)
    _verify_sources(source_root,windows)
    if config.fingerprint()!=spec.preprocessing_sha256 or stable_hash(encoder_metadata)!=spec.encoder_sha256:
        raise ValueError("preprocessing/encoder descriptor fingerprint mismatch")
    if (encoder_metadata.get("feature_dim")!=576 or encoder_metadata.get("test_only") is not spec.test_only
            or encoder_metadata.get("state_sha256")!=encoder_fingerprint(encoder)
            or any(p.requires_grad for p in encoder.parameters())):
        raise ValueError("encoder must be frozen, fingerprinted and feature_dim=576")
    if not spec.test_only and encoder_metadata.get("weights")!="IMAGENET1K_V1":
        raise ValueError("real cache requires local prepared ImageNet encoder")
    parameters=list(encoder.parameters())
    buffers=list(encoder.buffers())
    device=(parameters or buffers)[0].device
    if encoder_metadata.get("device")!=str(device):
        raise ValueError("encoder device does not match descriptor")
    was_training=encoder.training
    geometry={sample_key(window,sample):(window["source_width"],window["source_height"],window["source_rotation"])
              for window in windows for sample in window["samples"] if sample is not None and sample["image_mask"]}

    def build(staging,register):
        memo={}
        seen=set()
        encoder.eval()
        try:
            with torch.inference_mode():
                for key,image,rotation in frames:
                    if key not in wanted:continue
                    if key in seen:raise ValueError("duplicate source frame in cache producer")
                    seen.add(key)
                    result=preprocess_image(image,rotation=rotation,config=config)
                    meta=result["transform"]
                    if (meta["original_width"],meta["original_height"],rotation)!=geometry[key]:
                        raise ValueError("cache must use original decoded pixels/rotation, not annotation crops")
                    prepared=result["tensor"]
                    output=encoder(prepared[None].to(device))
                    if output.shape!=(1,576) or output.dtype!=torch.float32 or not bool(torch.isfinite(output).all()):
                        raise ValueError("encoder output must be finite FP32 [1,576]")
                    memo[key]=output[0].detach().cpu().numpy().copy()
            if seen!=wanted:raise ValueError("source producer did not provide every observed PTS")
            if encoder_fingerprint(encoder)!=encoder_metadata["state_sha256"]:
                raise ValueError("encoder state mutated during frozen cache")
            entries=[]
            for window in windows:
                size=len(window["samples"])
                features=np.zeros((size,576),dtype=np.float32)
                for n,sample in enumerate(window["samples"]):
                    if sample is not None and window["image_mask"][n]:
                        features[n]=memo[sample_key(window,sample)]
                payload=io.BytesIO()
                np.savez(payload,features=features,targets=np.asarray(window["targets"],dtype=np.float32),
                         known_mask=np.asarray(window["known_mask"],dtype=np.bool_),
                         image_mask=np.asarray(window["image_mask"],dtype=np.bool_),
                         padding_mask=np.asarray(window["padding_mask"],dtype=np.bool_))
                entry=register(window["window_id"]+".npz",payload.getvalue())
                entries.append({"window_id":window["window_id"],"path":entry["path"],"size":size})
            document={"cache_version":spec.version,"spec":spec.descriptor(),"windows":windows,"entries":entries,
                      "encoder":encoder_metadata,"preprocessing":config.descriptor(),"readiness_binding":readiness_binding}
            register("cache.json",__import__("json").dumps(document,ensure_ascii=False,indent=2,allow_nan=False).encode()+b"\n")
            _verify_sources(source_root,windows)
            return {"kind":"feature-cache-v1","spec":spec.descriptor(),"window_count":len(windows),"feature_dim":576,
                    "test_only":spec.test_only,"software_cache_complete":True,
                    "production_cache_ready":False,
                    "readiness_reason":"Completeness is separate from dataset/model production readiness."}
        finally:
            encoder.train(was_training)
            close=getattr(frames,"close",None)
            if close:close()
    return artifact_transaction(destination,spec.key(),build,max_bytes=max_bytes,min_free_bytes=64*1024**2)


def _numeric_npz(path: Path, size: int, classes: int) -> dict:
    expected={"features":((size,576),np.dtype("float32")),"targets":((size,classes),np.dtype("float32")),
              "known_mask":((size,classes),np.dtype("bool")),"image_mask":((size,),np.dtype("bool")),
              "padding_mask":((size,),np.dtype("bool"))}
    if path.stat().st_size>8*1024**2:raise ValueError("cache window byte budget")
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist()
        if len(infos)!=5 or {i.filename for i in infos}!={key+".npy" for key in expected}:
            raise ValueError("unexpected cache array entries")
        for info in infos:
            if info.compress_type!=zipfile.ZIP_STORED or info.file_size>8*1024**2:
                raise ValueError("compressed/oversize cache storage unsupported")
            shape,dtype=expected[info.filename[:-4]]
            with archive.open(info) as incoming:
                if np.lib.format.read_magic(incoming)!=(1,0):raise ValueError("unsupported numeric header version")
                actual,fortran,actual_dtype=np.lib.format.read_array_header_1_0(incoming,max_header_size=2048)
                if (actual!=shape or fortran or actual_dtype!=dtype or actual_dtype.hasobject
                        or info.file_size!=incoming.tell()+math.prod(shape)*dtype.itemsize):
                    raise ValueError("cache header shape/dtype/size mismatch")
    with np.load(path,allow_pickle=False,max_header_size=2048) as arrays:
        result={key:arrays[key].copy() for key in expected}
    if not np.isfinite(result["features"]).all() or not np.isfinite(result["targets"]).all() or not np.isin(result["targets"],(0,1)).all():
        raise ValueError("invalid numeric cache values")
    if (result["known_mask"] & (~result["image_mask"][:,None] | result["padding_mask"][:,None])).any():
        raise ValueError("unknown/padding cache mask mismatch")
    return result


def load_cache(directory: Path, spec: CacheSpec, *, max_bytes: int=2*1024**3) -> dict:
    directory=Path(directory)
    marker=read_json(directory/"artifacts.json",max_bytes=32*1024**2)
    if (len(marker.get("files",[]))>2049 or any(type(e.get("size_bytes")) is not int or e["size_bytes"]<0 for e in marker["files"])
            or sum(e["size_bytes"] for e in marker["files"])>max_bytes):
        raise ValueError("cache file count/byte budget")
    report=_existing(directory,spec.key())
    if report["data"].get("kind")!="feature-cache-v1" or report["data"].get("test_only") is not spec.test_only:
        raise ValueError("cache kind/provenance mismatch")
    document=read_json(directory/"cache.json")
    if CacheSpec.from_dict(document["spec"])!=spec:raise ValueError("foreign cache spec")
    if (CacheSpec.from_dict(report["data"]["spec"])!=spec or stable_hash(document["encoder"])!=spec.encoder_sha256
            or PreprocessConfig(**document["preprocessing"]).fingerprint()!=spec.preprocessing_sha256):
        raise ValueError("cache descriptor fingerprints changed")
    _validate_windows(document["windows"],spec)
    validate_data_binding(document.get("readiness_binding"),spec)
    if len(document["entries"])!=len(document["windows"]):
        raise ValueError("cache entry/window count mismatch")
    arrays=[]
    for entry,window in zip(document["entries"],document["windows"]):
        if (entry["window_id"]!=window["window_id"] or entry["path"]!=window["window_id"]+".npz"
                or entry["size"]!=len(window["samples"]) or not re.fullmatch(r"window-[a-f0-9]{24}\.npz",entry["path"])):
            raise ValueError("cache entry identity mismatch")
        arrays.append(_numeric_npz(directory/entry["path"],entry["size"],len(spec.class_ids)))
    return {"spec":spec,"windows":document["windows"],"arrays":arrays,"encoder":document["encoder"],
            "preprocessing":document["preprocessing"],"test_only":spec.test_only,
            "readiness_binding":document.get("readiness_binding")}


def cache_configuration(classes, binding=None):
    return {"version":"temporal-cache-v1","rate":2,"size":32,"stride":16,"class_ids":list(classes),
            "readiness_binding_sha256":None if binding is None else stable_hash(binding)}


def validate_data_binding(binding, spec):
    if binding is None:return
    from contracts.python_ports import validate_contract
    report=binding["report"]
    expected={key:getattr(spec,key) for key in ("dataset_sha256","split_sha256","annotation_sha256","taxonomy_sha256")}
    if (binding["version"]!="training-data-binding-v1" or binding["inputs"]!=expected
            or not isinstance(binding["qa_revision"],str) or re.fullmatch("[a-f0-9]{64}",binding["qa_revision"]) is None
            or report["report_version"]!="data-readiness-v1" or report["qa"]["qa_version"]!="annotations-qa-v1"
            or binding["qa_revision"]!=report["qa"]["dataset_revision"]
            or report["contract"]["provenance"]["sha256"]!=spec.dataset_sha256
            or stable_hash(cache_configuration(spec.class_ids,binding))!=spec.config_sha256):
        raise ValueError("cache/readiness/QA input binding mismatch")
    validate_contract("dataset_readiness",report["contract"])
