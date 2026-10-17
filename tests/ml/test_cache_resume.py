from dataclasses import asdict, replace
import copy
import io
from pathlib import Path

import numpy as np
import pytest
import torch

from ml.cache import CacheSpec, _numeric_npz, build_cache, encoder_fingerprint, load_cache
from ml.data.deduplicate import stable_hash
from ml.data.pts_index import iter_indexed_frames
from ml.preprocessing import PreprocessConfig
from ml.windows import labelled_windows
from test_annotations import sample_documents, add_action


class FixtureEncoder(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer("gain",torch.ones(1))
    def forward(self,images):
        return images.mean(dim=(-2,-1)).repeat(1,192)*self.gain


@pytest.fixture(scope="module",autouse=True)
def cpu_threads():
    previous=torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


def cache_case(root):
    data=sample_documents(root)
    classes=[c["id"] for c in data["action_taxonomy"]["classes"][:2]]
    add_action(data)
    add_action(data,start_sec=.5,end_sec=1.5,state="absent_verified")
    windows=labelled_windows(data["index"],data["scenes"],data["actions"],classes)
    encoder=FixtureEncoder()
    meta={"backbone":"fixture-channel-means-v1","feature_dim":576,"weights":"None","test_only":True,
          "device":"cpu","state_sha256":encoder_fingerprint(encoder)}
    spec=CacheSpec(source_sha256=stable_hash({w["video_id"]:w["source_sha256"] for w in windows}),
        dataset_sha256=stable_hash(data["manifest"]),split_sha256=stable_hash(data["manifest"]["split_version"]),
        annotation_sha256=stable_hash(data["actions"]),taxonomy_sha256=stable_hash(data["action_taxonomy"]),
        encoder_sha256=stable_hash(meta),preprocessing_sha256=PreprocessConfig().fingerprint(),
        config_sha256=stable_hash({"rate":2,"size":32,"stride":16}),windows_sha256=stable_hash(windows),
        class_ids=tuple(classes),partition=windows[0]["split"])
    def frames():
        for row,frame in iter_indexed_frames(root,data["index"]):
            scene=next(s for s in data["scenes"]["scenes"] if s["start_ordinal"]<=row["ordinal"]<s["end_ordinal"])
            yield (data["index"]["video_id"],scene["scene_id"],data["index"]["split"],row["source_pts"]),frame.to_image(),data["index"]["rotation"]
    return data,windows,encoder,meta,spec,frames


def build(root,case,**changes):
    data,windows,encoder,meta,spec,frames=case
    return build_cache(root,source_root=data["source_root"],spec=spec,windows=windows,frames=frames(),
                       encoder=encoder,encoder_metadata=meta,**changes)


def test_cache_complete_reuse_numeric_arrays_masks_and_test_only_provenance(tmp_path):
    case=cache_case(tmp_path)
    spec=case[4]
    report=build(tmp_path/"cache",case)
    loaded=load_cache(tmp_path/"cache",spec)
    arrays=loaded["arrays"][0]
    assert arrays["features"].shape==(32,576) and arrays["targets"].shape==(32,2)
    assert arrays["known_mask"].sum()==2 and not arrays["known_mask"][2:].any()
    assert loaded["test_only"] is True and report["data"]["production_cache_ready"] is False
    def must_not_decode():
        raise AssertionError("complete matching cache must not recompute")
        yield
    assert build_cache(tmp_path/"cache",source_root=case[0]["source_root"],spec=spec,windows=case[1],frames=must_not_decode(),
        encoder=case[2],encoder_metadata=case[3])==report


@pytest.mark.parametrize("field",[
    "source_sha256","dataset_sha256","split_sha256","annotation_sha256","taxonomy_sha256",
    "encoder_sha256","preprocessing_sha256","config_sha256","windows_sha256","class_ids","partition","test_only"])
def test_every_significant_input_invalidates_complete_cache(tmp_path,field):
    case=cache_case(tmp_path)
    spec=case[4]
    build(tmp_path/"cache",case)
    value="0"*64
    if field=="class_ids":value=tuple(reversed(spec.class_ids))
    if field=="partition":value="dev_validation"
    if field=="test_only":value=False
    with pytest.raises(ValueError):
        load_cache(tmp_path/"cache",replace(spec,**{field:value}))


def test_interrupted_partial_write_is_not_published_and_rebuild_from_sources_is_valid(tmp_path,monkeypatch):
    case=cache_case(tmp_path)
    source=tmp_path/case[0]["index"]["path"]
    original=(source.read_bytes(),source.stat().st_mtime_ns)
    open_file=Path.open
    class PartialWrite:
        def __init__(self,file):self.file=file
        def __enter__(self):return self
        def __exit__(self,*args):self.file.close()
        def write(self,data):
            self.file.write(data[:len(data)//2])
            raise OSError("injected partial cache write")
    def broken(path,*args,**kwargs):
        handle=open_file(path,*args,**kwargs)
        return PartialWrite(handle) if path.suffix==".npz" and args and args[0]=="xb" else handle
    monkeypatch.setattr(Path,"open",broken)
    with pytest.raises(OSError,match="partial"):
        build(tmp_path/"interrupted",case)
    assert not (tmp_path/"interrupted").exists() and not list(tmp_path.glob(".fortress-extract-*"))
    monkeypatch.undo()
    build(tmp_path/"recovered",case)
    assert load_cache(tmp_path/"recovered",case[4])["arrays"][0]["known_mask"].sum()==2
    assert (source.read_bytes(),source.stat().st_mtime_ns)==original


def test_corrupt_or_foreign_cache_rejected_preserved_and_new_generation_reconstructs(tmp_path):
    case=cache_case(tmp_path)
    build(tmp_path/"cache",case)
    expected=load_cache(tmp_path/"cache",case[4])["arrays"][0]["features"]
    path=next((tmp_path/"cache").glob("*.npz"))
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError):load_cache(tmp_path/"cache",case[4])
    build(tmp_path/"new-generation",case)
    assert np.array_equal(load_cache(tmp_path/"new-generation",case[4])["arrays"][0]["features"],expected)
    foreign=tmp_path/"foreign"
    foreign.mkdir()
    (foreign/"user-notes.txt").write_text("preserve")
    with pytest.raises(ValueError):build(foreign,case)
    assert (foreign/"user-notes.txt").read_text()=="preserve" and path.read_bytes()==b"corrupt"


def test_mutated_encoder_or_annotation_crop_cannot_reuse_source_cache(tmp_path):
    case=cache_case(tmp_path)
    build(tmp_path/"cache",case)
    case[2].gain.add_(1)
    with pytest.raises(ValueError,match="fingerprint"):
        build(tmp_path/"cache",case)
    case[2].gain.sub_(1)
    def cropped():
        for key,image,rotation in case[5]():
            yield key,image.crop((2,4,30,22)),rotation
    with pytest.raises(ValueError,match="original decoded"):
        build_cache(tmp_path/"crop",source_root=case[0]["source_root"],spec=case[4],windows=case[1],frames=cropped(),
                    encoder=case[2],encoder_metadata=case[3])


def test_changed_original_bytes_cannot_silently_reuse_an_old_complete_cache(tmp_path):
    case=cache_case(tmp_path)
    build(tmp_path/"cache",case)
    source=tmp_path/case[0]["index"]["path"]
    source.write_bytes(b"source changed after first cache generation")
    with pytest.raises(ValueError,match="source"):
        build(tmp_path/"cache",case)


@pytest.mark.parametrize("invalid",["object","shape","nan","known_padding"])
def test_numeric_cache_header_and_masks_fail_before_accepting_payload(tmp_path,invalid):
    features=np.zeros((1,576),dtype=np.float32)
    targets=np.zeros((1,2),dtype=np.float32)
    known=np.zeros((1,2),dtype=bool)
    image=np.ones(1,dtype=bool)
    padding=np.zeros(1,dtype=bool)
    if invalid=="object":features=np.zeros((1,576),dtype=object)
    if invalid=="shape":features=np.zeros((2,576),dtype=np.float32)
    if invalid=="nan":features[0,0]=np.nan
    if invalid=="known_padding":known[:]=True;padding[:]=True
    path=tmp_path/"invalid.npz"
    np.savez(path,features=features,targets=targets,known_mask=known,image_mask=image,padding_mask=padding)
    with pytest.raises(ValueError):_numeric_npz(path,1,2)
