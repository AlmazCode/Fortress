"""Local, experimental action-assisted training on explicitly reviewed source PTS.

Assistant observations remain assistant labels. This does not create a production
event release or legal evidence. Unknown entries never contribute to the loss.
"""
from __future__ import annotations

import argparse
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

from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.manifest import local_source
from ml.models.encoder import file_sha256, safe_torch_load
from ml.small_data import fit_norm, selection_rank, split_folds, summarize
from ml.video_baseline import atomic_checkpoint, atomic_json, calibrate_video, load_feature_cache, metrics

VERSION = "assistant-action-stage-v1"
TAXONOMY = ("flat_item_handling", "counter_interaction", "computer_interaction",
            "storage_interaction", "bag_interaction", "door_interaction", "writing",
            "operator_at_station", "person_at_counter", "storage_open", "bag_on_desk")
OBJECT_IDS = (10, 11, 1, 4, 7, 12, 13)  # key has zero supplied positives; no invented examples
SEEDS = (42, 137, 2026)
GRID = {arm: [{"epochs": 60, "lr": .001, "dropout": .35, "weight_decay": .01},
              {"epochs": 100, "lr": .0003, "dropout": .5, "weight_decay": .05}]
        for arm in ("video_only", "actions", "actions_objects")}
LOSS_WEIGHTS = {"video_only": (0., 0.), "actions": (.3, 0.), "actions_objects": (.3, .15)}


def code_hash():
    base = Path(__file__).parent
    names = ("action_refinement.py", "small_data.py", "video_baseline.py", "models/encoder.py", "preprocessing.py")
    return stable_hash({name: hashlib.sha256((base/name).read_text(encoding="utf-8-sig").encode()).hexdigest()
                        for name in names})


def observation_targets(observations, points, index):
    """Match exact source frames only; there is no interval filling/interpolation."""
    values = torch.full((len(points), len(TAXONOMY)), -1., dtype=torch.float32)
    timing = {f["source_pts"]: f["timestamp_sec"] for f in index["frames"]}
    positions = {int(p): i for i, p in enumerate(points)}
    seen = set()
    for obs in observations:
        pts, target = obs["source_pts"], obs["values"]
        if (type(pts) is not int or pts in seen or pts not in timing
                or abs(obs["timestamp_sec"]-timing[pts]) > 1e-7
                or len(target) != len(TAXONOMY) or any(type(t) is not int or t not in (-1, 0, 1) for t in target)):
            raise ValueError("invalid, duplicate or non-source observation")
        seen.add(pts)
        if pts in positions:
            values[positions[pts]] = torch.tensor(target)
    return values


