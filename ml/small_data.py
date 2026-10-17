"""Local small-data experiments; grouped nested CV, never a production release.

Run ``python -m ml.small_data --help``. The immutable protocol precedes training.
Only train/dev enter CV. Existing internal-test families remain reserved.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import platform
import time
import zipfile

import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
import torch
from torch import nn
from torch.nn.utils.rnn import pad_sequence

from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.manifest import local_source, probe_video, source_hash
from ml.data.pts_index import build_index, iter_indexed_frames
from ml.data.scenes import define_scenes, sample_scenes
from ml.models import FrozenEncoder
from ml.models.encoder import file_sha256, safe_torch_load
from ml.video_baseline import (VerdictGRU, atomic_checkpoint, atomic_json, calibrate_video,
                               input_views, load_feature_cache, metrics)

VERSION = "small-data-nested-v1"
SEEDS = (42, 137, 2026)
MAX_FRAMES = 64
GRID = {
    "linear": [{"c": c} for c in (.01, .1, 1.)],
    "gru": [{"epochs": 40, "lr": .001, "dropout": .2, "weight_decay": .01},
            {"epochs": 80, "lr": .0003, "dropout": .35, "weight_decay": .01}],
    "mil": [{"epochs": 80, "lr": .001, "dropout": .2, "weight_decay": .01},
            {"epochs": 120, "lr": .0003, "dropout": .35, "weight_decay": .05}],
    "finetune": [{"epochs": 40, "lr": .001, "dropout": .2, "weight_decay": .01,
                  "adapt_epochs": epochs, "backbone_lr": lr, "head_lr": .0003}
                 for epochs, lr in ((15, .0001), (30, .0003))],
}


def training_source(source):
    """Fingerprint training semantics independently of inference/CLI and newlines."""
    ignored = {"training_source", "legacy_code_matches", "code_hash", "load_protocol", "infer_video", "main"}
    tree = ast.parse(source)
    tree.body = [node for node in tree.body
                 if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ignored)
                 and not (isinstance(node, ast.Import) and all(alias.name in ("ast", "hashlib", "zipfile") for alias in node.names))]
    return ast.dump(tree, include_attributes=False)


def code_hash():
    base = Path(__file__).parent
    return stable_hash({name: hashlib.sha256((training_source((base/name).read_text(encoding="utf-8-sig"))
                       if name == "small_data.py" else (base/name).read_text(encoding="utf-8-sig")).encode()).hexdigest()
                       for name in ("small_data.py", "video_baseline.py", "models/encoder.py", "preprocessing.py")})


def legacy_code_matches(directory, expected):
    """Verify an old byte-bound snapshot, then allow only inference/CLI fixes.

    The archive is parsed as text, never executed or extracted. Training AST and
    the three dependencies must match. No protocol, fit identity or metric changes.
    """
    archive_path = Path(directory) / "source_snapshot.zip"
    if not archive_path.is_file():
        return False
    names = ("small_data.py", "video_baseline.py", "models/encoder.py", "preprocessing.py")
    base = Path(__file__).parent
    try:
        with zipfile.ZipFile(archive_path) as archive:
            if set(archive.namelist()) != {"ml/"+name for name in names} or sum(i.file_size for i in archive.infolist()) > 1024**2:
                return False
            old = {name: archive.read("ml/"+name) for name in names}
        if stable_hash({name: hashlib.sha256(data).hexdigest() for name, data in old.items()}) != expected:
            return False
        for name in names:
            previous = old[name].decode("utf-8-sig").replace("\r\n", "\n")
            current = (base/name).read_text(encoding="utf-8-sig")
            if (training_source(previous) != training_source(current) if name == "small_data.py" else previous != current):
                return False
        return True
    except (OSError, ValueError, SyntaxError, zipfile.BadZipFile):
        return False


def prefix_views(prefix, batch):
    # Preserve the baseline's per-view convolution batch layout, including TF32 rounding.
    return torch.stack([prefix(batch[:, view].contiguous()) for view in range(batch.shape[1])], dim=1)


def split_folds(rows, count, seed):
    """One source/family stays together; reject unusable folds rather than leak."""
    if len({r["video_id"] for r in rows}) != len(rows) or len({r["source_sha256"] for r in rows}) != len(rows):
        raise ValueError("duplicate source/video in CV")
    if any(r["split"] not in ("train", "dev_validation") for r in rows):
        raise ValueError("reserved/excluded data cannot enter CV")
    splitter = StratifiedGroupKFold(n_splits=count, shuffle=True, random_state=seed)
    y = [r["target"] for r in rows]
    groups = [r["group_id"] for r in rows]
    result = []
    for training, validation in splitter.split(np.zeros(len(rows)), y, groups):
        train_rows, val_rows = [rows[i] for i in training], [rows[i] for i in validation]
        if ({r["group_id"] for r in train_rows} & {r["group_id"] for r in val_rows}
                or any({r["target"] for r in part} != {0, 1} for part in (train_rows, val_rows))):
            raise ValueError("CV fold lacks a class or splits a family")
        result.append({"train": [r["video_id"] for r in train_rows], "validation": [r["video_id"] for r in val_rows]})
    if sorted(v for fold in result for v in fold["validation"]) != sorted(r["video_id"] for r in rows):
        raise ValueError("OOF coverage is not exactly once per video")
    return result


def fit_norm(rows):
    if not rows or {r["target"] for r in rows} != {0, 1}:
        raise ValueError("training needs both verdict classes")
    if any(r["split"] == "independent_test" for r in rows):
        raise ValueError("test data in training normalization")
    frames = torch.cat([r["features"] for r in rows])
    return {"mean": frames.mean(0), "std": frames.std(0, unbiased=False).clamp_min(.01)}


def frame_selection(length, *, rng=None):
    if length < 1:
        raise ValueError("empty video")
    if length <= MAX_FRAMES:
        return np.arange(length)
    if rng is None:
        return np.linspace(0, length - 1, MAX_FRAMES).round().astype(np.int64)
    edges = np.linspace(0, length, MAX_FRAMES + 1).astype(np.int64)
    return np.asarray([rng.integers(a, b) for a, b in zip(edges, edges[1:])])


def pooled(values):
    return torch.cat((values.mean(0), values.amax(0)))


def window_tokens(values):
    """4-second windows, 2-second stride; bag labels never become clip truth."""
    starts = list(range(0, max(1, len(values) - 7), 4))
    tail = max(0, len(values) - 8)
    if tail not in starts:
        starts.append(tail)
    return torch.stack([torch.cat((pooled(values[s:s+8]), values[min(s+7, len(values)-1)] - values[s])) for s in starts])


class WindowMIL(nn.Module):
    def __init__(self, dropout):
        super().__init__()
        self.head = nn.Sequential(nn.Linear(1728, 128), nn.ReLU(), nn.Dropout(dropout), nn.Linear(128, 1))

    def forward(self, tokens, lengths):
        logits = self.head(tokens).squeeze(-1)
        mask = torch.arange(tokens.shape[1], device=tokens.device)[None] < lengths.to(tokens.device)[:, None]
        # A video is one bag. No pseudo temporal labels or legal evidence are emitted.
        return torch.logsumexp(logits.masked_fill(~mask, -torch.inf), 1) - lengths.to(tokens.device).log()


def prepare(cache, output, *, audit_report, outer=4, inner=3, split_seed=20261018):
    document, rows = load_feature_cache(cache)
    development = [r for r in rows if r["split"] in ("train", "dev_validation")]
    reserved = [r for r in rows if r["split"] == "independent_test"]
    if {r["group_id"] for r in development} & {r["group_id"] for r in reserved}:
        raise ValueError("reserved family overlaps development")
    folds = split_folds(development, outer, split_seed)
    lookup = {r["video_id"]: r for r in development}
    for n, fold in enumerate(folds):
        fold["inner"] = split_folds([lookup[v] for v in fold["train"]], inner, split_seed+n+1)
    final_inner = split_folds(development, inner, split_seed+100)
    record = {"version": VERSION, "cache": str(Path(cache).resolve()), "cache_sha256": stable_hash(document),
              "code_sha256": code_hash(), "grid": GRID, "training_seeds": list(SEEDS), "selection_seed": 42,
              "max_frames": MAX_FRAMES, "folds": folds, "final_inner": final_inner,
              "development_ids": sorted(lookup), "reserved_ids": sorted(r["video_id"] for r in reserved),
              "label_policy": "Preserve supplied user_scenario verdicts; organizer conflicts remain unresolved.",
              "selection": "inner OOF balanced_accuracy, macro_f1, lower unweighted BCE; deterministic config order",
              "threshold": "inner-OOF score midpoints only, primary seed42; same threshold for seed sensitivity",
              "augmentation": "train only: order-preserving temporal bin jitter and brightness 0.85/1.15 for finetune",
              "production_ready": False, "independent_external_test": False,
              "runtime": {"torch": str(torch.__version__), "sklearn": sklearn.__version__, "python": platform.python_version()}}
    record["protocol_sha256"] = stable_hash(record)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "protocol.json", record)
    labels = read_json(Path(document["prepared_dir"]) / "labels.json")["videos"]
    baseline = read_json(audit_report)
    errors = [r for r in baseline["videos"] if r["duplicate_of"] is None and r["split"] == "train" and not r["correct"]]
    package = Path(read_json(Path(document["prepared_dir"]) / "readiness.json")["source_root"])
    actions = read_json(package / "annotations/actions.json")["annotations"]
    weak = read_json(package / "annotations/violations_weak.json")["annotations"]
    queue = []
    for row in labels:
        if row["split"] == "test":
            continue
        error = next((e for e in errors if e["video_id"] == row["video_id"]), None)
        if error or row["verdict_conflict"]:
            queue.append({"video_id": row["video_id"], "source_file": row["source_file"],
                          "source_sha256": row["source_sha256"], "source_video": str(package / row["video_path"]),
                          "user_verdict": row["verdict"], "organizer_verdict": row["organizer_verdict"],
                          "conflict": row["verdict_conflict"], "baseline_error": error,
                          "violation_types": row["violation_types"], "human_approved": False,
                          "status": "needs_visual_and_scenario_review", "verdict_changed": False,
                          "questions": ["Is the decisive event actually visible?", "Which interval proves it?",
                                        "Is missing pre-roll/occlusion being mistaken for absence?",
                                        "For conflicts, what is the authoritative scenario interpretation?"],
                          "action_proposals": [a for a in actions if a["video_id"] == row["video_id"]],
                          "weak_scenario_intervals": [a for a in weak if a["video_id"] == row["video_id"]]})
    atomic_json(output / "review_tasks.json", {"version": VERSION, "original_labels_unchanged": True,
                "proposals_are_not_gold": True, "training_error_count": len(errors),
                "conflict_count": sum(r["verdict_conflict"] for r in labels), "tasks": queue})
    print(json.dumps({"prepared": str(output), "development_videos": len(development), "reserved_videos": len(reserved),
                      "review_tasks": len(queue), "protocol_sha256": record["protocol_sha256"]}), flush=True)
    return record


def load_protocol(directory):
    plan = read_json(Path(directory) / "protocol.json")
    digest = plan.pop("protocol_sha256")
    if (stable_hash(plan) != digest or plan["version"] != VERSION
            or plan["code_sha256"] != code_hash() and not legacy_code_matches(directory, plan["code_sha256"])):
        raise ValueError("protocol/code changed; use a new experiment directory")
    plan["protocol_sha256"] = digest
    document, rows = load_feature_cache(plan["cache"])
    if stable_hash(document) != plan["cache_sha256"]:
        raise ValueError("input cache changed")
    return plan, document, rows


def make_prefix_cache(directory, plan, document, rows, weights, digest, device):
    """Frozen prefix can be cached before CV; no labels/BN fitting enter it."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    encoder = FrozenEncoder(weights_path=weights, weights_sha256=digest).to(device).eval()
    prefix, suffix = encoder.features[:-2], encoder.features[-2:]
    key = stable_hash({"protocol": plan["protocol_sha256"], "weights": digest, "prefix": "features[:-2]", "factors": [1., .85, 1.15]})
    marker_path = directory / "index.json"
    marker = read_json(marker_path) if marker_path.exists() else {"key": key, "entries": {}}
    if marker["key"] != key:
        raise ValueError("prefix cache belongs to another protocol")
    source_root = Path(read_json(Path(document["prepared_dir"]) / "readiness.json")["source_root"])
    mean = torch.tensor([.485, .456, .406], device=device)[None, :, None, None]
    std = torch.tensor([.229, .224, .225], device=device)[None, :, None, None]
    for row in rows:
        destination = directory / (row["video_id"] + ".npz")
        previous = marker["entries"].get(row["video_id"])
        if previous and destination.exists() and file_sha256(destination) == previous["sha256"]:
            continue
        if destination.exists():
            raise ValueError("unverified existing prefix file")
        index = read_json(Path(document["prepared_dir"]) / "indices" / (row["video_id"] + ".json"))
        selected = {s["time"]["source_pts"] for s in sample_scenes(index, define_scenes(index), rate=2.)}
        views, points = [], []
        arrays = {"base": [], "dark": [], "bright": []}

        def flush():
            if not views:
                return
            batch = torch.stack(views).to(device)
            for name, factor in (("base", 1.), ("dark", .85), ("bright", 1.15)):
                pixels = batch if factor == 1 else (((batch * std + mean) * factor).clamp(0, 1) - mean) / std
                arrays[name].append(prefix_views(prefix, pixels).cpu().numpy())
            views.clear()

        with torch.inference_mode():
            for timing, frame in iter_indexed_frames(source_root, index):
                if timing["source_pts"] in selected:
                    views.append(input_views(frame.to_image(), index["rotation"], document["views"]["mode"]))
                    points.append(timing["source_pts"])
                    if len(views) == 16:
                        flush()
            flush()
        values = {name: np.concatenate(chunks) for name, chunks in arrays.items()}
        if len(points) != len(row["features"]) or len(points) != len(selected):
            raise ValueError("prefix/sample frame mismatch")
        with torch.inference_mode():
            base = torch.from_numpy(values["base"]).to(device)
            chunks = [torch.stack([suffix(v[:, view].contiguous()).mean((-2, -1))
                                  for view in range(v.shape[1])], 1).mean(1) for v in base.split(16)]
            rebuilt = torch.cat(chunks).cpu()
            delta = float((rebuilt - row["features"]).abs().max())
            if not torch.allclose(rebuilt, row["features"], atol=1e-4, rtol=1e-4):
                raise ValueError("frozen prefix changes cached feature semantics")
        with destination.open("xb") as stream:
            np.savez_compressed(stream, **values, source_pts=np.asarray(points, dtype=np.int64))
        marker["entries"][row["video_id"]] = {"sha256": file_sha256(destination), "source_sha256": row["source_sha256"],
                                                "max_feature_reconstruction_delta": delta}
        atomic_json(marker_path, marker)
        print(json.dumps({"prefix_cached": row["video_id"], "frames": len(points), "feature_delta": delta}), flush=True)
    return marker


