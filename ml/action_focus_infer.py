"""Export and run the frozen local experimental model without the training dataset."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import torch
import torchvision

from ml import action_focus as training
from ml import action_focus_inputs as inputs
from ml.data.annotation_tasks import read_json
from ml.data.manifest import probe_video,source_hash
from ml.data.pts_index import build_index
from ml.data.scenes import define_scenes,sample_scenes
from ml.models.encoder import FrozenEncoder,file_sha256,safe_torch_load
from ml.video_baseline import atomic_checkpoint,atomic_json,encode_source

VERSION="workspace-action-first-local-bundle-v1"


def code_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def export(experiment,output):
    decision=training.frozen_decision(experiment)
    plan=read_json(Path(experiment)/"protocol.json")
    if plan["code_sha256"]!=training.code_hash():raise ValueError("training code changed")
    marker=read_json(Path(plan["focus"])/"inputs.json")
    state=safe_torch_load(Path(decision["fit"]),expected_sha256=decision["fit_sha256"])
    if state["format"]!=training.VERSION or state["identity"]["protocol"]!=plan["protocol_sha256"]:
        raise ValueError("fit lineage mismatch")
    encoder=FrozenEncoder(weights_path=Path(marker["encoder_weights"]),weights_sha256=marker["encoder_sha256"])
    if state["suffix"] is not None:encoder.features[-2:].load_state_dict(state["suffix"],strict=True)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    payload={"format":VERSION,"encoder":dict(encoder.features.state_dict()),"model":state["model"],
             "normalization":state["normalization"],"auxiliary_weights":state["auxiliary_weights"]}
    tensor_bytes=sum(v.numel()*v.element_size() for key in ("encoder","model") for v in payload[key].values())
    if tensor_bytes>12*1024**2:raise ValueError("model state exceeds12MiB budget")
    atomic_checkpoint(output/"weights.pt",payload)
    metadata={"version":VERSION,"arm":state["arm"],"config":state["config"],"threshold":decision["selected"]["threshold"],
              "weights_sha256":file_sha256(output/"weights.pt"),"original_fit_sha256":decision["fit_sha256"],
              "protocol_sha256":plan["protocol_sha256"],"pretrained_weights_sha256":marker["encoder_sha256"],
              "inference_code_sha256":code_hash(),"training_code_sha256":plan["code_sha256"],
              "roi":list(inputs.ROI),"rate":4 if state["arm"].startswith("roi4_") else 2,
              "taxonomy":list(inputs.TAXONOMY),"tensor_bytes":tensor_bytes,"production_ready":False,
              "event_intervals_validated":False,"human_approved_actions":False,"independent_external_test":False}
    atomic_json(output/"bundle.json",metadata)
    print(json.dumps(metadata),flush=True)
    return metadata


class FeatureEncoder(torch.nn.Module):
    def __init__(self,state):
        super().__init__()
        self.features=torchvision.models.mobilenet_v3_small(weights=None).features
        self.features.load_state_dict(state,strict=True)
        self.eval().requires_grad_(False)

    def forward(self,images):
        if (images.ndim!=4 or images.shape[1:]!=(3,224,224) or not 1<=len(images)<=64
                or images.dtype!=torch.float32 or not torch.isfinite(images).all()):
            raise ValueError("invalid encoder input")
        return self.features(images).mean((-2,-1))


class Predictor:
    def __init__(self,bundle,device="cuda"):
        torch.set_num_threads(4)
        self.device=device;self.metadata=read_json(Path(bundle)/"bundle.json")
        m=self.metadata
        if (m["version"]!=VERSION or m["inference_code_sha256"]!=code_hash() or m["training_code_sha256"]!=training.code_hash()
                or m["arm"] not in training.ARMS or m["taxonomy"]!=list(inputs.TAXONOMY) or m["roi"]!=list(inputs.ROI)
                or m["production_ready"] is not False or not 0<=m["threshold"]<=1):
            raise ValueError("unsupported local model bundle")
        state=safe_torch_load(Path(bundle)/"weights.pt",expected_sha256=m["weights_sha256"],max_bytes=12*1024**2)
        if state["format"]!=VERSION:raise ValueError("bundle format mismatch")
        self.encoder=FeatureEncoder(state["encoder"]).to(device).eval()
        self.model=training.ActionFirstGRU(m["config"]["dropout"],m["arm"]=="roi_action_bottleneck").to(device).eval()
        self.model.load_state_dict(state["model"],strict=True)
        self.norm=state["normalization"];self.support=state["auxiliary_weights"]

    def indexed(self,source_root,index,*,return_features=False):
        arm=self.metadata["arm"]
        if arm=="global_joint":
            features,points=encode_source(source_root,index,define_scenes(index),self.encoder,self.device,"three_crop")
        else:
            arrays=inputs.encode_roi(source_root,index,self.encoder,self.device,variants=False)
            features,points=arrays["features"],arrays["source_pts"]
            if not arm.startswith("roi4_"):
                lookup={int(p):i for i,p in enumerate(points)}
                selected=[lookup[s["time"]["source_pts"]] for s in sample_scenes(index,define_scenes(index),rate=2.)]
                features,points=features[selected],points[selected]
        normalized=(torch.from_numpy(features)-self.norm["mean"])/self.norm["std"]
        with torch.inference_mode():
            logit,a,_=self.model(normalized[None].to(self.device),torch.tensor([len(features)]))
        timing={f["source_pts"]:f["timestamp_sec"] for f in index["frames"]}
        result={"score":float(logit.sigmoid()[0].cpu()),"source_pts":points.tolist()}
        # Serialize only supported classes; unsupported is unknown rather than zero.
        action_values=a[0,:len(features)].sigmoid().cpu()
        result["action_scores"]=[{"source_pts":int(p),"timestamp_sec":timing[int(p)],
            "scores":{name:float(action_values[n,c]) if bool(self.support[0]["enabled"][c]) else None for c,name in enumerate(inputs.TAXONOMY)}}
            for n,p in enumerate(points)]
        if return_features:result["features"]=features
        return result

    def analyze(self,video,*,return_features=False):
        if self.device=="cuda":torch.cuda.synchronize()
        started=time.perf_counter()
        source=Path(video).resolve(strict=True)
        digest=source_hash(source,2*1024**3);metadata,_=probe_video(source)
        if metadata["duration_sec"]>180:raise ValueError("duration exceeds180 seconds")
        row={"video_id":"raw-"+digest[:24],"path":source.name,"sha256":digest,
             "canonical_id":"sha256:"+digest,"group_id":"sha256:"+digest,"scene_id":"unreviewed",
             "split":"excluded","official_label":None,"provenance":{"kind":"original","source_id":digest,"sha256":digest},**metadata}
        index=build_index(source.parent,row,dataset_version="local-focus-inference-v1",split_version="not-training")
        result=self.indexed(source.parent,index,return_features=return_features)
        if self.device=="cuda":torch.cuda.synchronize()
        return {**result,"source_sha256":digest,"threshold":self.metadata["threshold"],
                "prediction":"violation" if result["score"]>=self.metadata["threshold"] else "no_violation",
                "elapsed_seconds":time.perf_counter()-started,"model_sha256":self.metadata["weights_sha256"],
                "production_ready":False,"event_intervals_validated":False,"action_scores_are_assistant_agreement":True}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("export");a.add_argument("--experiment",type=Path,required=True);a.add_argument("--output",type=Path,required=True)
    a=sub.add_parser("infer");a.add_argument("--bundle",type=Path,required=True);a.add_argument("--video",type=Path,required=True);a.add_argument("--device",choices=("cpu","cuda"),default="cuda")
    a=p.parse_args(argv)
    if a.command=="export":export(a.experiment,a.output)
    else:print(json.dumps(Predictor(a.bundle,a.device).analyze(a.video)),flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