def load_inputs(cache, overlay):
    cache = Path(cache)
    document, rows = load_feature_cache(cache)
    prepared = Path(document["prepared_dir"])
    review = read_json(overlay)
    if (review["version"] != VERSION or review["taxonomy"] != list(TAXONOMY)
            or review["human_approved"] is not False or review["provenance"] != "assistant_sequence_review"
            or review["original_verdicts_changed"] is not False):
        raise ValueError("unsupported annotation provenance/taxonomy")
    root = Path(overlay).resolve().parent
    reviewed = {}
    for video in review["videos"]:
        if video["video_id"] in reviewed or video["human_approved"] is not False:
            raise ValueError("duplicate review or fabricated human approval")
        reviewed[video["video_id"]] = video
        for evidence in video["evidence"]:
            path = Path(evidence["path"]).resolve(strict=True)
            if not path.is_relative_to(root) or file_sha256(path) != evidence["image_sha256"]:
                raise ValueError("review evidence changed or escaped review directory")
        evidence_pts = {e["source_pts"] for e in video["evidence"]}
        if any(o["source_pts"] not in evidence_pts for o in video["observations"]):
            raise ValueError("observation without inspected evidence")
    by_id = {r["video_id"]: r for r in rows}
    if any(v not in by_id or by_id[v]["split"] not in ("train", "dev_validation") for v in reviewed):
        raise ValueError("reserved/unrecognized source in assistant annotations")
    package = Path(read_json(prepared/"readiness.json")["source_root"])
    objects_path = package/"annotations/objects.coco.json"
    approval_path = package/"fortress_manual_review.completed.json"
    objects, approval = read_json(objects_path), read_json(approval_path)
    if {c["id"] for c in objects["categories"]} != {*OBJECT_IDS, 3}:
        raise ValueError("object taxonomy changed")
    boxes = {}
    for box in objects["annotations"]:
        if (box["category_id"] not in {*OBJECT_IDS, 3} or box["attributes"].get("status") != "user_reviewed"
                or box["attributes"].get("confirmation_basis") != "user_declared_objects_complete"):
            raise ValueError("object provenance changed")
        boxes.setdefault(box["image_id"], []).append(box)
    images = {}
    for img in objects["images"]:
        key = (img["video_id"], img["source_pts"])
        record = approval["objects"].get(str(img["id"]), {})
        if (key in images or img["video_id"] not in by_id or record.get("reviewed") is not True
                or record.get("confirmation_basis") != "user_declared_objects_complete"
                or img["source_sha256"] != by_id[img["video_id"]]["source_sha256"]):
            raise ValueError("object frame/provenance mismatch")
        for box in boxes.get(img["id"], []):
            x, y, w, h = box["bbox"]
            if not all(math.isfinite(t) for t in (x, y, w, h)) or min(x, y) < 0 or min(w, h) <= 0 or x+w > img["width"]+.01 or y+h > img["height"]+.01:
                raise ValueError("invalid supplied object box")
        images[key] = img
    stats = {}
    for row in rows:
        index = read_json(prepared/"indices"/(row["video_id"]+".json"))
        timing = {f["source_pts"]: f["timestamp_sec"] for f in index["frames"]}
        with np.load(local_source(cache, row["path"]), allow_pickle=False) as arrays:
            points = arrays["source_pts"].copy()
        if any(int(p) not in timing for p in points):
            raise ValueError("cached PTS not in source index")
        row["source_pts"] = points
        row["actions"] = torch.full((len(points), len(TAXONOMY)), -1.)
        row["objects"] = torch.full((len(points), len(OBJECT_IDS)), -1.)
        video = reviewed.get(row["video_id"])
        if video:
            if video["source_sha256"] != row["source_sha256"]:
                raise ValueError("review belongs to another source")
            for evidence in video["evidence"]:
                if (evidence["video_id"] != row["video_id"] or evidence["source_sha256"] != row["source_sha256"]
                        or evidence["source_pts"] not in timing
                        or abs(evidence["timestamp_sec"]-timing[evidence["source_pts"]]) > 1e-7):
                    raise ValueError("evidence belongs to another source frame")
            row["actions"] = observation_targets(video["observations"], points, index)
        # Test labels are not even assembled as training tensors.
        if row["split"] in ("train", "dev_validation"):
            for n, pts in enumerate(points):
                img = images.get((row["video_id"], int(pts)))
                if img:
                    if abs(img["timestamp_sec"]-timing[int(pts)]) > 1e-7:
                        raise ValueError("object timestamp/PTS mismatch")
                    present = {b["category_id"] for b in boxes.get(img["id"], [])}
                    row["objects"][n] = torch.tensor([int(c in present) for c in OBJECT_IDS])
        stats[row["video_id"]] = {"action_known": int((row["actions"] >= 0).sum()),
                                  "object_known": int((row["objects"] >= 0).sum())}
    binding = {"overlay_sha256": file_sha256(overlay), "objects_sha256": file_sha256(objects_path),
               "supplied_review_sha256": file_sha256(approval_path), "cache_sha256": stable_hash(document)}
    return document, rows, binding, stats