def normalize_rows(rows, norm, arm):
    values = [(r["features"] - norm["mean"]) / norm["std"] for r in rows]
    if arm == "linear":
        return torch.stack([pooled(v) for v in values])
    if arm == "mil":
        return [window_tokens(v) for v in values]
    return [v[frame_selection(len(v))] for v in values]


def construct(arm, config, device):
    return (WindowMIL(config["dropout"]) if arm == "mil" else VerdictGRU(config["dropout"])).to(device)


class Experiment:
    def __init__(self, directory, *, weights, weights_sha256, device="cuda"):
        self.directory = Path(directory)
        self.plan, self.document, self.rows = load_protocol(directory)
        self.by_id = {r["video_id"]: r for r in self.rows}
        self.weights, self.weights_sha, self.device = Path(weights), weights_sha256, device
        if self.document["encoder"]["weights_sha256"] != weights_sha256 or file_sha256(self.weights) != weights_sha256:
            raise ValueError("experiment encoder weights mismatch")
        self.prefix = {}
        self.suffix_template = None
        self.prefix_marker = None
        self.fits = self.directory / "fits"
        self.fits.mkdir(exist_ok=True)

    def load_prefix(self, ids):
        rows = [self.by_id[v] for v in ids]
        marker = make_prefix_cache(self.directory / "prefix", self.plan, self.document, rows,
                                   self.weights, self.weights_sha, self.device)
        self.prefix_marker = marker
        for video_id in ids:
            if video_id in self.prefix:
                continue
            path = self.directory / "prefix" / (video_id + ".npz")
            if file_sha256(path) != marker["entries"][video_id]["sha256"]:
                raise ValueError("prefix bytes changed")
            with np.load(path, allow_pickle=False) as data:
                self.prefix[video_id] = {name: torch.from_numpy(data[name].copy()) for name in ("base", "dark", "bright")}
        if self.suffix_template is None:
            encoder = FrozenEncoder(weights_path=self.weights, weights_sha256=self.weights_sha)
            self.suffix_template = copy.deepcopy(encoder.features[-2:])

    def fit(self, ids, arm, config, seed):
        rows = [self.by_id[v] for v in ids]
        if not set(ids) <= set(self.plan["development_ids"]) or len(set(ids)) != len(ids):
            raise ValueError("only unique development videos may train")
        identity = {"protocol": self.plan["protocol_sha256"], "ids": sorted(ids), "arm": arm, "config": config, "seed": seed}
        key = stable_hash(identity)
        path = self.fits / (key + ".pt")
        if path.exists():
            existing = safe_torch_load(path)
            if existing["identity"] != identity:
                raise ValueError("fit identity mismatch")
            return path
        started = time.perf_counter()
        torch.manual_seed(seed)
        if self.device == "cuda":
            torch.cuda.manual_seed_all(seed)
        rng = np.random.default_rng(seed)
        norm = fit_norm(rows)
        values = normalize_rows(rows, norm, arm)
        target = torch.tensor([r["target"] for r in rows], dtype=torch.float32, device=self.device)
        result = {"identity": identity, "normalization": norm, "arm": arm, "config": config,
                  "threshold_fitted": False, "format": VERSION, "weights_sha256": self.weights_sha}
        if arm == "linear":
            center = values.mean(0)
            scale = values.std(0, unbiased=False).clamp_min(.01)
            classifier = LogisticRegression(C=config["c"], class_weight="balanced", max_iter=1000, random_state=seed)
            classifier.fit(((values-center)/scale).numpy(), target.cpu().numpy())
            result.update({"coef": torch.from_numpy(classifier.coef_.astype(np.float32)),
                           "intercept": torch.from_numpy(classifier.intercept_.astype(np.float32)),
                           "pool_mean": center, "pool_std": scale})
        else:
            model = construct(arm, config, self.device)
            data = pad_sequence(values, batch_first=True).to(self.device)
            lengths = torch.tensor([len(v) for v in values])
            positive_weight = (target == 0).sum() / (target == 1).sum()
            loss_fn = nn.BCEWithLogitsLoss(pos_weight=positive_weight)
            optimizer = torch.optim.AdamW(model.parameters(), lr=config["lr"], weight_decay=config["weight_decay"])
            losses = []
            model.train()
            for _ in range(config["epochs"]):
                optimizer.zero_grad(set_to_none=True)
                loss = loss_fn(model(data, lengths), target)
                if not torch.isfinite(loss):
                    raise ValueError("nonfinite training loss")
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.)
                optimizer.step()
                losses.append(float(loss.detach()))
            if arm == "finetune":
                if not all(v in self.prefix for v in ids):
                    raise ValueError("prepare frozen-prefix inputs before fine-tuning")
                suffix = copy.deepcopy(self.suffix_template).to(self.device).eval().requires_grad_(True)
                optimizer = torch.optim.AdamW([{"params": suffix.parameters(), "lr": config["backbone_lr"]},
                                                {"params": model.parameters(), "lr": config["head_lr"]}], weight_decay=config["weight_decay"])
                for _ in range(config["adapt_epochs"]):
                    optimizer.zero_grad(set_to_none=True)
                    epoch_loss = 0.
                    # Accumulate a full-video-bag objective with bounded CNN activation memory.
                    for start in range(0, len(rows), 3):
                        selected_rows = rows[start:start+3]
                        adapted = []
                        for row in selected_rows:
                            variant = ("base", "dark", "bright")[int(rng.integers(3))]
                            source = self.prefix[row["video_id"]][variant]
                            selected = source[frame_selection(len(source), rng=rng)].to(self.device)
                            chunks = [suffix(v).mean((-2, -1)) for v in selected.flatten(0, 1).split(64)]
                            features = torch.cat(chunks).reshape(len(selected), selected.shape[1], 576).mean(1)
                            adapted.append((features - norm["mean"].to(self.device)) / norm["std"].to(self.device))
                        loss = loss_fn(model(pad_sequence(adapted, batch_first=True), torch.tensor([len(v) for v in adapted])), target[start:start+3])
                        if not torch.isfinite(loss):
                            raise ValueError("nonfinite fine-tuning loss")
                        scaled = loss * (len(selected_rows) / len(rows))
                        scaled.backward()
                        epoch_loss += float(scaled.detach())
                    nn.utils.clip_grad_norm_([*suffix.parameters(), *model.parameters()], 1.)
                    optimizer.step()
                    losses.append(epoch_loss)
                result["suffix"] = {k: v.detach().cpu() for k, v in suffix.state_dict().items()}
                result["prefix_inputs"] = {v: self.prefix_marker["entries"][v]["sha256"] for v in sorted(ids)}
            result["model"] = {k: v.detach().cpu() for k, v in model.state_dict().items()}
            result["first_loss"], result["last_loss"] = losses[0], losses[-1]
        result["elapsed_seconds"] = time.perf_counter() - started
        atomic_checkpoint(path, result)
        print(json.dumps({"fit": arm, "videos": len(ids), "seed": seed, "seconds": result["elapsed_seconds"], "key": key}), flush=True)
        return path

    def predict(self, path, ids):
        state = safe_torch_load(path)
        if state["format"] != VERSION or state["identity"]["protocol"] != self.plan["protocol_sha256"]:
            raise ValueError("fit/protocol mismatch")
        rows = [self.by_id[v] for v in ids]
        norm, arm = state["normalization"], state["arm"]
        with torch.inference_mode():
            if arm == "linear":
                features = normalize_rows(rows, norm, arm)
                result = (((features-state["pool_mean"])/state["pool_std"]) @ state["coef"].T + state["intercept"]).squeeze(1).sigmoid().tolist()
            else:
                model = construct(arm, state["config"], self.device)
                model.load_state_dict(state["model"], strict=True)
                model.eval()
                if arm == "finetune":
                    suffix = copy.deepcopy(self.suffix_template).to(self.device).eval()
                    suffix.load_state_dict(state["suffix"], strict=True)
                    values = []
                    for row in rows:
                        source = self.prefix[row["video_id"]]["base"]
                        selected = source[frame_selection(len(source))].to(self.device)
                        features = torch.cat([suffix(v).mean((-2, -1)) for v in selected.flatten(0, 1).split(64)])
                        features = features.reshape(len(selected), selected.shape[1], 576).mean(1)
                        values.append((features - norm["mean"].to(self.device)) / norm["std"].to(self.device))
                else:
                    values = normalize_rows(rows, norm, arm)
                result = model(pad_sequence(values, batch_first=True).to(self.device), torch.tensor([len(v) for v in values])).sigmoid().cpu().tolist()
        return [{"video_id": row["video_id"], "truth": bool(row["target"]), "score": float(score)} for row, score in zip(rows, result)]

    def select(self, folds):
        selections = {}
        for arm, configurations in self.plan["grid"].items():
            trials = []
            for index, config in enumerate(configurations):
                oof = []
                for fold in folds:
                    fitted = self.fit(fold["train"], arm, config, self.plan["selection_seed"])
                    oof.extend(self.predict(fitted, fold["validation"]))
                threshold = calibrate_video(oof, partition="dev_validation")
                measured = metrics(oof, threshold)
                bce = float(np.mean([-math.log(max(1e-7, min(1-1e-7, r["score"] if r["truth"] else 1-r["score"]))) for r in oof]))
                trials.append({"arm": arm, "config": config, "config_index": index, "threshold": threshold,
                               "metrics": measured, "bce": bce, "oof": oof})
            selections[arm] = max(trials, key=selection_rank)
        return selections, max(selections.values(), key=selection_rank)


