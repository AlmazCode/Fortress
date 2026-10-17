"""Masked action diagnostics, separately supplied verdicts, and fixed-tolerance events."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

import numpy as np
import torch

from ml.cache import CacheSpec, encoder_fingerprint, load_cache
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.splits import validate_splits
from ml.models import FrozenEncoder, ModelConfig, VideoActionModel
from ml.models.encoder import file_sha256, safe_torch_load
from ml.windows import merge_scores, sample_key


def ratio(a, b):
    return a / b if b else None


def binary_metrics(truth, prediction):
    if len(truth) != len(prediction):
        raise ValueError("metric label/prediction lengths")
    if any(v is not None and type(v) is not bool for v in [*truth, *prediction]):
        raise ValueError("metrics accept explicit bool or unknown/null only")
    covered = [(y, p) for y, p in zip(truth, prediction) if y is not None and p is not None]
    tp = sum(y and p for y, p in covered)
    tn = sum(not y and not p for y, p in covered)
    fp = sum(not y and p for y, p in covered)
    fn = sum(y and not p for y, p in covered)
    known = sum(y is not None for y in truth)
    per_class = []
    for positive, false_positive, false_negative, support in ((tn, fn, fp, tn + fp), (tp, fp, fn, tp + fn)):
        per_class.append({"support_covered": support, "precision": ratio(positive, positive + false_positive),
                          "recall": ratio(positive, positive + false_negative),
                          "f1": ratio(2 * positive, 2 * positive + false_positive + false_negative) or 0.0,
                          "fp": false_positive, "fn": false_negative})
    recalls = [row["recall"] for row in per_class if row["recall"] is not None]
    return {"metric_version": "binary-covered-v1", "total": len(truth), "known_truth": known,
            "support": {"negative": sum(y is False for y in truth), "positive": sum(y is True for y in truth)},
            "covered": len(covered), "coverage": ratio(len(covered), known),
            "unknown_truth": len(truth) - known, "unknown_prediction_on_known": known - len(covered),
            "unknown_rate": ratio(sum(p is None for p in prediction), len(prediction)),
            "accuracy": ratio(tp + tn, len(covered)), "accuracy_over_all_known": ratio(tp + tn, known),
            "balanced_accuracy": sum(recalls) / len(recalls) if recalls else None,
            "macro_f1": sum(row["f1"] for row in per_class) / 2 if covered else None,
            "tp": tp, "tn": tn, "fp": fp, "fn": fn, "absolute_errors": fp + fn, "per_class": per_class}


def validate_packet(packet):
    if (packet["version"] != "ml-evaluation-input-v1" or type(packet["test_only"]) is not bool
            or packet["split"] not in ("train", "dev_validation", "independent_test")
            or not 1 <= len(packet["class_ids"]) <= 256
            or len(set(packet["class_ids"])) != len(packet["class_ids"])):
        raise ValueError("unsupported evaluation packet/classes/partition")
    validate_splits(packet["manifest"])
    if packet["manifest_sha256"] != stable_hash(packet["manifest"]):
        raise ValueError("evaluation manifest fingerprint mismatch")
    videos = {row["video_id"]: row for row in packet["manifest"]["videos"]}
    if not packet["test_only"] and any(v["provenance"]["kind"] == "synthetic" for v in videos.values()):
        raise ValueError("synthetic manifest cannot claim real evaluation")
    seen, points = set(), set()
    for row in packet["samples"]:
        if row["id"] in seen or videos[row["video_id"]]["split"] != packet["split"]:
            raise ValueError("duplicate evaluation point or wrong partition")
        seen.add(row["id"])
        point = (row["video_id"], row["scene_id"], row["time_sec"])
        if point in points:
            raise ValueError("duplicate source time in evaluation points")
        points.add(point)
        if (not isinstance(row["scene_id"], str) or not row["scene_id"]
                or type(row["time_sec"]) not in (int, float) or not math.isfinite(row["time_sec"])
                or not 0 <= row["time_sec"] < videos[row["video_id"]]["duration_sec"]
                or len(row["targets"]) != len(packet["class_ids"]) or len(row["scores"]) != len(row["targets"])):
            raise ValueError("evaluation sample shape/time")
        if any(v is not None and type(v) is not bool for v in row["targets"]):
            raise ValueError("target must be bool or unknown")
        if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1)
               for v in row["scores"]):
            raise ValueError("score must be probability or unknown")
    if len(seen) > 100000:
        raise ValueError("evaluation sample budget")
    for rows in (packet.get("verdicts", []), packet.get("truth_events", []), packet.get("predicted_events", [])):
        if len(rows) > 5000 or len({r["id"] for r in rows}) != len(rows):
            raise ValueError("evaluation verdict/event IDs or budget")
        if any(videos[r["video_id"]]["split"] != packet["split"] for r in rows):
            raise ValueError("verdict/event belongs to another partition")
    for row in packet.get("truth_events", []) + packet.get("predicted_events", []):
        if (row["class_id"] not in packet["class_ids"] or not isinstance(row["scene_id"], str) or not row["scene_id"]
                or row["end_sec"] > videos[row["video_id"]]["duration_sec"]):
            raise ValueError("event class/scene/duration mismatch")
    protocol = packet["event_protocol"]
    if (set(protocol) != {"version", "tolerance_sec"} or protocol["version"] != "event-boundary-v1"
            or type(protocol["tolerance_sec"]) not in (float, int)
            or not math.isfinite(protocol["tolerance_sec"]) or not 0 <= protocol["tolerance_sec"] <= 10):
        raise ValueError("predeclared event protocol required")


def event_metrics(truth, predicted, *, tolerance_sec=.5):
    if type(tolerance_sec) not in (int, float) or not math.isfinite(tolerance_sec) or not 0 <= tolerance_sec <= 10:
        raise ValueError("invalid event tolerance")
    groups = {}
    unknown = 0
    for is_prediction, rows in ((False, truth), (True, predicted)):
        for row in rows:
            if (type(row["known"]) is not bool or type(row["start_sec"]) not in (int, float)
                    or type(row["end_sec"]) not in (int, float)
                    or not math.isfinite(row["start_sec"]) or not math.isfinite(row["end_sec"])
                    or not 0 <= row["start_sec"] < row["end_sec"]):
                raise ValueError("invalid event interval/known mask")
            if not row["known"]:
                unknown += 1
                continue
            key = (row["video_id"], row["scene_id"], row["class_id"])
            groups.setdefault(key, [[], []])[int(is_prediction)].append(row)
    tp = fp = fn = 0
    matches = []
    for key, (expected, actual) in sorted(groups.items()):
        if max(len(expected), len(actual)) > 500:
            raise ValueError("event matching budget per video/scene/class")
        expected.sort(key=lambda r: r["id"])
        actual.sort(key=lambda r: r["id"])
        edges = [[j for j, ref in sorted(enumerate(expected), key=lambda item:
                  (abs(row["start_sec"] - item[1]["start_sec"]) + abs(row["end_sec"] - item[1]["end_sec"]), item[1]["id"]))
                  if abs(row["start_sec"] - ref["start_sec"]) <= tolerance_sec + 1e-9
                  and abs(row["end_sec"] - ref["end_sec"]) <= tolerance_sec + 1e-9] for row in actual]
        owner = {}

        def augment(index, visited):
            for candidate in edges[index]:
                if candidate in visited:
                    continue
                visited.add(candidate)
                if candidate not in owner or augment(owner[candidate], visited):
                    owner[candidate] = index
                    return True
            return False

        for index in range(len(actual)):
            augment(index, set())
        tp += len(owner)
        fp += len(actual) - len(owner)
        fn += len(expected) - len(owner)
        matches.extend({"truth_id": expected[j]["id"], "prediction_id": actual[i]["id"]} for j, i in sorted(owner.items()))
    return {"protocol": {"version": "event-boundary-v1", "tolerance_sec": tolerance_sec},
            "tp": tp, "fp": fp, "fn": fn, "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
            "f1": ratio(2 * tp, 2 * tp + fp + fn), "unknown_events": unknown, "matches": matches}


def evaluate(packet, thresholds):
    validate_packet(packet)
    from ml.thresholds import validate_thresholds
    validate_thresholds(thresholds, packet)
    classes = {}
    for column, class_id in enumerate(packet["class_ids"]):
        threshold = thresholds["values"][class_id]
        labels = [row["targets"][column] for row in packet["samples"]]
        predictions = [None if threshold is None or row["scores"][column] is None
                       else row["scores"][column] >= threshold for row in packet["samples"]]
        classes[class_id] = binary_metrics(labels, predictions)
    verdicts = packet.get("verdicts", [])
    verdict = binary_metrics([r["truth"] for r in verdicts], [r["prediction"] for r in verdicts]) if verdicts else None
    events = event_metrics(packet.get("truth_events", []), packet.get("predicted_events", []),
                           tolerance_sec=packet["event_protocol"]["tolerance_sec"])
    return {"version": "ml-evaluation-v1", "input_sha256": stable_hash(packet), "split": packet["split"],
            "split_manifest": copy.deepcopy(packet["manifest"]),
            "manifest_sha256": packet["manifest_sha256"], "checkpoint_sha256": packet["checkpoint_sha256"],
            "dataset_sha256": packet["dataset_sha256"], "taxonomy_sha256": packet["taxonomy_sha256"],
            "class_ids": packet["class_ids"], "thresholds_sha256": stable_hash(thresholds),
            "test_only": packet["test_only"], "action_sample_metrics": classes, "verdict_metrics": verdict,
            "event_metrics": events, "validation_status": "not_validated", "real_targets_evaluated": False,
            "limitations": ["Action scores are not legal verdicts; verdict metrics require separately supplied reviewed verdicts.",
                             "Accuracy/FP/FN use covered known labels; unknown coverage and all-known accuracy are separate.",
                             "Macro-F1 averages both binary classes with zero for undefined F1; balanced accuracy averages supported recalls.",
                             "Event boundaries use fixed tolerance and maximum one-to-one matching within video/scene/class.",
                             "Synthetic calculations verify software only; real quality >=0.80 and performance are not established."]}


def score_cache(directory, checkpoint_path, manifest, *, encoder_weights=None, encoder_sha256=None):
    spec = CacheSpec.from_dict(read_json(Path(directory) / "cache.json")["spec"])
    cache = load_cache(directory, spec)
    checkpoint = safe_torch_load(checkpoint_path)
    signature = checkpoint["signature"]
    if (checkpoint["checkpoint_version"] != "training-checkpoint-v1"
            or checkpoint["signature_sha256"] != stable_hash(signature)
            or checkpoint["completed_steps"] < 1 or signature["class_ids"] != list(spec.class_ids)
            or signature["encoder"] != cache["encoder"] or signature["preprocessing"] != cache["preprocessing"]):
        raise ValueError("evaluation checkpoint/cache mismatch or zero trained steps")
    # Train/dev/final have different windows/source SHA, but share these immutable inputs.
    training_spec = signature.get("training_spec")
    if training_spec is None:
        # M2 v1 embeds the entire key rather than enough fields to compare new partitions.
        # Until a cross-partition spec is available, only the identical train cache is safe.
        if signature["cache_key"] != spec.key():
            raise ValueError("cross-partition scoring requires checkpoint training_spec provenance")
    else:
        original = CacheSpec.from_dict(training_spec)
        if original.partition != "train" or original.key() != signature["cache_key"]:
            raise ValueError("checkpoint training partition/key mismatch")
        for field in ("dataset_sha256", "split_sha256", "annotation_sha256", "taxonomy_sha256",
                      "encoder_sha256", "preprocessing_sha256", "config_sha256", "class_ids", "test_only"):
            if getattr(original, field) != getattr(spec, field):
                raise ValueError("evaluation dataset/split/annotation/config lineage mismatch")
    validate_splits(manifest)
    if stable_hash(manifest) != spec.dataset_sha256:
        raise ValueError("evaluation manifest differs from cache dataset revision")
    if training_spec is not None:
        validate_training_lineage(original, manifest)
    videos = {row["video_id"]: row for row in manifest["videos"]}
    for window in cache["windows"]:
        original = videos[window["video_id"]]
        if original["sha256"] != window["source_sha256"] or original["split"] != window["split"]:
            raise ValueError("cached window differs from original split/source")
    encoder = FrozenEncoder(test_only=spec.test_only, seed=cache["encoder"].get("seed", 42),
                            weights_path=encoder_weights, weights_sha256=encoder_sha256)
    model = VideoActionModel(encoder, ModelConfig(**signature["architecture"]))
    model.load_state_dict(checkpoint["model"], strict=True)
    if encoder_fingerprint(model.encoder) != cache["encoder"]["state_sha256"]:
        raise ValueError("evaluation encoder state mismatch")
    model.eval()
    values = []
    with torch.inference_mode():
        for item in cache["arrays"]:
            logits, _ = model.temporal(torch.from_numpy(item["features"])[None],
                                      image_mask=torch.from_numpy(item["image_mask"])[None])
            values.append(torch.sigmoid(logits[0]).numpy())
    merged = merge_scores(cache["windows"], values)
    targets = {}
    for window, item in zip(cache["windows"], cache["arrays"]):
        for n, sample in enumerate(window["samples"]):
            if sample is None or not window["image_mask"][n]:
                continue
            key = sample_key(window, sample)
            row = [bool(v) if known else None for v, known in zip(item["targets"][n], item["known_mask"][n])]
            if key in targets and targets[key] != row:
                raise ValueError("overlap label disagreement")
            targets[key] = row
    samples = []
    for row in merged:
        key = (row["video_id"], row["scene_id"], row["split"], row["time"]["source_pts"])
        samples.append({"id": stable_hash(key), "video_id": key[0], "scene_id": key[1],
                        "time_sec": row["time"]["timestamp_sec"], "targets": targets[key], "scores": row["scores"]})
    packet = {"version": "ml-evaluation-input-v1", "manifest": copy.deepcopy(manifest),
              "manifest_sha256": stable_hash(manifest), "split": spec.partition, "test_only": spec.test_only,
              "class_ids": list(spec.class_ids), "dataset_sha256": spec.dataset_sha256,
              "taxonomy_sha256": spec.taxonomy_sha256, "checkpoint_sha256": file_sha256(checkpoint_path),
              "samples": samples, "verdicts": [], "truth_events": [], "predicted_events": [],
              "event_protocol": {"version": "event-boundary-v1", "tolerance_sec": .5}}
    validate_packet(packet)
    return packet


def validate_training_lineage(spec, manifest):
    validate_splits(manifest)
    if (spec.partition != "train" or spec.dataset_sha256 != stable_hash(manifest)
            or spec.split_sha256 != stable_hash(manifest["split_version"])
            or spec.source_sha256 != stable_hash({r["video_id"]: r["sha256"] for r in manifest["videos"]
                                                  if r["split"] == "train"})):
        raise ValueError("training cache must cover the declared train sources of the immutable split manifest")


def write_new_json(path, document):
    payload = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8") as output:
        output.write(payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="explicit ml-evaluation-input-v1 JSON")
    source.add_argument("--cache", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--encoder-weights", type=Path)
    parser.add_argument("--encoder-sha256")
    parser.add_argument("--thresholds", type=Path, help="omit to export scores only")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input:
            packet = read_json(args.input)
        else:
            if not args.checkpoint or not args.manifest:
                raise ValueError("cache scoring requires --checkpoint and --manifest")
            manifest = read_json(args.manifest)
            packet = score_cache(args.cache, args.checkpoint, manifest.get("manifest", manifest),
                                 encoder_weights=args.encoder_weights, encoder_sha256=args.encoder_sha256)
        validate_packet(packet)
        result = packet if args.thresholds is None else evaluate(packet, read_json(args.thresholds))
        write_new_json(args.output, result)
        print(json.dumps({"version": result["version"], "test_only": result["test_only"], "production_ready": False}))
        return 0
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
        parser.exit(1, f"evaluation refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
