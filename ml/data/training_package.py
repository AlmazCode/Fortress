"""Import a local annotation package without promoting weak labels to human gold.

Video verdicts can supervise a first video classifier. The separate, incomplete
action intervals cannot supply absent-action labels or independent validation.
"""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from ml.data.annotation_tasks import read_json, scene_context
from ml.data.annotations import validate_actions
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import artifact_transaction
from ml.data.manifest import local_source, probe_video, source_hash
from ml.data.pts_index import build_index
from ml.data.scenes import define_scenes
from ml.data.splits import validate_splits
from ml.data.taxonomy import load_taxonomy, validate_taxonomy

SPLITS = {"train": "train", "val": "dev_validation", "test": "independent_test"}
VERDICTS = {"no_violation": 0, "violation": 1}
FORMAT = "video-training-package-v1"


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def validate_package_inputs(labels, split, actions):
    """Validate references and groups before any decoder, allocation or output."""
    rows = labels["videos"]
    if not rows or len(rows) > 500:
        raise ValueError("expected 1..500 unique videos")
    ids = [r["video_id"] for r in rows]
    if len(set(ids)) != len(ids) or any(not isinstance(v, str) or not re.fullmatch(r"video_[0-9]+", v) for v in ids):
        raise ValueError("missing/duplicate/unsafe video ID")
    if set(split["videos"]) != set(SPLITS):
        raise ValueError("preserved train/val/test assignments required")
    assignment = {}
    for partition, videos in split["videos"].items():
        for video in videos:
            if video in assignment:
                raise ValueError("video crosses partitions")
            assignment[video] = partition
    if set(assignment) != set(ids):
        raise ValueError("split does not cover exactly the declared videos")
    groups = defaultdict(set)
    hashes = defaultdict(set)
    for row in rows:
        if row["split"] != assignment[row["video_id"]] or row["verdict"] not in VERDICTS:
            raise ValueError("label/partition mismatch or unknown video verdict")
        if row.get("verdict_source") not in ("user_scenario", "organizer", "human_reviewed"):
            raise ValueError("video verdict needs an explicit supported source")
        if not re.fullmatch(r"[a-f0-9]{64}", row["source_sha256"]):
            raise ValueError("source SHA-256 required")
        if not isinstance(row.get("scenario_family"), str) or not row["scenario_family"]:
            raise ValueError("scenario family required")
        if not isinstance(row.get("duration_sec"), (int, float)) or not 0 < row["duration_sec"] <= 180:
            raise ValueError("invalid/beyond-budget duration")
        groups[row["scenario_family"]].add(row["split"])
        hashes[row["source_sha256"]].add(row["split"])
    if any(len(v) > 1 for v in [*groups.values(), *hashes.values()]):
        raise ValueError("source hash or scenario family crosses partitions")
    if len(hashes) != len(rows):
        raise ValueError("exclude exact duplicate aliases before training")
    for family in split.get("scenario_families", []):
        members = [f"video_{n:03}" for n in family]
        if not set(members) <= set(ids) or len({assignment[v] for v in members}) != 1:
            raise ValueError("paired scenario family crosses partitions")
    for partition in ("train", "val"):
        if {r["verdict"] for r in rows if r["split"] == partition} != set(VERDICTS):
            raise ValueError("training and development need both video verdicts")
    by_id = {r["video_id"]: r for r in rows}
    seen = set()
    for action in actions["annotations"]:
        if action["id"] in seen or action["video_id"] not in by_id:
            raise ValueError("duplicate action ID or unknown source")
        seen.add(action["id"])
        row = by_id[action["video_id"]]
        if (not 0 <= action["start_sec"] < action["end_sec"] <= row["duration_sec"]
                or action["split"] != row["split"]):
            raise ValueError("action bounds/partition mismatch")
        if action.get("explicit_negative") is True:
            raise ValueError("negative annotations need the canonical human review workflow")
    return assignment


def candidate_taxonomy(actions, base):
    """Append exact source meanings; never squeeze 50 labels into unrelated IDs."""
    result = copy.deepcopy(base)
    result.update(version="actions-package-candidates-v1", status="draft", reviewer=None, production_ready=False)
    by_id = {r["id"]: r for r in result["classes"]}
    mapping = {}
    source_names = {}
    template = result["classes"][0]
    for name in sorted({a["event_type"] for a in actions["annotations"]}):
        suffix = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
        if not suffix or not suffix[0].isalpha():
            raise ValueError("unsupported source action name")
        key = "action." + suffix
        if key in source_names and source_names[key] != name:
            raise ValueError("source action names collide after normalization")
        source_names[key] = name
        mapping[name] = key
        if key in by_id:
            continue
        row = copy.deepcopy(template)
        row.update(id=key, label=name, includes=["Source package candidate: " + name],
                   excludes=["Unlabeled motion, inferred absence, legal or financial conclusions"],
                   hard_negatives=["Similar motion with an unidentifiable object or participant"],
                   case_refs=[], case_mapping_status="unmapped")
        result["classes"].append(row)
        by_id[key] = row
    validate_taxonomy(result, previous=base)
    return result, mapping