def selection_rank(trial):
    return (trial["metrics"]["balanced_accuracy"], trial["metrics"]["macro_f1"], -trial["bce"], -trial["config_index"])


def summarize(predictions):
    # Each OOF row has its own threshold learned exclusively on its inner folds.
    from ml.evaluate import binary_metrics
    return binary_metrics([r["truth"] for r in predictions], [r["score"] >= r["threshold"] for r in predictions])


def run(directory, *, weights, weights_sha256, device="cuda"):
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    experiment = Experiment(directory, weights=weights, weights_sha256=weights_sha256, device=device)
    output = Path(directory)
    if (output / "complete.json").exists():
        raise ValueError("experiment already completed; preserve its results")
    experiment.load_prefix(experiment.plan["development_ids"])
    results = {arm: {str(seed): [] for seed in SEEDS} for arm in GRID}
    nested = {str(seed): [] for seed in SEEDS}
    fold_reports = []
    for number, fold in enumerate(experiment.plan["folds"]):
        choices, selected = experiment.select(fold["inner"])
        record = {"fold": number, "choices": choices, "nested_selected_arm": selected["arm"], "train": fold["train"], "validation": fold["validation"]}
        for arm, choice in choices.items():
            for seed in SEEDS:
                fitted = experiment.fit(fold["train"], arm, choice["config"], seed)
                predictions = [{**row, "fold": number, "threshold": choice["threshold"], "arm": arm}
                               for row in experiment.predict(fitted, fold["validation"])]
                results[arm][str(seed)].extend(predictions)
                if arm == selected["arm"]:
                    nested[str(seed)].extend(predictions)
        fold_reports.append(record)
        atomic_json(output / f"outer-fold-{number}.json", record)
        print(json.dumps({"outer_fold_done": number, "nested_selected": selected["arm"]}), flush=True)
    comparisons = {arm: {seed: summarize(rows) for seed, rows in per_seed.items()} for arm, per_seed in results.items()}
    nested_metrics = {seed: summarize(rows) for seed, rows in nested.items()}
    # Final family/config/threshold are selected by the same inner-only procedure on all development data.
    choices, selected = experiment.select(experiment.plan["final_inner"])
    final_path = experiment.fit(experiment.plan["development_ids"], selected["arm"], selected["config"], 42)
    decision = {"protocol_sha256": experiment.plan["protocol_sha256"], "selected": selected,
                "fit": str(final_path.resolve()), "fit_sha256": file_sha256(final_path),
                "seed": 42, "selection_uses_reserved_test": False, "production_ready": False,
                "note": "Fixed final decision before any reserved-test prediction; internal holdout is previously observed."}
    atomic_json(output / "frozen_decision.json", decision)
    report = {"version": VERSION, "protocol_sha256": experiment.plan["protocol_sha256"], "comparisons": comparisons,
              "nested_selection_metrics": nested_metrics, "oof_predictions": results, "nested_oof_predictions": nested,
              "fold_reports": fold_reports, "final_choices": choices, "frozen_decision": decision,
              "development_videos": len(experiment.plan["development_ids"]), "reserved_videos": len(experiment.plan["reserved_ids"]),
              "independent_external_test": False, "production_ready": False,
              "limitations": ["Same camera and previously examined dataset; exploratory grouped internal CV only.",
                              "Seed42 is the primary predeclared model; additional seeds measure sensitivity, not a lucky-seed selection.",
                              "Family selection for the nested estimate uses inner folds only. Per-family comparisons are exploratory.",
                              "No human review is manufactured; coarse intervals and unlabeled frames do not become action negatives.",
                              "MIL predicts a video bag, not validated temporal/legal evidence."]}
    atomic_json(output / "cv_report.json", report)
    atomic_json(output / "complete.json", {"report_sha256": file_sha256(output / "cv_report.json"), "decision_sha256": file_sha256(output / "frozen_decision.json")})
    print(json.dumps({"comparisons": comparisons, "nested_selection": nested_metrics, "final": {k: selected[k] for k in ("arm", "config", "threshold")}}), flush=True)
    return report


