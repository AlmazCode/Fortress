"""Reproducible local MobileNetV3 + GRU video-verdict baseline.

This experimental checkpoint is deliberately distinct from an event/rules release.
Missing action annotations never become negative action labels. Test labels never
select normalization, model weights, early stopping, or classification thresholds.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import io
import json
import math
import os
from pathlib import Path
import platform
import time
import urllib.request

# Required by deterministic CUDA matrix multiplication; set before importing torch.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence, pad_sequence
import torchvision

from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import _existing, artifact_transaction, display_transform, transformed_image
from ml.data.manifest import local_source, source_hash, probe_video
from ml.data.pts_index import build_index, iter_indexed_frames
from ml.data.scenes import define_scenes, sample_scenes
from ml.data.training_package import (VERDICTS, json_bytes, load_prepared, prepare, verify_sources)
from ml.evaluate import binary_metrics
from ml.models import FrozenEncoder
from ml.models.encoder import file_sha256, safe_torch_load
from ml.preprocessing import PreprocessConfig, preprocess_image

CACHE_FORMAT = "video-baseline-cache-v1"
CHECKPOINT_FORMAT = "video-baseline-checkpoint-v1"


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".writing")
    with temp.open("wb") as stream:
        stream.write(json_bytes(value))
    os.replace(temp, path)


def atomic_checkpoint(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".writing")
    torch.save(value, temp)
    # Refuse to publish a checkpoint that the bounded tensor-only loader rejects.
    safe_torch_load(temp)
    os.replace(temp, path)


def download_weights(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    url = torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1.url
    if not url.startswith("https://download.pytorch.org/models/"):
        raise ValueError("unexpected publisher URL")
    target = directory / url.rsplit("/", 1)[-1]
    prefix = target.stem.rsplit("-", 1)[-1]
    if not target.exists():
        temp = target.with_suffix(".download")
        if temp.exists():
            raise ValueError("incomplete download exists; choose a new weights directory")
        count = 0
        try:
            with urllib.request.urlopen(url, timeout=60) as response, temp.open("xb") as output:
                if not response.url.startswith("https://download.pytorch.org/"):
                    raise ValueError("unexpected weights redirect")
                while chunk := response.read(1024**2):
                    count += len(chunk)
                    if count > 16 * 1024**2:
                        raise ValueError("weights download exceeds byte budget")
                    output.write(chunk)
            if not file_sha256(temp).startswith(prefix):
                raise ValueError("publisher filename/hash mismatch")
            os.replace(temp, target)
        except Exception:
            # Keep a failed partial download for diagnosis, never publish it.
            raise
    digest = file_sha256(target)
    if not digest.startswith(prefix):
        raise ValueError("prepared weights publisher hash mismatch")
    FrozenEncoder(weights_path=target, weights_sha256=digest)
    receipt = {"source": url, "path": str(target.resolve()), "sha256": digest,
               "publisher_prefix_verified": True, "weights": "IMAGENET1K_V1"}
    atomic_json(directory / "weights_receipt.json", receipt)
    return receipt


def device_preflight(device="cuda"):
    if device not in ("cpu", "cuda") or device == "cuda" and not torch.cuda.is_available():
        raise ValueError("requested CUDA runtime is unavailable; install the locked ml-cuda extra")
    with torch.random.fork_rng(devices=[] if device == "cpu" else [torch.cuda.current_device()]):
        torch.manual_seed(42)
        model = nn.GRU(576, 256, batch_first=True).to(device)
        data = torch.randn(2, 16, 576, device=device)
        result, _ = model(data)
        result.square().mean().backward()
        if not all(p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in model.parameters()):
            raise ValueError("device produced missing/nonfinite gradients")
        if device == "cuda":
            torch.cuda.synchronize()
    return {"device": device, "python": platform.python_version(), "torch": str(torch.__version__),
            "torchvision": str(torchvision.__version__), "cuda_runtime": torch.version.cuda,
            "gpu": torch.cuda.get_device_name() if device == "cuda" else None,
            "vram_bytes": torch.cuda.get_device_properties(0).total_memory if device == "cuda" else None,
            "gru_forward_backward": "passed", "quality_evaluation": "not_run"}


def input_views(image, rotation, mode):
    if mode not in ("global", "three_crop"):
        raise ValueError("unknown versioned view mode")
    result = [preprocess_image(image, rotation=rotation)["tensor"]]
    if mode == "three_crop":
        displayed = transformed_image(image, display_transform({"width": image.width, "height": image.height, "rotation": rotation}))
        w, h = displayed.size
        side = min(w, h)
        boxes = ((0, 0, side, side), (w-side, h-side, w, h))
        result.extend(preprocess_image(displayed.crop(box))["tensor"] for box in boxes)
    return torch.stack(result)


def encode_source(source_root, index, scenes, encoder, device, views, batch_size=16):
    sampled = sample_scenes(index, scenes, rate=2.0)
    if any(not s["image_mask"] for s in sampled):
        raise ValueError("source has missing sample coverage; review before baseline training")
    selected = {s["time"]["source_pts"] for s in sampled}
    if len(selected) != len(sampled) or len(sampled) > 360:
        raise ValueError("duplicate/over-budget sampled PTS")
    features, points, tensors, pending_points = [], [], [], []

    def flush():
        if tensors:
            batch = torch.stack(tensors).to(device)
            # Reuse the same frozen encoder; no extra model or 4D feature contract.
            values = torch.stack([encoder(batch[:, view]) for view in range(batch.shape[1])], dim=1).mean(1)
            features.extend(values.detach().cpu().numpy().copy())
            points.extend(pending_points)
            tensors.clear()
            pending_points.clear()

    with torch.inference_mode():
        for frame_row, frame in iter_indexed_frames(source_root, index):
            if frame_row["source_pts"] in selected:
                tensors.append(input_views(frame.to_image(), index["rotation"], views))
                pending_points.append(frame_row["source_pts"])
                if len(tensors) == batch_size:
                    flush()
        flush()
    if len(features) != len(selected):
        raise ValueError("not all requested source PTS were decoded")
    return np.asarray(features, dtype=np.float32), np.asarray(points, dtype=np.int64)


def cache(prepared, output, *, weights, weights_sha256, device="cuda", batch_size=16, rate=2.0, views="global"):
    if type(batch_size) is not int or not 1 <= batch_size <= 64 or rate != 2.0:
        raise ValueError("baseline cache requires batch 1..64 and the fixed 2 fps preprocessing")
    prepared = Path(prepared).resolve(strict=True)
    report, manifest = load_prepared(prepared)
    device_preflight(device)
    encoder = FrozenEncoder(weights_path=weights, weights_sha256=weights_sha256).to(device)
    descriptor = encoder.descriptor()
    config = PreprocessConfig()
    view_descriptor = {"version": "video-views-v1", "mode": views, "fusion": "feature_mean_576",
                       "definition": "full letterbox; optional first/last displayed square; identical encoder weights"}
    if views not in ("global", "three_crop"):
        raise ValueError("unknown view mode")
    key = stable_hash({"format": CACHE_FORMAT, "manifest": manifest, "inputs": report["input_hashes"],
                       "encoder": descriptor, "preprocessing": config.descriptor(), "views": view_descriptor, "rate": rate})
    labels = {v["video_id"]: v for v in read_json(prepared / "labels.json")["videos"]}

    def build(staging, register):
        entries = []
        old_threads = torch.get_num_threads()
        torch.set_num_threads(min(old_threads, 4))
        try:
            with torch.inference_mode():
                for row in manifest["videos"]:
                    index = read_json(prepared / f"indices/{row['video_id']}.json")
                    scenes = read_json(prepared / f"scenes/{row['video_id']}.json")
                    features, points = encode_source(report["source_root"], index, scenes, encoder, device, views, batch_size)
                    payload = io.BytesIO()
                    np.savez(payload, features=np.asarray(features, dtype=np.float32), source_pts=np.asarray(points, dtype=np.int64))
                    relative = f"features/{row['video_id']}.npz"
                    file_entry = register(relative, payload.getvalue())
                    entries.append({"video_id": row["video_id"], "split": row["split"], "group_id": row["group_id"],
                        "source_sha256": row["sha256"], "path": relative, "sha256": file_entry["sha256"],
                        "frames": len(features), "target": VERDICTS[labels[row["video_id"]]["verdict"]],
                        "label_source": labels[row["video_id"]]["verdict_source"]})
                    print(json.dumps({"cached": row["video_id"], "frames": len(features), "device": device}), flush=True)
        finally:
            torch.set_num_threads(old_threads)
        verify_sources(report["source_root"], manifest)
        document = {"format": CACHE_FORMAT, "prepared_dir": str(prepared), "manifest_sha256": stable_hash(manifest),
            "encoder": descriptor, "preprocessing": config.descriptor(), "views": view_descriptor, "rate": rate, "entries": entries,
            "test_role": "internal_grouped_holdout", "production_ready": False,
            "independent_external_test": False, "input_hashes": report["input_hashes"]}
        register("cache.json", json_bytes(document))
        return {"format": CACHE_FORMAT, "videos": len(entries), "frames": sum(e["frames"] for e in entries),
                "device": device, "feature_dim": 576, "views": views, "video_training_ready": True, "production_ready": False}

    return artifact_transaction(output, key, build, max_bytes=128 * 1024**2, min_free_bytes=256 * 1024**2)


def load_feature_cache(directory):
    directory = Path(directory).resolve(strict=True)
    marker = read_json(directory / "artifacts.json")
    _existing(directory, marker["cache_key"])
    document = read_json(directory / "cache.json")
    if document["format"] != CACHE_FORMAT or document["production_ready"] is not False:
        raise ValueError("unsupported baseline feature cache")
    report, manifest = load_prepared(document["prepared_dir"])
    if document["manifest_sha256"] != stable_hash(manifest) or document["input_hashes"] != report["input_hashes"]:
        raise ValueError("prepared dataset/cache lineage mismatch")
    rows = {r["video_id"]: r for r in manifest["videos"]}
    if len(document["entries"]) != len(rows) or {e["video_id"] for e in document["entries"]} != set(rows):
        raise ValueError("feature cache must cover every declared video exactly once")
    labels = {v["video_id"]: v for v in read_json(Path(document["prepared_dir"]) / "labels.json")["videos"]}
    data = []
    for entry in document["entries"]:
        source = rows[entry["video_id"]]
        if (entry["split"] != source["split"] or entry["source_sha256"] != source["sha256"]
                or entry["target"] != VERDICTS[labels[entry["video_id"]]["verdict"]]
                or entry["group_id"] != source["group_id"]):
            raise ValueError("cache label/source/group/partition binding mismatch")
        path = local_source(directory, entry["path"])
        if source_hash(path, 8 * 1024**2) != entry["sha256"]:
            raise ValueError("feature bytes changed")
        with np.load(path, allow_pickle=False) as arrays:
            if set(arrays.files) != {"features", "source_pts"}:
                raise ValueError("unsupported feature array layout")
            features, points = arrays["features"], arrays["source_pts"]
        if (features.dtype != np.float32 or features.shape != (entry["frames"], 576) or not 1 <= len(features) <= 360
                or points.dtype != np.int64 or points.shape != (len(features),) or not np.isfinite(features).all()
                or not np.all(np.diff(points) > 0)):
            raise ValueError("invalid numeric feature/PTS arrays")
        data.append({**entry, "features": torch.from_numpy(features.copy())})
    return document, data


@dataclass(frozen=True)
class Config:
    version: str = "video-gru-baseline-v2"
    selection_metric: str = "balanced_accuracy_macro_f1_bce"
    seed: int = 42
    epochs: int = 80
    batch_size: int = 4
    learning_rate: float = 0.00003
    weight_decay: float = 0.1
    dropout: float = 0.6
    patience: int = 20
    grad_clip: float = 1.0
    device: str = "cuda"
    cpu_threads: int = 4

    def __post_init__(self):
        if (self.version != "video-gru-baseline-v2" or self.selection_metric != "balanced_accuracy_macro_f1_bce"
                or self.device not in ("cpu", "cuda")
                or any(type(v) is not int for v in (self.seed, self.epochs, self.batch_size, self.patience, self.cpu_threads))
                or not 0 <= self.seed < 2**32 or not 1 <= self.epochs <= 200 or not 1 <= self.batch_size <= 16
                or not 1 <= self.patience <= 100 or not 1 <= self.cpu_threads <= 16):
            raise ValueError("unsupported baseline config")
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in
               (self.learning_rate, self.weight_decay, self.dropout, self.grad_clip)):
            raise ValueError("nonfinite config")
        if not (0 < self.learning_rate <= .01 and 0 <= self.weight_decay <= 1 and 0 <= self.dropout < .9 and 0 < self.grad_clip <= 100):
            raise ValueError("hyperparameter outside baseline budget")


class VerdictGRU(nn.Module):
    """One 576 -> 256 causal GRU; masked mean/max pooling -> one video logit."""
    def __init__(self, dropout=.35):
        super().__init__()
        self.gru = nn.GRU(576, 256, num_layers=1, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(512, 1)

    def forward(self, features, lengths):
        if (features.ndim != 3 or features.shape[-1] != 576 or not torch.isfinite(features).all()
                or lengths.ndim != 1 or len(lengths) != len(features) or (lengths < 1).any()
                or (lengths > features.shape[1]).any()):
            raise ValueError("invalid padded video features/lengths")
        packed = pack_padded_sequence(features, lengths.cpu(), batch_first=True, enforce_sorted=False)
        output, _ = self.gru(packed)
        output, _ = pad_packed_sequence(output, batch_first=True)
        mask = torch.arange(output.shape[1], device=features.device)[None] < lengths.to(features.device)[:, None]
        mean = output.sum(1) / lengths.to(features.device)[:, None]
        maximum = output.masked_fill(~mask[..., None], float("-inf")).amax(1)
        return self.head(self.dropout(torch.cat((mean, maximum), dim=-1))).squeeze(-1)


def normalization(rows):
    if not rows or any(r["split"] != "train" for r in rows):
        raise ValueError("normalization fits train videos only")
    values = torch.cat([r["features"] for r in rows])
    return {"mean": values.mean(0), "std": values.std(0, unbiased=False).clamp_min(.01)}


def batch(rows, norm, device):
    features = [(r["features"] - norm["mean"]) / norm["std"] for r in rows]
    return (pad_sequence(features, batch_first=True).to(device), torch.tensor([len(f) for f in features]),
            torch.tensor([r["target"] for r in rows], dtype=torch.float32, device=device))


def scores(model, rows, norm, device, batch_size):
    model.eval()
    result = []
    with torch.inference_mode():
        for start in range(0, len(rows), batch_size):
            selected = rows[start:start + batch_size]
            features, lengths, _ = batch(selected, norm, device)
            probabilities = model(features, lengths).sigmoid().cpu().tolist()
            result.extend({"video_id": r["video_id"], "truth": bool(r["target"]), "score": float(p)}
                          for r, p in zip(selected, probabilities))
    return result


def metrics(rows, threshold):
    return binary_metrics([r["truth"] for r in rows], [r["score"] >= threshold for r in rows])


def calibrate_video(rows, *, partition):
    if partition != "dev_validation" or {r["truth"] for r in rows} != {False, True}:
        raise ValueError("threshold selection requires both classes on development only")
    if any(type(r["score"]) not in (int, float) or not math.isfinite(r["score"]) or not 0 <= r["score"] <= 1 for r in rows):
        raise ValueError("finite development probabilities required")
    # A fixed .01 grid can miss a valid decision boundary (e.g. .4627/.4660).
    # Enumerate every distinct development decision partition, without test data.
    ordered = sorted({0., 1., *(float(r["score"]) for r in rows)})
    thresholds = {.5, *((a+b)/2 for a, b in zip(ordered, ordered[1:]) if a < b)}
    candidates = []
    for threshold in sorted(thresholds):
        m = metrics(rows, threshold)
        candidates.append((m["balanced_accuracy"], m["macro_f1"], -abs(threshold - .5), threshold))
    return max(candidates)[-1]


def quality_gate(result, *, independent_external_test):
    reached = all(result.get(k) is not None and result[k] >= .8 for k in ("accuracy", "balanced_accuracy", "macro_f1"))
    return {"target": .8, "internal_target_reached": reached,
            "independent_80_confirmed": bool(reached and independent_external_test),
            "production_ready": False,
            "reason": "An internal camera holdout cannot establish independent/generalization quality or event/rules readiness."}


def train(cache_dir, output_dir, *, config=Config(), resume=None, stop_after_epochs=None):
    started = time.monotonic()
    document, data = load_feature_cache(cache_dir)
    device_preflight(config.device)
    train_rows = [r for r in data if r["split"] == "train"]
    dev_rows = [r for r in data if r["split"] == "dev_validation"]
    if {r["target"] for r in train_rows} != {0, 1} or {r["target"] for r in dev_rows} != {0, 1}:
        raise ValueError("train and dev must each contain positive and negative video labels")
    if stop_after_epochs is not None and (type(stop_after_epochs) is not int or stop_after_epochs < 1):
        raise ValueError("positive stop-after epoch budget required")
    cache_sha = stable_hash(document)
    signature = {"format": CHECKPOINT_FORMAT, "cache_sha256": cache_sha, "config": {k: v for k, v in asdict(config).items() if k != "epochs"},
                 "threshold_protocol": "dev-score-midpoints-v1",
                 "features": {k: document.get(k) for k in ("encoder", "preprocessing", "views", "rate")},
                 "architecture": {"encoder": "mobilenet_v3_small", "feature_dim": 576, "hidden_size": 256, "layers": 1,
                                  "pooling": "masked_mean_max", "task": "video_verdict"},
                 "torch": str(torch.__version__), "torchvision": str(torchvision.__version__)}
    signature_sha = stable_hash(signature)
    previous = None if resume is None else safe_torch_load(resume)
    if previous is not None and (previous.get("format") != CHECKPOINT_FORMAT or previous.get("signature") != signature
                                 or previous.get("signature_sha256") != signature_sha):
        raise ValueError("resume model/config/runtime/dataset/cache mismatch")
    expected_norm = normalization(train_rows)
    if previous is not None:
        if previous["completed_epochs"] >= config.epochs or previous["stale_epochs"] >= config.patience:
            raise ValueError("resume requires a larger epoch budget and a run that has not early-stopped")
        if any(not torch.equal(previous["normalization"][k], expected_norm[k]) for k in ("mean", "std")):
            raise ValueError("resume normalization differs from train-only features")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    old_threads = torch.get_num_threads()
    old_deterministic = torch.are_deterministic_algorithms_enabled()
    torch.set_num_threads(config.cpu_threads)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(config.seed)
    if config.device == "cuda":
        torch.cuda.manual_seed_all(config.seed)
        torch.cuda.reset_peak_memory_stats()
    model = VerdictGRU(config.dropout).to(config.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=.5, patience=4, min_lr=1e-6)
    generator = torch.Generator().manual_seed(config.seed)
    norm = expected_norm
    completed, history, stale = 0, [], 0
    best_state, best_loss, best_epoch = None, float("inf"), 0
    best_selection = (-1., -1., float("-inf"))
    if previous is not None:
        model.load_state_dict(previous["model"], strict=True)
        optimizer.load_state_dict(previous["optimizer"])
        scheduler.load_state_dict(previous["scheduler"])
        norm = previous["normalization"]
        completed, history, stale = previous["completed_epochs"], previous["history"], previous["stale_epochs"]
        best_state, best_loss, best_epoch = previous["best_state"], previous["best_dev_loss"], previous["best_epoch"]
        best_selection = tuple(previous["best_selection_score"])
        generator.set_state(previous["sampler_rng"])
        torch.set_rng_state(previous["torch_rng"])
        if config.device == "cuda":
            torch.cuda.set_rng_state_all(previous["cuda_rng"])
    if completed >= config.epochs:
        raise ValueError("resume needs a larger total epoch budget")
    positives = sum(r["target"] for r in train_rows)
    pos_weight = torch.tensor((len(train_rows) - positives) / positives, device=config.device)
    checkpoint = None
    try:
        for epoch in range(completed + 1, config.epochs + 1):
            model.train()
            order = torch.randperm(len(train_rows), generator=generator).tolist()
            losses = []
            for start in range(0, len(order), config.batch_size):
                selected = [train_rows[i] for i in order[start:start + config.batch_size]]
                features, lengths, targets = batch(selected, norm, config.device)
                optimizer.zero_grad(set_to_none=True)
                logits = model(features, lengths)
                loss = nn.functional.binary_cross_entropy_with_logits(logits, targets, pos_weight=pos_weight)
                if not torch.isfinite(loss):
                    raise ValueError("nonfinite training loss")
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip, error_if_nonfinite=True)
                optimizer.step()
                losses.append(float(loss.detach().cpu()))
            dev_scores = scores(model, dev_rows, norm, config.device, config.batch_size)
            dev_loss = float(nn.functional.binary_cross_entropy(torch.tensor([r["score"] for r in dev_scores]),
                               torch.tensor([float(r["truth"]) for r in dev_scores])))
            scheduler.step(dev_loss)
            dev_threshold = calibrate_video(dev_scores, partition="dev_validation")
            calibrated_metrics = metrics(dev_scores, dev_threshold)
            selection = (calibrated_metrics["balanced_accuracy"], calibrated_metrics["macro_f1"], -dev_loss)
            if selection > best_selection:
                best_loss, best_epoch, stale = dev_loss, epoch, 0
                best_selection = selection
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            else:
                stale += 1
            row = {"epoch": epoch, "train_loss": sum(losses) / len(losses), "dev_loss": dev_loss,
                   "dev_at_0_5": metrics(dev_scores, .5), "dev_threshold": dev_threshold,
                   "dev_calibrated": calibrated_metrics, "learning_rate": optimizer.param_groups[0]["lr"]}
            history.append(row)
            checkpoint = {"format": CHECKPOINT_FORMAT, "signature": signature, "signature_sha256": signature_sha,
                "model": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                "optimizer": optimizer.state_dict(),
                # ReduceLROnPlateau's constant mode_worse=inf is reconstructed by
                # load_state_dict; keep the bounded tensor-only checkpoint finite.
                "scheduler": {k: v for k, v in scheduler.state_dict().items() if k != "mode_worse"}, "normalization": norm,
                "completed_epochs": epoch, "history": history, "best_state": best_state, "best_dev_loss": best_loss,
                "best_epoch": best_epoch, "best_selection_score": list(best_selection),
                "stale_epochs": stale, "sampler_rng": generator.get_state(),
                "torch_rng": torch.get_rng_state(), "cuda_rng": torch.cuda.get_rng_state_all() if config.device == "cuda" else []}
            atomic_checkpoint(output / "last.pt", checkpoint)
            atomic_json(output / "history.json", history)
            print(json.dumps({"epoch": epoch, "train_loss": row["train_loss"], "dev_loss": dev_loss, "best_epoch": best_epoch}), flush=True)
            if stale >= config.patience or stop_after_epochs is not None and epoch - completed >= stop_after_epochs:
                break
        model.load_state_dict(best_state)
        dev_scores = scores(model, dev_rows, norm, config.device, config.batch_size)
        threshold = calibrate_video(dev_scores, partition="dev_validation")
        candidate = {"format": CHECKPOINT_FORMAT, "signature": signature, "signature_sha256": signature_sha,
                     "model": best_state, "normalization": norm, "best_epoch": best_epoch, "threshold": threshold,
                     "threshold_partition": "dev_validation", "production_ready": False}
        atomic_checkpoint(output / "best.pt", candidate)
        result = {"task": "video_verdict", "completed_epochs": checkpoint["completed_epochs"], "best_epoch": best_epoch,
            "requested_total_epochs": config.epochs,
            "stop_reason": ("early_stopping" if stale >= config.patience else
                            "verification_budget" if stop_after_epochs is not None and checkpoint["completed_epochs"] < config.epochs else "epoch_budget"),
            "resumed": resume is not None, "threshold": threshold, "selection_metric": config.selection_metric,
            "threshold_protocol": signature["threshold_protocol"],
            "dev_metrics": metrics(dev_scores, threshold),
            "train_metrics": metrics(scores(model, train_rows, norm, config.device, config.batch_size), threshold),
            "dev_predictions": dev_scores, "test_evaluated": False, "independent_test_evaluated": False,
            "quality": quality_gate(metrics(dev_scores, threshold), independent_external_test=False),
            "cache_sha256": cache_sha, "checkpoint_sha256": file_sha256(output / "best.pt"),
            "runtime": device_preflight(config.device), "elapsed_seconds": time.monotonic() - started,
            "peak_allocated_vram_bytes": torch.cuda.max_memory_allocated() if config.device == "cuda" else None,
            "production_ready": False, "event_localization_trained": False,
            "limitations": ["Development metrics select the checkpoint and threshold; they are not final quality.",
                            "The model predicts a supplied video verdict; event evidence and legal rules need separate validation."]}
        atomic_json(output / "training_report.json", result)
        # Recheck every original after training; a successful run binds immutable inputs.
        load_prepared(document["prepared_dir"])
        atomic_json(output / "complete.json", {"signature_sha256": signature_sha, "report_sha256": stable_hash(result)})
        return result
    except BaseException as error:
        atomic_json(output / "failure.json", {"type": type(error).__name__, "detail": str(error),
                    "last_checkpoint_available": (output / "last.pt").is_file()})
        raise
    finally:
        torch.set_num_threads(old_threads)
        torch.use_deterministic_algorithms(old_deterministic)


def evaluate(cache_dir, checkpoint_path, output, *, split="independent_test", device="cuda"):
    if split not in ("train", "dev_validation", "independent_test"):
        raise ValueError("unknown partition")
    document, data = load_feature_cache(cache_dir)
    candidate = safe_torch_load(checkpoint_path)
    if (candidate.get("format") != CHECKPOINT_FORMAT or candidate["signature"]["cache_sha256"] != stable_hash(document)
            or candidate.get("signature_sha256") != stable_hash(candidate["signature"])
            or candidate.get("threshold_partition") != "dev_validation" or not 0 < candidate["threshold"] < 1):
        raise ValueError("checkpoint/cache/calibration mismatch")
    device_preflight(device)
    model = VerdictGRU(candidate["signature"]["config"]["dropout"]).to(device)
    model.load_state_dict(candidate["model"], strict=True)
    selected = [r for r in data if r["split"] == split]
    if not selected:
        raise ValueError("empty evaluation split")
    predictions = scores(model, selected, candidate["normalization"], device, 4)
    result = metrics(predictions, candidate["threshold"])
    # Wilson interval exposes the uncertainty of a four-video internal holdout.
    n, p, z = result["covered"], result["accuracy"], 1.959963984540054
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    report = {"task": "video_verdict", "split": split, "test_role": "internal_grouped_holdout" if split == "independent_test" else split,
              "metrics": result, "accuracy_wilson_95": [center-half, center+half], "predictions": predictions,
              "threshold": candidate["threshold"], "threshold_partition": "dev_validation",
              "checkpoint_sha256": file_sha256(checkpoint_path), "cache_sha256": stable_hash(document),
              "quality": quality_gate(result, independent_external_test=False), "production_ready": False}
    with Path(output).open("xb") as stream:
        stream.write(json_bytes(report))
    return report


def infer(video, checkpoint_path, *, weights, weights_sha256, device="cuda"):
    candidate = safe_torch_load(checkpoint_path)
    if (candidate.get("format") != CHECKPOINT_FORMAT or candidate.get("signature_sha256") != stable_hash(candidate["signature"])
            or candidate.get("threshold_partition") != "dev_validation"):
        raise ValueError("invalid baseline candidate")
    descriptor = candidate["signature"].get("features")
    if (not descriptor or stable_hash(descriptor["preprocessing"]) != stable_hash(PreprocessConfig().descriptor())
            or descriptor["encoder"]["weights_sha256"] != weights_sha256 or descriptor["rate"] != 2.0
            or descriptor["views"]["version"] != "video-views-v1"):
        raise ValueError("candidate preprocessing/weights/views mismatch")
    device_preflight(device)
    video = Path(video).resolve(strict=True)
    path = local_source(video.parent, video.name)
    digest = source_hash(path, 2 * 1024**3)
    metadata, _ = probe_video(path)
    if metadata["duration_sec"] > 180:
        raise ValueError("baseline video duration budget")
    row = {"video_id": "inference-" + digest[:24], "path": video.name, "sha256": digest,
           "canonical_id": "sha256:" + digest, "group_id": "sha256:" + digest,
           "scene_id": "raw-unreviewed", "split": "excluded", "official_label": None,
           "provenance": {"kind": "original", "source_id": digest, "sha256": digest}, **metadata}
    index = build_index(video.parent, row, dataset_version="raw-inference-v1", split_version="not-training")
    encoder = FrozenEncoder(weights_path=weights, weights_sha256=weights_sha256).to(device)
    features, points = encode_source(video.parent, index, define_scenes(index), encoder, device, descriptor["views"]["mode"])
    model = VerdictGRU(candidate["signature"]["config"]["dropout"]).to(device)
    model.load_state_dict(candidate["model"], strict=True)
    rows = [{"video_id": row["video_id"], "features": torch.from_numpy(features), "target": 0}]
    score = scores(model, rows, candidate["normalization"], device, 1)[0]["score"]
    return {"task": "video_verdict", "source_sha256": digest, "frames": len(points), "score": score,
            "threshold": candidate["threshold"], "prediction": "violation" if score >= candidate["threshold"] else "no_violation",
            "production_ready": False, "event_localization_available": False, "legal_rules_verified": False,
            "checkpoint_sha256": file_sha256(checkpoint_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight").add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    commands.add_parser("weights").add_argument("--output-dir", type=Path, required=True)
    importer = commands.add_parser("prepare")
    importer.add_argument("--package", type=Path, required=True)
    importer.add_argument("--output-dir", type=Path, required=True)
    importer.add_argument("--allow-dataset-use", action="store_true")
    caching = commands.add_parser("cache")
    caching.add_argument("--prepared", type=Path, required=True)
    caching.add_argument("--output-dir", type=Path, required=True)
    caching.add_argument("--encoder-weights", type=Path, required=True)
    caching.add_argument("--encoder-sha256", required=True)
    caching.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    caching.add_argument("--batch-size", type=int, default=16)
    caching.add_argument("--views", choices=["global", "three_crop"], default="global")
    fitting = commands.add_parser("train")
    fitting.add_argument("--cache", type=Path, required=True)
    fitting.add_argument("--output-dir", type=Path, required=True)
    fitting.add_argument("--config", type=Path, default=Path(__file__).parent / "config/video_baseline.json")
    fitting.add_argument("--resume", type=Path)
    fitting.add_argument("--stop-after-epochs", type=int)
    fitting.add_argument("--allow-real-training", action="store_true")
    scoring = commands.add_parser("evaluate")
    scoring.add_argument("--cache", type=Path, required=True)
    scoring.add_argument("--checkpoint", type=Path, required=True)
    scoring.add_argument("--output", type=Path, required=True)
    scoring.add_argument("--split", choices=["train", "dev_validation", "independent_test"], default="independent_test")
    scoring.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    inference = commands.add_parser("infer")
    inference.add_argument("--video", type=Path, required=True)
    inference.add_argument("--checkpoint", type=Path, required=True)
    inference.add_argument("--encoder-weights", type=Path, required=True)
    inference.add_argument("--encoder-sha256", required=True)
    inference.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    args = parser.parse_args(argv)
    torch.set_num_threads(4)
    try:
        if args.command == "preflight":
            result = device_preflight(args.device)
        elif args.command == "weights":
            result = download_weights(args.output_dir)
        elif args.command == "prepare":
            result = prepare(args.package, args.output_dir, allow_dataset_use=args.allow_dataset_use)["data"]
        elif args.command == "cache":
            result = cache(args.prepared, args.output_dir, weights=args.encoder_weights, weights_sha256=args.encoder_sha256,
                           device=args.device, batch_size=args.batch_size, views=args.views)["data"]
        elif args.command == "train":
            if not args.allow_real_training:
                raise ValueError("real training requires --allow-real-training")
            result = train(args.cache, args.output_dir, config=Config(**read_json(args.config)),
                           resume=args.resume, stop_after_epochs=args.stop_after_epochs)
        elif args.command == "infer":
            result = infer(args.video, args.checkpoint, weights=args.encoder_weights, weights_sha256=args.encoder_sha256, device=args.device)
        else:
            result = evaluate(args.cache, args.checkpoint, args.output, split=args.split, device=args.device)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        parser.exit(1, f"baseline {args.command} refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