def action_support(actions, assignment):
    counts = {s: Counter() for s in SPLITS}
    for row in actions["annotations"]:
        counts[assignment[row["video_id"]]][row["event_type"]] += 1
    all_names = set().union(*(c for c in counts.values()))
    return {
        "per_split": {s: dict(c) for s, c in counts.items()},
        "missing_train": sorted(all_names - counts["train"].keys()),
        "missing_development": sorted(all_names - counts["val"].keys()),
        "singleton_classes": sorted(k for k in all_names if sum(c[k] for c in counts.values()) == 1),
        "eligible_auxiliary_classes": sorted(k for k in counts["train"] if counts["train"][k] >= 3 and counts["val"][k] >= 1),
        "supervision": "weak positive proposals only; no automatic complement negatives",
        "action_training_ready": False,
    }


def prepare(package_root: Path, output_dir: Path, *, allow_dataset_use=False):
    if not allow_dataset_use:
        raise ValueError("dataset-use authorization is required (--allow-dataset-use)")
    root = Path(package_root).resolve(strict=True)
    paths = {"labels": "annotations/video_labels.json", "splits": "splits.json", "actions": "annotations/actions.json",
             "objects": "annotations/objects.coco.json", "people": "annotations/people.coco.json"}
    inputs = {key: read_json(local_source(root, value)) for key, value in paths.items()}
    labels, split, actions = (inputs[k] for k in ("labels", "splits", "actions"))
    assignment = validate_package_inputs(labels, split, actions)
    input_hashes = {key: source_hash(local_source(root, value), 64 * 1024**2) for key, value in paths.items()}
    taxonomy, mapping = candidate_taxonomy(actions, load_taxonomy(Path(__file__).parents[1] / "config/action_taxonomy.draft.json"))
    key = stable_hash({"format": FORMAT, "inputs": input_hashes, "taxonomy": taxonomy, "authorized_use": "local_training"})

    def build(staging, register):
        manifest = {"schema_version": "1.0", "dataset_version": "package-" + key,
                    "split_version": "preserved-" + stable_hash(split), "videos": []}
        timing_adjustments = []
        for row in labels["videos"]:
            path = local_source(root, row["video_path"])
            digest = source_hash(path, 2 * 1024**3)
            if digest != row["source_sha256"]:
                raise ValueError("original video hash mismatch: " + row["video_id"])
            metadata, _ = probe_video(path)
            delta = metadata["duration_sec"] - row["duration_sec"]
            if abs(delta) > .05:
                raise ValueError("original duration mismatch: " + row["video_id"])
            if abs(delta) > 1e-6:
                timing_adjustments.append({"video_id": row["video_id"], "declared_sec": row["duration_sec"],
                                           "decoded_sec": metadata["duration_sec"], "reason": "container end vs decoded last-frame end"})
            manifest["videos"].append({"video_id": row["video_id"], "canonical_id": "sha256:" + digest,
                "group_id": row["scenario_family"], "scene_id": row["video_id"] + ":unsegmented",
                "path": row["video_path"], "sha256": digest, "split": SPLITS[row["split"]], **metadata,
                "official_label": row.get("organizer_verdict"),
                "provenance": {"kind": row.get("provenance_kind", "original"), "source_id": "sha256:" + digest, "sha256": digest}})
        validate_splits(manifest)
        pairs = []
        for row in manifest["videos"]:
            index = build_index(root, row, dataset_version=manifest["dataset_version"], split_version=manifest["split_version"])
            scenes = define_scenes(index)
            pairs.append({"index": index, "scenes": scenes})
            register(f"indices/{row['video_id']}.json", json_bytes(index))
            register(f"scenes/{row['video_id']}.json", json_bytes(scenes))
            print(json.dumps({"prepared": row["video_id"], "split": row["split"]}), flush=True)
        contexts = scene_context(manifest, pairs)
        by_video = {v["video_id"]: v for v in manifest["videos"]}
        scene_for = {s["video_id"]: s["scene_id"] for s in contexts.values()}
        canonical = {"actions_version": "actions-v1", "dataset_version": manifest["dataset_version"],
            "annotation_version": "package-proposals-" + input_hashes["actions"], "taxonomy_version": taxonomy["version"],
            "provenance": {"kind": "original" if all(v["provenance"]["kind"] == "original" for v in manifest["videos"]) else "synthetic",
                           "source_id": manifest["dataset_version"], "sha256": stable_hash(manifest)}, "records": []}
        for action in actions["annotations"]:
            source = by_video[action["video_id"]]
            canonical["records"].append({"annotation_id": action["id"], "video_id": source["video_id"],
                "scene_id": scene_for[source["video_id"]], "source_sha256": source["sha256"], "split": source["split"],
                "start_sec": action["start_sec"], "end_sec": min(action["end_sec"], source["duration_sec"]), "event_type": mapping[action["event_type"]],
                "taxonomy_version": taxonomy["version"], "review_status": "unreviewed", "label_origin": "imported",
                "annotator": action.get("label_source", "source-package"), "reviewer": None, "human_approved": False,
                "interval_complete": False, "visibility": action.get("visibility", "unknown"), "state": "unreviewed",
                "known_mask": False, "actor_id": None, "relations": [], "weak_source_record": copy.deepcopy(action)})
        validate_actions(canonical, manifest=manifest, taxonomy=taxonomy, scenes=contexts)
        object_counts = Counter(a["category_id"] for a in inputs["objects"]["annotations"])
        object_support = [{**c, "positive_boxes": object_counts[c["id"]], "active_for_detector_training": object_counts[c["id"]] > 0}
                          for c in inputs["objects"]["categories"]]
        key_tasks = [{"video_id": a["video_id"], "start_sec": a["start_sec"], "end_sec": a["end_sec"],
                      "source_sha256": by_video[a["video_id"]]["sha256"], "evidence": a.get("evidence", []),
                      "status": "needs_pixel_review", "boxes": [], "reason": "Taking-key action is not itself a verified visible key box."}
                     for a in actions["annotations"] if a["event_type"] in ("take_key", "place_key")]
        report = {"format": FORMAT, "dataset_version": manifest["dataset_version"], "source_root": str(root),
            "input_hashes": input_hashes, "manifest_sha256": stable_hash(manifest), "split_sha256": stable_hash(split),
            "video_training_ready": True, "action_training_ready": False, "production_ready": False,
            "source_use_authorized": True, "independent_external_test": False, "test_role": "internal_grouped_holdout",
            "timing_adjustments": timing_adjustments,
            "data_kind": "original" if all(v["provenance"]["kind"] == "original" for v in manifest["videos"]) else "synthetic_or_mixed",
            "video_count": len(manifest["videos"]), "split_counts": dict(Counter(v["split"] for v in manifest["videos"])),
            "verdict_counts": {s: dict(Counter(v["verdict"] for v in labels["videos"] if v["split"] == s)) for s in SPLITS},
            "verdict_conflicts": [v["video_id"] for v in labels["videos"] if v.get("verdict_conflict")],
            "action_support": action_support(actions, assignment), "object_support": object_support,
            "limitations": ["Internal holdout uses the same camera; external generalization is unmeasured.",
                            "Video labels are supplied scenarios, including disclosed user/organizer disagreements.",
                            "Actions remain unreviewed weak proposals; unlabeled frames remain unknown.",
                            "Video classification alone does not establish event boundaries or applicable legal rules.",
                            "An empty object class is excluded from detector training, not filled with invented boxes."]}
        for name, value in (("manifest.json", manifest), ("labels.json", labels), ("action_taxonomy.json", taxonomy),
                            ("actions.json", canonical), ("scenes.json", contexts), ("readiness.json", report)):
            register(name, json_bytes(value))
        register("key_annotation_tasks.json", json_bytes({"class": "key", "tasks": key_tasks,
                    "required_for_video_verdict_training": False, "automatic_boxes_added": 0}))
        for name in ("labels", "splits", "actions", "objects", "people"):
            register(f"sources/{name}.json", json_bytes(inputs[name]))
        # Protect input annotations and every original even after the full decode.
        verify_sources(root, manifest)
        if input_hashes != {k: source_hash(local_source(root, v), 64 * 1024**2) for k, v in paths.items()}:
            raise ValueError("annotation inputs changed during import")
        return report

    return artifact_transaction(output_dir, key, build, max_bytes=128 * 1024**2, min_free_bytes=256 * 1024**2)


def verify_sources(root, manifest):
    validate_splits(manifest)
    for row in manifest["videos"]:
        if source_hash(local_source(Path(root), row["path"]), 2 * 1024**3) != row["sha256"]:
            raise ValueError("original source changed: " + row["video_id"])


def load_prepared(directory):
    from ml.data.extract_frames import _existing
    directory = Path(directory).resolve(strict=True)
    marker = read_json(directory / "artifacts.json")
    checked = _existing(directory, marker["cache_key"])
    report = read_json(directory / "readiness.json")
    manifest = read_json(directory / "manifest.json")
    if (report["format"] != FORMAT or report["video_training_ready"] is not True or report["production_ready"] is not False
            or report["manifest_sha256"] != stable_hash(manifest) or checked["data"] != report):
        raise ValueError("training package completion/readiness binding mismatch")
    validate_package_inputs(read_json(directory / "labels.json"), read_json(directory / "sources/splits.json"),
                            read_json(directory / "sources/actions.json"))
    verify_sources(report["source_root"], manifest)
    return report, manifest