def evaluate_reserved(directory, *, weights, weights_sha256, device="cuda"):
    output = Path(directory)
    if (output / "reserved_report.json").exists():
        raise ValueError("reserved diagnostic already exists")
    complete = read_json(output / "complete.json")
    if file_sha256(output / "frozen_decision.json") != complete["decision_sha256"]:
        raise ValueError("final decision changed")
    decision = read_json(output / "frozen_decision.json")
    if file_sha256(decision["fit"]) != decision["fit_sha256"]:
        raise ValueError("frozen fit changed")
    torch.set_num_threads(4)
    experiment = Experiment(directory, weights=weights, weights_sha256=weights_sha256, device=device)
    if decision["selected"]["arm"] == "finetune":
        experiment.load_prefix(experiment.plan["reserved_ids"])
    predictions = experiment.predict(decision["fit"], experiment.plan["reserved_ids"])
    report = {"test_role": "previously_observed_internal_grouped_holdout", "predictions": predictions,
              "threshold": decision["selected"]["threshold"], "metrics": metrics(predictions, decision["selected"]["threshold"]),
              "decision_sha256": complete["decision_sha256"], "independent_external_test": False, "production_ready": False}
    atomic_json(output / "reserved_report.json", report)
    print(json.dumps(report), flush=True)
    return report