class ActionGRU(nn.Module):
    """The same single causal GRU256 and video pooling, plus auxiliary heads."""
    def __init__(self, dropout):
        super().__init__()
        self.gru = nn.GRU(576, 256, num_layers=1, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(512, 1)
        self.action_head = nn.Linear(256, len(TAXONOMY))
        self.object_head = nn.Linear(256, len(OBJECT_IDS))

    def forward(self, values, lengths):
        if values.ndim != 3 or values.shape[-1] != 576 or not torch.isfinite(values).all() or len(lengths) != len(values) or (lengths < 1).any() or (lengths > values.shape[1]).any():
            raise ValueError("invalid padded video features")
        packed = pack_padded_sequence(values, lengths.cpu(), batch_first=True, enforce_sorted=False)
        output, _ = self.gru(packed)
        output, _ = pad_packed_sequence(output, batch_first=True, total_length=values.shape[1])
        mask = torch.arange(values.shape[1], device=values.device)[None] < lengths.to(values.device)[:, None]
        mean = output.sum(1)/lengths.to(values.device)[:, None]
        maximum = output.masked_fill(~mask[..., None], -torch.inf).amax(1)
        video = self.head(self.dropout(torch.cat((mean, maximum), -1))).squeeze(-1)
        return video, self.action_head(output), self.object_head(output)


def auxiliary_weights(targets):
    positive, negative = (targets == 1).sum((0, 1)), (targets == 0).sum((0, 1))
    return {"enabled": (positive > 0) & (negative > 0),
            "positive_weight": (negative/positive.clamp_min(1)).clamp(.1, 10.)}


def masked_loss(logits, targets, weights):
    known = (targets >= 0) & weights["enabled"][None, None]
    raw = nn.functional.binary_cross_entropy_with_logits(logits, targets.clamp_min(0), reduction="none",
                                                         pos_weight=weights["positive_weight"])
    count = known.sum((0, 1))
    loss = (raw*known).sum((0, 1))/count.clamp_min(1)
    return (loss*(count > 0)).sum()/(count > 0).sum().clamp_min(1)


def prepare(cache, overlay, output, previous):
    document, rows, binding, stats = load_inputs(cache, overlay)
    old = read_json(Path(previous)/"protocol.json")
    development = [r for r in rows if r["split"] in ("train", "dev_validation")]
    reserved = [r for r in rows if r["split"] == "independent_test"]
    if (sorted(old["development_ids"]) != sorted(r["video_id"] for r in development)
            or sorted(old["reserved_ids"]) != sorted(r["video_id"] for r in reserved)
            or {r["group_id"] for r in development} & {r["group_id"] for r in reserved}):
        raise ValueError("previous split does not match protected development/test families")
    folds = split_folds(development, 4, 20261018)
    lookup = {r["video_id"]: r for r in development}
    for n, fold in enumerate(folds):
        fold["inner"] = split_folds([lookup[v] for v in fold["train"]], 3, 20261018+n+1)
    final_inner = split_folds(development, 3, 20261118)
    if folds != old["folds"] or final_inner != old["final_inner"]:
        raise ValueError("comparison folds changed")
    plan = {"version": VERSION, "cache": str(Path(cache).resolve()), "overlay": str(Path(overlay).resolve()),
            "binding": binding, "code_sha256": code_hash(), "grid": GRID, "loss_weights": LOSS_WEIGHTS,
            "seeds": list(SEEDS), "primary_seed": 42, "folds": folds, "final_inner": final_inner,
            "development_ids": sorted(lookup), "reserved_ids": sorted(r["video_id"] for r in reserved),
            "supervision_counts": stats, "taxonomy": list(TAXONOMY), "object_ids": list(OBJECT_IDS),
            "label_policy": "unchanged user_scenario; four organizer conflicts retained",
            "selection": "inner OOF balanced_accuracy, macro_f1, lower BCE; fixed seed42; inner thresholds only",
            "augmentation": "train only normalized feature Gaussian noise std0.03, same in all three arms",
            "sampling": "all cached 2fps source PTS; action/object targets on exact reviewed frames only",
            "production_ready": False, "independent_external_test": False,
            "runtime": {"torch": str(torch.__version__), "numpy": str(np.__version__)}}
    plan["protocol_sha256"] = stable_hash(plan)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=False)
    atomic_json(destination/"protocol.json", plan)
    with zipfile.ZipFile(destination/"source_snapshot.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for name in ("action_refinement.py", "small_data.py", "video_baseline.py", "models/encoder.py", "preprocessing.py"):
            archive.write(Path(__file__).parent/name, "ml/"+name)
    print(json.dumps({"prepared": str(destination), "protocol_sha256": plan["protocol_sha256"], "supervision": stats}), flush=True)
    return plan


class Experiment:
    def __init__(self, directory, device="cuda"):
        self.directory, self.device = Path(directory), device
        self.plan = read_json(self.directory/"protocol.json")
        bare = {k:v for k,v in self.plan.items() if k != "protocol_sha256"}
        if stable_hash(bare) != self.plan["protocol_sha256"] or self.plan["code_sha256"] != code_hash():
            raise ValueError("protocol/code changed; start a new version")
        self.document, rows, binding, _ = load_inputs(self.plan["cache"], self.plan["overlay"])
        if binding != self.plan["binding"]:
            raise ValueError("dataset/annotations changed")
        self.by_id = {r["video_id"]:r for r in rows}
        self.fits = self.directory/"fits"
        self.fits.mkdir(exist_ok=True)

    def fit(self, ids, arm, config, seed):
        if len(set(ids)) != len(ids) or not set(ids) <= set(self.plan["development_ids"]):
            raise ValueError("only unique development sources may train")
        identity = {"protocol": self.plan["protocol_sha256"], "ids": sorted(ids), "arm": arm, "config": config, "seed": seed}
        path = self.fits/(stable_hash(identity)+".pt")
        if path.exists():
            if safe_torch_load(path)["identity"] != identity:
                raise ValueError("fit identity mismatch")
            return path
        start = time.perf_counter()
        torch.manual_seed(seed)
        if self.device == "cuda":
            torch.cuda.manual_seed_all(seed)
        rows = [self.by_id[v] for v in ids]
        norm = fit_norm(rows)
        values = pad_sequence([(r["features"]-norm["mean"])/norm["std"] for r in rows], batch_first=True).to(self.device)
        lengths = torch.tensor([len(r["features"]) for r in rows])
        target = torch.tensor([r["target"] for r in rows], device=self.device, dtype=torch.float32)
        actions = pad_sequence([r["actions"] for r in rows], batch_first=True, padding_value=-1).to(self.device)
        objects = pad_sequence([r["objects"] for r in rows], batch_first=True, padding_value=-1).to(self.device)
        weights = [auxiliary_weights(t) for t in (actions, objects)]
        model = ActionGRU(config["dropout"]).to(self.device).train()
        optimizer = torch.optim.AdamW(model.parameters(), lr=config["lr"], weight_decay=config["weight_decay"])
        video_loss = nn.BCEWithLogitsLoss(pos_weight=(target == 0).sum()/(target == 1).sum())
        action_weight, object_weight = self.plan["loss_weights"][arm]
        losses = []
        for _ in range(config["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            logits, a, o = model(values + torch.randn_like(values)*.03, lengths)
            components = (video_loss(logits, target), masked_loss(a, actions, weights[0]), masked_loss(o, objects, weights[1]))
            loss = components[0] + action_weight*components[1] + object_weight*components[2]
            if not torch.isfinite(loss):
                raise ValueError("nonfinite training objective")
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
            losses.append([float(v.detach()) for v in components])
        state = {"format": VERSION, "identity": identity, "normalization": norm, "config": config,
                 "arm": arm, "model": {k:v.detach().cpu() for k,v in model.state_dict().items()},
                 "auxiliary_weights": [{k:v.cpu() for k,v in w.items()} for w in weights],
                 "loss_history": losses, "elapsed_seconds": time.perf_counter()-start,
                 "production_ready": False, "human_approved_actions": False}
        atomic_checkpoint(path, state)
        print(json.dumps({"fit": arm, "seed": seed, "videos": len(ids), "seconds": state["elapsed_seconds"], "key": path.stem}), flush=True)
        return path

    def predict(self, path, ids, *, auxiliary=False):
        state = safe_torch_load(path)
        if state["format"] != VERSION or state["identity"]["protocol"] != self.plan["protocol_sha256"]:
            raise ValueError("fit/protocol mismatch")
        model = ActionGRU(state["config"]["dropout"]).to(self.device).eval()
        model.load_state_dict(state["model"], strict=True)
        norm = state["normalization"]
        rows = [self.by_id[v] for v in ids]
        values = pad_sequence([(r["features"]-norm["mean"])/norm["std"] for r in rows], batch_first=True).to(self.device)
        with torch.inference_mode():
            video, a, o = model(values, torch.tensor([len(r["features"]) for r in rows]))
        predictions = [{"video_id":r["video_id"], "truth":bool(r["target"]), "score":float(score)}
                       for r,score in zip(rows, video.sigmoid().cpu())]
        if auxiliary:
            return predictions, [{"video_id":r["video_id"], "actions":a[n,:len(r["features"])].sigmoid().cpu(),
                                  "objects":o[n,:len(r["features"])].sigmoid().cpu(),
                                  "actions_supported":state["auxiliary_weights"][0]["enabled"],
                                  "objects_supported":state["auxiliary_weights"][1]["enabled"]} for n,r in enumerate(rows)]
        return predictions

    def select(self, folds):
        choices = {}
        for arm, configs in self.plan["grid"].items():
            trials = []
            for i, config in enumerate(configs):
                predictions = []
                for fold in folds:
                    fitted = self.fit(fold["train"], arm, config, 42)
                    predictions.extend(self.predict(fitted, fold["validation"]))
                threshold = calibrate_video(predictions, partition="dev_validation")
                bce = float(np.mean([-math.log(max(1e-7, min(1-1e-7, p["score"] if p["truth"] else 1-p["score"]))) for p in predictions]))
                trials.append({"arm":arm, "config":config, "config_index":i, "threshold":threshold,
                               "metrics":metrics(predictions, threshold), "bce":bce, "oof":predictions})
            choices[arm] = max(trials, key=selection_rank)
        return choices, max(choices.values(), key=selection_rank)


def auxiliary_metrics(predictions, by_id, key, names):
    """Fixed 0.5 exploratory frame metrics; unknowns and missing support excluded."""
    result = {}
    for c, name in enumerate(names):
        truth, scores, unsupported = [], [], 0
        for pred in predictions:
            target = by_id[pred["video_id"]][key][:, c]
            known = target >= 0
            if not bool(pred[key+"_supported"][c]):
                unsupported += int(known.sum())
                continue
            truth.extend(target[known].bool().tolist())
            scores.extend(pred[key][known,c].tolist())
        positive, negative = sum(truth), len(truth)-sum(truth)
        if not positive or not negative:
            result[name] = {"positive":positive, "negative":negative, "unsupported_known":unsupported, "metrics":None, "reason":"both classes required"}
        else:
            rows = [{"truth":t, "score":s} for t,s in zip(truth,scores)]
            result[name] = {"positive":positive, "negative":negative, "unsupported_known":unsupported, "metrics":metrics(rows,.5)}
    return result


def run(directory, device="cuda"):
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    experiment = Experiment(directory, device)
    output = Path(directory)
    if (output/"complete.json").exists():
        raise ValueError("completed experiment is immutable")
    result = {arm:{str(seed):[] for seed in SEEDS} for arm in GRID}
    auxiliary = {arm:[] for arm in GRID}
    nested = {str(seed):[] for seed in SEEDS}
    reports = []
    for n, fold in enumerate(experiment.plan["folds"]):
        choices, selected = experiment.select(fold["inner"])
        for arm, choice in choices.items():
            for seed in SEEDS:
                fitted = experiment.fit(fold["train"], arm, choice["config"], seed)
                predictions, frames = experiment.predict(fitted, fold["validation"], auxiliary=True)
                predictions = [{**p, "threshold":choice["threshold"], "fold":n, "arm":arm} for p in predictions]
                result[arm][str(seed)].extend(predictions)
                if seed == 42:
                    auxiliary[arm].extend(frames)
                if arm == selected["arm"]:
                    nested[str(seed)].extend(predictions)
        record = {"fold":n, "choices":choices, "selected_arm":selected["arm"], "train":fold["train"], "validation":fold["validation"]}
        reports.append(record)
        atomic_json(output/f"outer-fold-{n}.json", record)
        print(json.dumps({"outer_fold_done":n, "selected":selected["arm"]}), flush=True)
    choices, selected = experiment.select(experiment.plan["final_inner"])
    fitted = experiment.fit(experiment.plan["development_ids"], selected["arm"], selected["config"], 42)
    decision = {"protocol_sha256":experiment.plan["protocol_sha256"], "selected":selected, "fit":str(fitted.resolve()),
                "fit_sha256":file_sha256(fitted), "selection_uses_reserved":False, "production_ready":False}
    atomic_json(output/"frozen_decision.json", decision)
    report = {"version":VERSION, "protocol_sha256":experiment.plan["protocol_sha256"],
              "comparisons":{arm:{seed:summarize(rows) for seed,rows in seeds.items()} for arm,seeds in result.items()},
              "nested_selection_metrics":{seed:summarize(rows) for seed,rows in nested.items()},
              "oof_predictions":result, "nested_oof":nested, "fold_reports":reports, "final_choices":choices,
              "auxiliary_oof":{arm:{"actions":auxiliary_metrics(pred,experiment.by_id,"actions",TAXONOMY),
                                     "objects":auxiliary_metrics(pred,experiment.by_id,"objects",[str(i) for i in OBJECT_IDS])}
                               for arm,pred in auxiliary.items()},
              "frozen_decision":decision, "production_ready":False, "independent_external_test":False,
              "limitations":["Exploratory same-camera data already examined, assistant labels selected using prior train errors.",
                             "Reviewed snapshots are not dense temporal gold; exact observed PTS only, other entries unknown.",
                             "Normative/system/identity claims are not supervised visual facts; original verdict conflicts retained.",
                             "Auxiliary OOF measures agreement with assistant/supplied annotations, not human validation.",
                             "Previously observed internal test cannot establish new independent 95% performance."]}
    atomic_json(output/"cv_report.json", report)
    atomic_checkpoint(output/"auxiliary_oof.pt", {"format":VERSION,"predictions":auxiliary})
    atomic_json(output/"complete.json", {"report_sha256":file_sha256(output/"cv_report.json"), "decision_sha256":file_sha256(output/"frozen_decision.json")})
    print(json.dumps({"comparisons":report["comparisons"], "nested":report["nested_selection_metrics"], "final_arm":selected["arm"]}), flush=True)
    return report


def evaluate_reserved(directory, device="cuda"):
    output = Path(directory)
    if (output/"reserved_report.json").exists():
        raise ValueError("reserved diagnostic already completed")
    marker = read_json(output/"complete.json")
    if file_sha256(output/"frozen_decision.json") != marker["decision_sha256"] or file_sha256(output/"cv_report.json") != marker["report_sha256"]:
        raise ValueError("decision/report changed")
    decision = read_json(output/"frozen_decision.json")
    if file_sha256(decision["fit"]) != decision["fit_sha256"]:
        raise ValueError("selected fit changed")
    torch.set_num_threads(4)
    experiment = Experiment(output, device)
    predictions = experiment.predict(decision["fit"], experiment.plan["reserved_ids"])
    report = {"role":"previously_observed_internal_holdout", "threshold":decision["selected"]["threshold"],
              "predictions":predictions, "metrics":metrics(predictions,decision["selected"]["threshold"]),
              "production_ready":False, "independent_external_test":False, "decision_sha256":marker["decision_sha256"]}
    atomic_json(output/"reserved_report.json", report)
    print(json.dumps(report), flush=True)
    return report


def infer_video(directory, video, *, weights, weights_sha256, device="cuda"):
    """Raw local-video diagnostic with the frozen decision and source timestamps."""
    from ml.data.manifest import probe_video, source_hash
    from ml.data.pts_index import build_index
    from ml.data.scenes import define_scenes
    from ml.models import FrozenEncoder
    from ml.video_baseline import encode_source
    started = time.perf_counter()
    output = Path(directory)
    marker = read_json(output/"complete.json")
    if file_sha256(output/"frozen_decision.json") != marker["decision_sha256"]:
        raise ValueError("decision changed")
    decision = read_json(output/"frozen_decision.json")
    if file_sha256(decision["fit"]) != decision["fit_sha256"]:
        raise ValueError("selected fit changed")
    torch.set_num_threads(4)
    experiment = Experiment(directory, device)
    if experiment.document["encoder"]["weights_sha256"] != weights_sha256:
        raise ValueError("encoder weights mismatch")
    source = Path(video).resolve(strict=True)
    digest = source_hash(source,2*1024**3)
    metadata, _ = probe_video(source)
    if metadata["duration_sec"] > 180:
        raise ValueError("video exceeds duration budget")
    row = {"video_id":"inference-"+digest[:24], "path":source.name, "sha256":digest,
           "canonical_id":"sha256:"+digest, "group_id":"sha256:"+digest,
           "scene_id":"raw-unreviewed", "split":"excluded", "official_label":None,
           "provenance":{"kind":"original","source_id":digest,"sha256":digest}, **metadata}
    index = build_index(source.parent,row,dataset_version="raw-inference-v1",split_version="not-training")
    encoder = FrozenEncoder(weights_path=weights,weights_sha256=weights_sha256).to(device).eval()
    features, points = encode_source(source.parent,index,define_scenes(index),encoder,device,experiment.document["views"]["mode"])
    row.update({"features":torch.from_numpy(features),"target":0})
    experiment.by_id[row["video_id"]] = row
    predictions, auxiliary = experiment.predict(decision["fit"],[row["video_id"]],auxiliary=True)
    pred, frames = predictions[0], auxiliary[0]
    timing = {f["source_pts"]:f["timestamp_sec"] for f in index["frames"]}
    threshold = decision["selected"]["threshold"]
    return {"source_sha256":digest,"score":pred["score"],"threshold":threshold,
            "prediction":"violation" if pred["score"] >= threshold else "no_violation",
            "elapsed_seconds":time.perf_counter()-started,"model_sha256":decision["fit_sha256"],
            "production_ready":False,"event_intervals_validated":False,"action_scores_are_assistant_agreement":True,
            "frames":[{"source_pts":int(pts),"timestamp_sec":timing[int(pts)],
                       "scores":{name:float(score) if bool(frames["actions_supported"][c]) and decision["selected"]["arm"] != "video_only" else None
                                 for c,(name,score) in enumerate(zip(TAXONOMY,frames["actions"][n]))}}
                      for n,pts in enumerate(points)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    children = parser.add_subparsers(dest="command",required=True)
    p = children.add_parser("prepare")
    for name in ("cache", "overlay", "output", "previous"):
        p.add_argument("--"+name,type=Path,required=True)
    for name in ("run", "evaluate-reserved", "infer"):
        p = children.add_parser(name)
        p.add_argument("--experiment",type=Path,required=True)
        p.add_argument("--device",choices=("cpu","cuda"),default="cuda")
        if name == "infer":
            p.add_argument("--video",type=Path,required=True)
            p.add_argument("--encoder-weights",type=Path,required=True)
            p.add_argument("--encoder-sha256",required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.cache,args.overlay,args.output,args.previous)
    elif args.command == "infer":
        print(json.dumps(infer_video(args.experiment,args.video,weights=args.encoder_weights,
                                    weights_sha256=args.encoder_sha256,device=args.device)))
    else:
        (run if args.command == "run" else evaluate_reserved)(args.experiment,args.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
