"""Local grouped comparison of workspace crops and action-first learning."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import time
import zipfile

import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence, pad_sequence

from ml import action_refinement as previous
from ml import action_focus_inputs as inputs
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.models.encoder import FrozenEncoder, file_sha256, safe_torch_load
from ml.small_data import fit_norm, summarize
from ml.video_baseline import atomic_checkpoint, atomic_json, metrics

VERSION = "workspace-action-first-v1"
ARMS = ("global_joint", "roi_joint", "roi_pretrain", "roi_action_bottleneck", "roi_finetune_pair", "roi4_finetune_pair")
SEEDS = previous.SEEDS
CONFIG = {"epochs":60,"lr":.0003,"dropout":.5,"weight_decay":.05,
          "pretrain_epochs":40,"cnn_epochs":6,"cnn_lr":.0001,"clip_frames_2fps":32}


def code_hash():
    return stable_hash({"focus":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "inputs":inputs.code_hash(),"previous":previous.code_hash()})


def rank(trial):
    m=trial["metrics"]
    return (min(m["accuracy"],m["balanced_accuracy"],m["macro_f1"]),
            m["accuracy"],m["balanced_accuracy"],m["macro_f1"],-trial["bce"])


def calibrate(predictions):
    if {p["truth"] for p in predictions}!={False,True}:
        raise ValueError("calibration needs both development classes")
    scores=sorted({p["score"] for p in predictions})
    thresholds=[0.]+[(a+b)/2 for a,b in zip(scores,scores[1:])]+[1.]
    return max(thresholds,key=lambda t:rank({"metrics":metrics(predictions,t),"bce":0.})+( -abs(t-.5),-t))


def masked_loss(logits,targets,weights,state_weight=.25):
    known=(targets>=0)&weights["enabled"]
    raw=nn.functional.binary_cross_entropy_with_logits(logits,targets.clamp_min(0),reduction="none",pos_weight=weights["positive_weight"])
    axes=tuple(range(targets.ndim-1))
    count=known.sum(axes)
    scale=torch.ones(logits.shape[-1],device=logits.device)
    if logits.shape[-1]==len(inputs.TAXONOMY):
        scale[7:]=state_weight
    scale=scale*(count>0)
    return (((raw*known).sum(axes)/count.clamp_min(1))*scale).sum()/scale.sum().clamp_min(1)


def training_pairs(rows):
    return [(a,b) for a,r in enumerate(rows) for b,s in enumerate(rows)
            if r["group_id"]==s["group_id"] and r["target"]==1 and s["target"]==0]


def pair_loss(logits,pairs):
    if not pairs:
        return logits.sum()*0.
    return torch.stack([nn.functional.softplus(-(logits[a]-logits[b])) for a,b in pairs]).mean()


def clip_start(row,width,rng):
    n=len(row["features"])
    if n<=width:
        return 0
    positive=torch.where((row["actions"][:,:7]==1).any(1))[0].tolist()
    if positive and rng.random()<.5:
        anchor=int(rng.choice(positive))
        return min(n-width,max(0,anchor-width//2))
    return int(rng.integers(0,n-width+1))


def action_statistics(probabilities,lengths):
    """Predicted probabilities only; no annotations/appearance enter the verdict head."""
    result=[]
    for values,n in zip(probabilities,lengths.tolist()):
        values=values[:n]
        third=max(1,n//3)
        position=torch.linspace(0,1,n,device=values.device)[:,None]
        stats=[values.mean(0),values.amax(0),values[:third].mean(0),values[-third:].mean(0),
               (values*position).sum(0)/values.sum(0).clamp_min(1e-6)]
        history=values.cumsum(0)-values
        order=(values.T@history)/(n*n)
        result.append(torch.cat([*stats,order.flatten()]))
    return torch.stack(result)


class ActionFirstGRU(nn.Module):
    def __init__(self,dropout=.5,bottleneck=False):
        super().__init__()
        self.gru=nn.GRU(576,256,batch_first=True)
        self.action_head=nn.Linear(256,len(inputs.TAXONOMY))
        self.object_head=nn.Linear(256,len(previous.OBJECT_IDS))
        self.dropout=nn.Dropout(dropout)
        self.bottleneck=bottleneck
        count=len(inputs.TAXONOMY)+len(previous.OBJECT_IDS)
        self.head=nn.Linear(count*5+count*count if bottleneck else 512,1)
        self.register_buffer("support",torch.ones(count,dtype=torch.bool))

    def forward(self,values,lengths):
        if (values.ndim!=3 or values.shape[-1]!=576 or not torch.isfinite(values).all()
                or len(lengths)!=len(values) or (lengths<1).any() or (lengths>values.shape[1]).any()):
            raise ValueError("invalid padded sequence")
        output,_=self.gru(pack_padded_sequence(values,lengths.cpu(),batch_first=True,enforce_sorted=False))
        output,_=pad_packed_sequence(output,batch_first=True,total_length=values.shape[1])
        a,o=self.action_head(output),self.object_head(output)
        if self.bottleneck:
            probabilities=torch.cat((a,o),-1).sigmoid()*self.support
            representation=action_statistics(probabilities,lengths)
        else:
            mask=torch.arange(values.shape[1],device=values.device)[None]<lengths.to(values.device)[:,None]
            mean=output.sum(1)/lengths.to(values.device)[:,None]
            maximum=output.masked_fill(~mask[...,None],-torch.inf).amax(1)
            representation=torch.cat((mean,maximum),-1)
        return self.head(self.dropout(representation)).squeeze(-1),a,o


def prepare(cache,overlay,compat,focus,output,previous_experiment):
    document,rows,binding,stats,marker=inputs.load(cache,overlay,compat,focus)
    old=read_json(Path(previous_experiment)/"protocol.json")
    development=sorted(r["video_id"] for r in rows if r["split"] in ("train","dev_validation"))
    reserved=sorted(r["video_id"] for r in rows if r["split"]=="independent_test")
    if development!=old["development_ids"] or reserved!=old["reserved_ids"]:
        raise ValueError("development/holdout changed")
    for fold in old["folds"]:
        groups={r["video_id"]:r["group_id"] for r in rows}
        if {groups[v] for v in fold["train"]}&{groups[v] for v in fold["validation"]}:
            raise ValueError("family leakage")
    plan={"version":VERSION,"cache":str(Path(cache).resolve()),"overlay":str(Path(overlay).resolve()),
          "compat":str(Path(compat).resolve()),"focus":str(Path(focus).resolve()),"binding":binding,
          "code_sha256":code_hash(),"arms":list(ARMS),"config":CONFIG,"seeds":list(SEEDS),"primary_seed":42,
          "folds":old["folds"],"final_inner":old["final_inner"],"development_ids":development,"reserved_ids":reserved,
          "selection":"inner OOF max min(accuracy,balanced_accuracy,macro_f1), accuracy,BA,F1,lower BCE; threshold inner only",
          "sampling":"exact source PTS; ROI2/4fps; full 2fps control; unknown labels masked; no dense interval fill",
          "training":"fixed hyperparameters; train-only normalization, weights and CNN/action pretraining; last2 CNN blocks only; BN frozen",
          "pair_weight":.2,"auxiliary_weights":[.3,.15],"roi":list(inputs.ROI),"human_approved_actions":False,
          "supervision_counts":stats,"original_verdicts_changed":False,"production_ready":False,"independent_external_test":False,
          "runtime":{"torch":str(torch.__version__),"numpy":str(np.__version__)}}
    plan["protocol_sha256"]=stable_hash(plan)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    atomic_json(output/"protocol.json",plan)
    with zipfile.ZipFile(output/"source_snapshot.zip","x",zipfile.ZIP_DEFLATED) as archive:
        for name in ("action_focus.py","action_focus_inputs.py","action_refinement.py","small_data.py","video_baseline.py","preprocessing.py","models/encoder.py"):
            archive.write(Path(__file__).parent/name,"ml/"+name)
    print(json.dumps({"prepared":str(output),"protocol_sha256":plan["protocol_sha256"]}),flush=True)
    return plan


class Experiment:
    def __init__(self,directory,device="cuda"):
        self.directory,self.device=Path(directory),device
        self.plan=read_json(self.directory/"protocol.json")
        if (self.plan["version"]!=VERSION or self.plan["code_sha256"]!=code_hash()
                or stable_hash({k:v for k,v in self.plan.items() if k!="protocol_sha256"})!=self.plan["protocol_sha256"]):
            raise ValueError("protocol/code changed; create new version")
        self.document,rows,binding,_,marker=inputs.load(self.plan["cache"],self.plan["overlay"],self.plan["compat"],self.plan["focus"])
        if binding!=self.plan["binding"]:
            raise ValueError("inputs changed")
        self.by_id={r["video_id"]:r for r in rows}
        self.fits=self.directory/"fits";self.fits.mkdir(exist_ok=True)
        encoder=FrozenEncoder(weights_path=Path(marker["encoder_weights"]),weights_sha256=marker["encoder_sha256"])
        self.suffix_template=copy.deepcopy(encoder.features[-2:]).eval().requires_grad_(True)

    def rows(self,ids,arm,suffix=None):
        rows=[]
        for video in ids:
            original=self.by_id[video]
            if arm=="global_joint":
                rows.append(original)
                continue
            if "prefix" not in original:
                raise ValueError("ROI inputs missing")
            features=original["roi_features"]
            if suffix is not None:
                output=[]
                with torch.inference_mode():
                    for batch in original["prefix"][:,0].split(64):
                        output.append(suffix(batch.to(self.device)).mean((-2,-1)).cpu())
                features=torch.cat(output)
            indices=torch.arange(len(features)) if arm.startswith("roi4_") else original["roi2_indices"]
            rows.append({**original,"features":features[indices],"actions":original["roi_actions"][indices],
                         "objects":original["roi_objects"][indices],"source_pts":original["roi_pts"][indices.numpy()]})
        return rows

    def adapt_cnn(self,ids,config):
        suffix=copy.deepcopy(self.suffix_template).to(self.device).eval().requires_grad_(True)
        frame_head=nn.Linear(576,len(inputs.TAXONOMY)+len(previous.OBJECT_IDS)).to(self.device)
        prefixes,actions,objects=[],[],[]
        for video in ids:
            row=self.by_id[video]
            known=(row["roi_actions"]>=0).any(1)|(row["roi_objects"]>=0).any(1)
            prefixes.append(row["prefix"][known]);actions.append(row["roi_actions"][known]);objects.append(row["roi_objects"][known])
        x=torch.cat(prefixes).to(self.device);a=torch.cat(actions).to(self.device);o=torch.cat(objects).to(self.device)
        weights=[previous.auxiliary_weights(t[None]) for t in (a,o)]
        optimizer=torch.optim.AdamW([*suffix.parameters(),*frame_head.parameters()],lr=config["cnn_lr"],weight_decay=.05)
        for _ in range(config["cnn_epochs"]):
            order=torch.randperm(len(x),device=self.device)
            for indices in order.split(64):
                variants=torch.randint(0,3,(len(indices),),device=self.device)
                logits=frame_head(suffix(x[indices,variants]).mean((-2,-1)))
                la,lo=logits.split([len(inputs.TAXONOMY),len(previous.OBJECT_IDS)],-1)
                loss=masked_loss(la,a[indices],weights[0])+.5*masked_loss(lo,o[indices],weights[1])
                optimizer.zero_grad(set_to_none=True);loss.backward()
                nn.utils.clip_grad_norm_([*suffix.parameters(),*frame_head.parameters()],1.)
                optimizer.step()
        return suffix.eval(),{k:v.detach().cpu() for k,v in frame_head.state_dict().items()}

    def fit(self,ids,arm,config,seed):
        if arm not in ARMS or len(set(ids))!=len(ids) or not set(ids)<=set(self.plan["development_ids"]):
            raise ValueError("training restricted to unique development sources")
        identity={"protocol":self.plan["protocol_sha256"],"ids":sorted(ids),"arm":arm,"config":config,"seed":seed}
        path=self.fits/(stable_hash(identity)+".pt")
        if path.exists():
            if safe_torch_load(path)["identity"]!=identity:
                raise ValueError("fit identity changed")
            return path
        started=time.perf_counter();torch.manual_seed(seed)
        if self.device=="cuda":torch.cuda.manual_seed_all(seed)
        rng=np.random.default_rng(seed)
        suffix,frame_head=(self.adapt_cnn(ids,config) if "finetune" in arm else (None,None))
        rows=self.rows(ids,arm,suffix)
        norm=fit_norm(rows)
        normalized=[{**r,"features":(r["features"]-norm["mean"])/norm["std"]} for r in rows]
        def batch(selected):
            return (pad_sequence([r["features"] for r in selected],batch_first=True).to(self.device),
                    torch.tensor([len(r["features"]) for r in selected]),
                    pad_sequence([r["actions"] for r in selected],batch_first=True,padding_value=-1).to(self.device),
                    pad_sequence([r["objects"] for r in selected],batch_first=True,padding_value=-1).to(self.device))
        values,lengths,actions,objects=batch(normalized)
        target=torch.tensor([r["target"] for r in rows],device=self.device,dtype=torch.float32)
        weights=[previous.auxiliary_weights(t) for t in (actions,objects)]
        model=ActionFirstGRU(config["dropout"],arm=="roi_action_bottleneck").to(self.device)
        model.support.copy_(torch.cat([w["enabled"] for w in weights]))
        optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=config["weight_decay"])
        pretrain=arm not in ("global_joint","roi_joint")
        model.train()
        pretrain_losses=[]
        if pretrain:
            width=config["clip_frames_2fps"]*(2 if arm.startswith("roi4_") else 1)
            for _ in range(config["pretrain_epochs"]):
                clips=[]
                for row in normalized:
                    start=clip_start(row,width,rng)
                    clips.append({k:(v[start:start+width] if k in ("features","actions","objects") else v) for k,v in row.items()})
                x,l,a,o=batch(clips)
                _,la,lo=model(x+torch.randn_like(x)*.03,l)
                loss=masked_loss(la,a,weights[0])+.5*masked_loss(lo,o,weights[1])
                optimizer.zero_grad(set_to_none=True);loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
                pretrain_losses.append(float(loss.detach()))
        if model.bottleneck:
            for module in (model.gru,model.action_head,model.object_head):module.requires_grad_(False)
        optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=config["lr"],weight_decay=config["weight_decay"])
        objective=nn.BCEWithLogitsLoss(pos_weight=(target==0).sum()/(target==1).sum())
        pairs=training_pairs(rows) if "pair" in arm else []
        losses=[]
        for _ in range(config["epochs"]):
            logits,a,o=model(values+torch.randn_like(values)*.03,lengths)
            components=(objective(logits,target),masked_loss(a,actions,weights[0]),masked_loss(o,objects,weights[1]),pair_loss(logits,pairs))
            loss=components[0]+.3*components[1]+.15*components[2]+.2*components[3]
            if not torch.isfinite(loss):raise ValueError("nonfinite objective")
            optimizer.zero_grad(set_to_none=True);loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
            losses.append([float(c.detach()) for c in components])
        state={"format":VERSION,"identity":identity,"config":config,"arm":arm,"normalization":norm,
               "model":{k:v.detach().cpu() for k,v in model.state_dict().items()},
               "suffix":{k:v.detach().cpu() for k,v in suffix.state_dict().items()} if suffix is not None else None,
               "frame_head":frame_head,"auxiliary_weights":[{k:v.cpu() for k,v in w.items()} for w in weights],
               "loss_history":losses,"pretrain_loss_history":pretrain_losses,"pair_count":len(pairs),
               "elapsed_seconds":time.perf_counter()-started,"production_ready":False,"human_approved_actions":False}
        atomic_checkpoint(path,state)
        print(json.dumps({"fit":arm,"seed":seed,"videos":len(ids),"seconds":state["elapsed_seconds"],"key":path.stem}),flush=True)
        return path

    def predict(self,path,ids,auxiliary=False):
        state=safe_torch_load(path)
        if state["format"]!=VERSION or state["identity"]["protocol"]!=self.plan["protocol_sha256"]:
            raise ValueError("fit/protocol mismatch")
        suffix=None
        if state["suffix"] is not None:
            suffix=copy.deepcopy(self.suffix_template).to(self.device).eval()
            suffix.load_state_dict(state["suffix"],strict=True)
        rows=self.rows(ids,state["arm"],suffix)
        model=ActionFirstGRU(state["config"]["dropout"],state["arm"]=="roi_action_bottleneck").to(self.device).eval()
        model.load_state_dict(state["model"],strict=True)
        norm=state["normalization"]
        values=pad_sequence([(r["features"]-norm["mean"])/norm["std"] for r in rows],batch_first=True).to(self.device)
        with torch.inference_mode():
            video,a,o=model(values,torch.tensor([len(r["features"]) for r in rows]))
        predictions=[{"video_id":r["video_id"],"truth":bool(r["target"]),"score":float(s)} for r,s in zip(rows,video.sigmoid().cpu())]
        if not auxiliary:return predictions
        frames=[{"video_id":r["video_id"],"actions":a[n,:len(r["features"])].sigmoid().cpu(),"objects":o[n,:len(r["features"])].sigmoid().cpu(),
                 "actions_supported":state["auxiliary_weights"][0]["enabled"],"objects_supported":state["auxiliary_weights"][1]["enabled"]} for n,r in enumerate(rows)]
        return predictions,frames,rows

    def select(self,folds):
        choices={}
        for arm in self.plan["arms"]:
            predictions=[]
            for fold in folds:
                path=self.fit(fold["train"],arm,self.plan["config"],42)
                predictions.extend(self.predict(path,fold["validation"]))
            threshold=calibrate(predictions)
            bce=float(np.mean([-math.log(max(1e-7,min(1-1e-7,p["score"] if p["truth"] else 1-p["score"]))) for p in predictions]))
            choices[arm]={"arm":arm,"config":self.plan["config"],"threshold":threshold,"metrics":metrics(predictions,threshold),"bce":bce,"oof":predictions}
        return choices,max(choices.values(),key=rank)


def run(directory,device="cuda"):
    torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
    experiment=Experiment(directory,device);output=Path(directory)
    if (output/"complete.json").exists():raise ValueError("completed experiment is immutable")
    result={arm:{str(s):[] for s in SEEDS} for arm in ARMS};nested={str(s):[] for s in SEEDS};fold_reports=[]
    auxiliary={arm:[] for arm in ARMS};aux_rows={arm:{} for arm in ARMS}
    for number,fold in enumerate(experiment.plan["folds"]):
        choices,selected=experiment.select(fold["inner"])
        for arm,choice in choices.items():
            for seed in SEEDS:
                path=experiment.fit(fold["train"],arm,choice["config"],seed)
                predictions,frames,rows=experiment.predict(path,fold["validation"],True)
                predictions=[{**p,"threshold":choice["threshold"],"fold":number,"arm":arm} for p in predictions]
                result[arm][str(seed)].extend(predictions)
                if seed==42:
                    auxiliary[arm].extend(frames);aux_rows[arm].update({r["video_id"]:r for r in rows})
                if arm==selected["arm"]:nested[str(seed)].extend(predictions)
        record={"fold":number,"choices":choices,"selected_arm":selected["arm"],"train":fold["train"],"validation":fold["validation"]}
        fold_reports.append(record);atomic_json(output/f"outer-fold-{number}.json",record)
        print(json.dumps({"outer_fold_done":number,"selected":selected["arm"]}),flush=True)
    choices,selected=experiment.select(experiment.plan["final_inner"])
    path=experiment.fit(experiment.plan["development_ids"],selected["arm"],selected["config"],42)
    decision={"protocol_sha256":experiment.plan["protocol_sha256"],"selected":selected,"fit":str(path.resolve()),"fit_sha256":file_sha256(path),"selection_uses_reserved":False,"production_ready":False}
    atomic_json(output/"frozen_decision.json",decision)
    report={"version":VERSION,"protocol_sha256":experiment.plan["protocol_sha256"],
            "comparisons":{a:{s:summarize(p) for s,p in seeds.items()} for a,seeds in result.items()},
            "nested_selection_metrics":{s:summarize(p) for s,p in nested.items()},"oof_predictions":result,"nested_oof":nested,
            "fold_reports":fold_reports,"final_choices":choices,"frozen_decision":decision,
            "auxiliary_oof":{arm:{"actions":previous.auxiliary_metrics(auxiliary[arm],aux_rows[arm],"actions",inputs.TAXONOMY),
                                  "objects":previous.auxiliary_metrics(auxiliary[arm],aux_rows[arm],"objects",[str(i) for i in previous.OBJECT_IDS])} for arm in ARMS},
            "production_ready":False,"independent_external_test":False,
            "limitations":["Exploratory same-camera sources and previously inspected internal test; not external validation.",
                           "Assistant observations are snapshot labels, not human-approved dense temporal ground truth.",
                           "Original user verdicts and four organizer conflicts retained; OS/identity/transaction claims unobserved.",
                           "Comparisons use grouped outer folds and inner-only thresholds; best arm alone is selection-biased; nested result is primary."]}
    atomic_json(output/"cv_report.json",report)
    atomic_checkpoint(output/"auxiliary_oof.pt",{"format":VERSION,"predictions":auxiliary})
    atomic_json(output/"complete.json",{"report_sha256":file_sha256(output/"cv_report.json"),"decision_sha256":file_sha256(output/"frozen_decision.json")})
    print(json.dumps({"comparisons":report["comparisons"],"nested":report["nested_selection_metrics"],"final_arm":selected["arm"]}),flush=True)
    return report


def raw_row(experiment,source_root,index,video_id,encoder,arm,*,target=0):
    """Same crop/PTS/encoder path for source MOVs and cached training inputs."""
    from ml.data.scenes import define_scenes,sample_scenes
    from ml.video_baseline import encode_source
    row={"video_id":video_id,"target":target,"split":"excluded","group_id":"raw-inference"}
    if arm=="global_joint":
        features,pts=encode_source(source_root,index,define_scenes(index),encoder,experiment.device,"three_crop")
        row.update(features=torch.from_numpy(features),source_pts=pts,actions=torch.full((len(pts),15),-1.),objects=torch.full((len(pts),7),-1.))
    else:
        arrays=inputs.encode_roi(source_root,index,encoder,experiment.device,variants=False)
        positions={int(p):n for n,p in enumerate(arrays["source_pts"])}
        sampled=sample_scenes(index,define_scenes(index),rate=2.)
        two=[s["time"]["source_pts"] for s in sampled]
        row.update(roi_features=torch.from_numpy(arrays["features"]),prefix=torch.from_numpy(arrays["prefix"]),
                   roi_pts=arrays["source_pts"],roi2_indices=torch.tensor([positions[p] for p in two]),
                   roi_actions=torch.full((len(positions),15),-1.),roi_objects=torch.full((len(positions),7),-1.))
    return row


def frozen_decision(directory):
    output=Path(directory);marker=read_json(output/"complete.json")
    if (file_sha256(output/"frozen_decision.json")!=marker["decision_sha256"]
            or file_sha256(output/"cv_report.json")!=marker["report_sha256"]):
        raise ValueError("frozen report/decision changed")
    decision=read_json(output/"frozen_decision.json")
    if file_sha256(decision["fit"])!=decision["fit_sha256"]:
        raise ValueError("selected weights changed")
    return decision


def evaluate_reserved(directory,device="cuda"):
    from ml.data.manifest import local_source,source_hash
    output=Path(directory)
    if (output/"reserved_report.json").exists():raise ValueError("reserved diagnostic already completed")
    decision=frozen_decision(directory);torch.set_num_threads(4)
    experiment=Experiment(directory,device)
    encoder=FrozenEncoder(weights_path=Path(read_json(Path(experiment.plan["focus"])/"inputs.json")["encoder_weights"]),
                          weights_sha256=experiment.document["encoder"]["weights_sha256"]).to(device).eval()
    prepared=Path(experiment.document["prepared_dir"])
    source_root=Path(read_json(prepared/"readiness.json")["source_root"])
    latencies=[]
    for video in experiment.plan["reserved_ids"]:
        index=read_json(prepared/"indices"/(video+".json"))
        if source_hash(local_source(source_root,index["path"]),2*1024**3)!=index["source_sha256"]:
            raise ValueError("reserved source changed")
        started=time.perf_counter()
        row=raw_row(experiment,source_root,index,video,encoder,decision["selected"]["arm"],target=experiment.by_id[video]["target"])
        experiment.by_id[video]=row
        prediction=experiment.predict(decision["fit"],[video])[0]
        latencies.append({**prediction,"elapsed_seconds":time.perf_counter()-started})
    report={"role":"previously_observed_internal_holdout","threshold":decision["selected"]["threshold"],"predictions":latencies,
            "metrics":metrics(latencies,decision["selected"]["threshold"]),"pipeline_mean_seconds_after_encoder_setup":float(np.mean([p["elapsed_seconds"] for p in latencies])),
            "fit_sha256":decision["fit_sha256"],"production_ready":False,"independent_external_test":False}
    atomic_json(output/"reserved_report.json",report);print(json.dumps(report),flush=True)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("prepare")
    for name in ("cache","overlay","compat","focus","output","previous-experiment"):a.add_argument("--"+name,type=Path,required=True)
    a=sub.add_parser("run");a.add_argument("--experiment",type=Path,required=True)
    a=sub.add_parser("evaluate-reserved");a.add_argument("--experiment",type=Path,required=True)
    a=p.parse_args(argv)
    if a.command=="prepare":prepare(a.cache,a.overlay,a.compat,a.focus,a.output,a.previous_experiment)
    elif a.command=="run":run(a.experiment)
    else:evaluate_reserved(a.experiment)
    return 0


if __name__=="__main__":raise SystemExit(main())