def infer_video(directory, video, *, weights, weights_sha256, device="cuda"):
    """Use the frozen decision on a real local video; no action/rule claims."""
    from ml.video_baseline import encode_source
    output = Path(directory)
    complete = read_json(output / "complete.json")
    if file_sha256(output / "frozen_decision.json") != complete["decision_sha256"]:
        raise ValueError("final decision changed")
    decision = read_json(output / "frozen_decision.json")
    if file_sha256(decision["fit"]) != decision["fit_sha256"]:
        raise ValueError("frozen fit changed")
    torch.set_num_threads(4)
    experiment = Experiment(directory, weights=weights, weights_sha256=weights_sha256, device=device)
    source = Path(video).resolve(strict=True)
    digest = source_hash(source, 2*1024**3)
    metadata, _ = probe_video(source)
    if metadata["duration_sec"] > 180:
        raise ValueError("video exceeds duration budget")
    row = {"video_id": "inference-"+digest[:24], "path": source.name, "sha256": digest,
           "canonical_id": "sha256:"+digest, "group_id": "sha256:"+digest,
           "scene_id": "raw-unreviewed", "split": "excluded", "official_label": None,
           "provenance": {"kind": "original", "source_id": digest, "sha256": digest}, **metadata}
    index = build_index(source.parent, row, dataset_version="raw-inference-v1", split_version="not-training")
    row.update({"source_sha256": digest, "target": 0})
    encoder = FrozenEncoder(weights_path=weights, weights_sha256=weights_sha256).to(device).eval()
    state = safe_torch_load(decision["fit"])
    views = experiment.document["views"]["mode"]
    if state["arm"] == "finetune":
        selected = {s["time"]["source_pts"] for s in sample_scenes(index, define_scenes(index), rate=2.)}
        values, pending = [], []
        with torch.inference_mode():
            for timing, frame in iter_indexed_frames(source.parent, index):
                if timing["source_pts"] in selected:
                    pending.append(input_views(frame.to_image(), index["rotation"], views))
                    if len(pending) == 16:
                        values.append(prefix_views(encoder.features[:-2], torch.stack(pending).to(device)).cpu())
                        pending.clear()
            if pending:
                values.append(prefix_views(encoder.features[:-2], torch.stack(pending).to(device)).cpu())
        base = torch.cat(values)
        if len(base) != len(selected):
            raise ValueError("missing raw prefix coverage")
        experiment.prefix[row["video_id"]] = {"base": base}
        experiment.suffix_template = copy.deepcopy(encoder.features[-2:]).cpu()
        row["features"] = torch.zeros((len(base), 576))  # unused by adapted predictor
    else:
        features, _ = encode_source(source.parent, index, define_scenes(index), encoder, device, views)
        row["features"] = torch.from_numpy(features)
    experiment.by_id[row["video_id"]] = row
    prediction = experiment.predict(decision["fit"], [row["video_id"]])[0]
    threshold = decision["selected"]["threshold"]
    return {"task": "video_verdict", "source_sha256": digest, "score": prediction["score"], "threshold": threshold,
            "prediction": "violation" if prediction["score"] >= threshold else "no_violation", "arm": state["arm"],
            "model_sha256": decision["fit_sha256"], "production_ready": False, "event_localization_available": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--cache", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--audit-report", type=Path, required=True)
    for name in ("run", "evaluate-reserved", "infer"):
        child = commands.add_parser(name)
        child.add_argument("--experiment", type=Path, required=True)
        child.add_argument("--encoder-weights", type=Path, required=True)
        child.add_argument("--encoder-sha256", required=True)
        child.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
        if name == "infer":
            child.add_argument("--video", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.cache, args.output, audit_report=args.audit_report)
    elif args.command == "infer":
        print(json.dumps(infer_video(args.experiment, args.video, weights=args.encoder_weights,
                   weights_sha256=args.encoder_sha256, device=args.device), ensure_ascii=False, indent=2))
    else:
        (run if args.command == "run" else evaluate_reserved)(args.experiment, weights=args.encoder_weights,
                    weights_sha256=args.encoder_sha256, device=args.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
