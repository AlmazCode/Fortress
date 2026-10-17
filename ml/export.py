"""Immutable local tensor packages. Random smoke packages are never K production releases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import torch

from contracts.python_ports import validate_contract
from ml.cache import CacheSpec, encoder_fingerprint
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import artifact_transaction
from ml.data.taxonomy import class_ids, validate_taxonomy
from ml.models import FrozenEncoder, ModelConfig, VideoActionModel
from ml.models.encoder import file_sha256, safe_torch_load
from ml.evaluate import validate_training_lineage
from ml.preprocessing import PreprocessConfig
from ml.thresholds import validate_thresholds


def model_budget(state, serialized_bytes, training_checkpoint_bytes):
    if not state or any(not isinstance(v, torch.Tensor) or (v.is_floating_point() and v.dtype != torch.float32)
                        for v in state.values()):
        raise ValueError("export requires complete FP32 model state")
    sizes = {name: tensor.numel() * tensor.element_size() for name, tensor in state.items()}
    if not any(k.startswith("encoder.features.") for k in sizes) or not any(k.startswith("temporal.head.") for k in sizes):
        raise ValueError("whole encoder+GRU+head required in budget")
    total = sum(sizes.values())
    return {"version": "fp32-model-budget-v1", "units": {"MB": 1000000, "MiB": 1048576},
            "encoder_tensor_bytes": sum(v for k, v in sizes.items() if k.startswith("encoder.")),
            "gru_head_tensor_bytes": sum(v for k, v in sizes.items() if k.startswith("temporal.")),
            "whole_model_tensor_bytes": total, "whole_model_file_bytes": serialized_bytes,
            "whole_model_file_MB": serialized_bytes / 1000000,
            "whole_model_file_MiB": serialized_bytes / 1048576,
            "all_model_files_bytes": serialized_bytes, "training_checkpoint_bytes_with_optimizer": training_checkpoint_bytes,
            "whole_model_limit_bytes": 12000000, "all_models_limit_bytes": 35000000,
            "passed": max(total, serialized_bytes) <= 12000000 and serialized_bytes <= 35000000,
            "scope": "This exact class count only; production taxonomy/performance remain unverified for smoke."}


def contract_preprocessing(config):
    return {"version": config.version, "size": 224, "fps": 2, "window_frames": 32,
            "overlap": .5, "views": 1, "resize": "letterbox", "mean": list(config.mean), "std": list(config.std)}


def _production_gate(spec, encoder, taxonomy, thresholds, metrics, approval, checkpoint_sha):
    expected = {"checkpoint_sha256": checkpoint_sha, "metrics_sha256": stable_hash(metrics),
                "taxonomy_sha256": stable_hash(taxonomy), "dataset_sha256": spec.dataset_sha256}
    if (spec.test_only or encoder["test_only"] or encoder["weights"] != "IMAGENET1K_V1"
            or any(r["provenance"]["kind"] != "original" for r in metrics["split_manifest"]["videos"] if r["split"] != "excluded")
            or taxonomy["status"] != "reviewed" or taxonomy["production_ready"] is not True
            or metrics["test_only"] or metrics["split"] != "independent_test"
            or any(v is None for v in thresholds["values"].values())
            or not isinstance(approval, dict) or approval.get("approved") is not True
            or not isinstance(approval.get("reviewer"), str) or not approval["reviewer"].strip()
            or any(approval.get(k) != v for k, v in expected.items())
            or any(approval.get(k) is not True for k in ("independence_verified", "rights_verified", "real_data_verified"))):
        raise ValueError("production requires real pretrained data, final human taxonomy and verified independent release approval")
    verdict = metrics.get("verdict_metrics")
    if (not verdict or any(verdict.get(k) is None or verdict[k] < .8
                           for k in ("accuracy", "balanced_accuracy", "macro_f1", "accuracy_over_all_known"))):
        raise ValueError("real independent verdict targets have not been established")


def export_package(checkpoint_path: Path, destination: Path, *, taxonomy: dict, thresholds: dict,
                   metrics: dict, versions: dict, release_version: str, production: bool = False,
                   approval: dict | None = None, encoder_weights: Path | None = None,
                   encoder_sha256: str | None = None):
    if (not isinstance(release_version, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", release_version) is None
            or set(versions) != {"dataset", "split", "annotations", "rules"}
            or any(not isinstance(v, str) or not v.strip() for v in versions.values())):
        raise ValueError("explicit release/version lineage required")
    checkpoint = safe_torch_load(checkpoint_path)
    checkpoint_sha = file_sha256(checkpoint_path)
    signature = checkpoint["signature"]
    if (checkpoint["checkpoint_version"] != "training-checkpoint-v1"
            or stable_hash(signature) != checkpoint["signature_sha256"] or checkpoint["completed_steps"] < 1):
        raise ValueError("export requires a compatible nonempty optimizer smoke/run")
    spec = CacheSpec.from_dict(signature["training_spec"])
    if spec.partition != "train" or spec.key() != signature["cache_key"]:
        raise ValueError("invalid training provenance")
    validate_taxonomy(taxonomy)
    available = class_ids(taxonomy, include_states=True)
    ordered = tuple(key for key in available if key in spec.class_ids)
    if ordered != spec.class_ids or stable_hash(taxonomy) != spec.taxonomy_sha256:
        raise ValueError("export taxonomy/order differs from training cache")
    validate_thresholds(thresholds)
    if (thresholds["checkpoint_sha256"] != checkpoint_sha or metrics["checkpoint_sha256"] != checkpoint_sha
            or metrics["thresholds_sha256"] != stable_hash(thresholds) or metrics["version"] != "ml-evaluation-v1"):
        raise ValueError("threshold/metrics/checkpoint fingerprint mismatch")
    for field, expected in (("class_ids", list(spec.class_ids)), ("dataset_sha256", spec.dataset_sha256),
                            ("taxonomy_sha256", spec.taxonomy_sha256), ("test_only", spec.test_only)):
        if thresholds[field] != expected or metrics[field] != expected:
            raise ValueError("export metrics/thresholds/training lineage mismatch")
    if thresholds["manifest_sha256"] != metrics["manifest_sha256"]:
        raise ValueError("calibration/evaluation split manifest changed")
    split_manifest = metrics["split_manifest"]
    validate_training_lineage(spec, split_manifest)
    videos = {r["video_id"]: r for r in split_manifest["videos"]}
    if (metrics["manifest_sha256"] != stable_hash(split_manifest) or not thresholds["dev_video_ids"]
            or any(videos[k]["split"] != "dev_validation" for k in thresholds["dev_video_ids"])):
        raise ValueError("threshold selection must reference actual dev-only sources")
    preprocessing = PreprocessConfig(**signature["preprocessing"])
    encoder_meta = signature["encoder"]
    encoder = FrozenEncoder(test_only=spec.test_only, seed=encoder_meta.get("seed", 42),
                            weights_path=encoder_weights, weights_sha256=encoder_sha256)
    model = VideoActionModel(encoder, ModelConfig(**signature["architecture"]))
    model.load_state_dict(checkpoint["model"], strict=True)
    if encoder_fingerprint(model.encoder) != encoder_meta["state_sha256"]:
        raise ValueError("export encoder changed")
    if production:
        _production_gate(spec, encoder_meta, taxonomy, thresholds, metrics, approval, checkpoint_sha)
    request = {"checkpoint_sha256": checkpoint_sha, "taxonomy": taxonomy, "thresholds": thresholds,
               "metrics": metrics, "versions": versions, "release_version": release_version,
               "production": production, "approval": approval}

    def build(staging, register):
        state = {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}
        torch.save(state, staging / "model.pt")
        budget = model_budget(state, (staging / "model.pt").stat().st_size, Path(checkpoint_path).stat().st_size)
        if not budget["passed"]:
            raise ValueError("whole FP32 encoder+GRU+head exceeds 12 MB or all models exceed 35 MB")
        config = {"version": "model-package-v1", "release_version": release_version,
                  "architecture": signature["architecture"], "class_ids": list(spec.class_ids),
                  "encoder": encoder_meta, "training_spec": spec.descriptor(),
                  "training_checkpoint_sha256": checkpoint_sha, "optimizer_steps": checkpoint["completed_steps"],
                  "training_smoke": signature["smoke"], "preprocessing": signature["preprocessing"],
                  "contract_preprocessing": contract_preprocessing(preprocessing), "budget": budget,
                  "versions": versions, "test_only": not production, "trained": production,
                  "validated": production, "release_approval": approval if production else None}
        documents = {"config.json": ("config", config), "taxonomy.json": ("taxonomy", taxonomy),
                     "preprocessing.json": ("preprocessing", signature["preprocessing"]),
                     "thresholds.json": ("thresholds", thresholds), "metrics.json": ("metrics", metrics),
                     "rules.json": ("rules", {"version": versions["rules"], "applicability_verified": False,
                                               "note": "External rules provenance/applicability belongs to R; version reference only."}),
                     "split.json": ("split", {"version": versions["split"], "sha256": spec.split_sha256,
                                               "manifest_sha256": metrics["manifest_sha256"], "manifest": split_manifest}),
                     "annotations.json": ("annotations", {"version": versions["annotations"],
                                                            "sha256": spec.annotation_sha256})}
        files = [{**register("model.pt"), "role": "checkpoint"}]
        for path, (role, document) in documents.items():
            files.append({**register(path, json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False).encode() + b"\n"),
                          "role": role})
        card = (f"# {release_version}\n\n"
                f"Intended use: {'production after recorded independent approval' if production else 'test-only software smoke'}.\n"
                f"Encoder weights: {encoder_meta['weights']}; test provenance: {spec.test_only}.\n"
                f"Frozen MobileNetV3-Small features576, GRU1x256, Linear{len(spec.class_ids)}.\n"
                "One view, RGB letterbox224/ImageNet normalization, 2fps, windows32, stride16.\n"
                "Action scores do not identify actors or establish legal violations. Unobservable labels/relations remain unknown.\n"
                f"Whole model: {budget['whole_model_file_bytes']} bytes; encoder: {budget['encoder_tensor_bytes']} tensor bytes; "
                f"GRU/head: {budget['gru_head_tensor_bytes']} tensor bytes. Optimizer checkpoint excluded from inference package.\n"
                "Smoke metrics measure code only. Real independent >=0.80 quality, production taxonomy budget, latency/RAM/VRAM "
                "are not established by synthetic smoke. Full training/fine-tuning/GPU search were not run for this delivery.\n")
        files.append({**register("MODEL_CARD.md", card.encode()), "role": "model_card"})
        # artifact_transaction calls this field size_bytes; K uses the same unit.
        listed = [{"path": f["path"], "size_bytes": f["size_bytes"], "sha256": f["sha256"], "role": f["role"]} for f in files]
        if production:
            manifest = {"schema_version": "1.0", "release_version": release_version, "intended_use": "production",
                        "training_status": "trained", "checkpoint": "model.pt", "backbone": "mobilenet_v3_small",
                        "weights": "IMAGENET1K_V1", "feature_dim": 576,
                        "model_config": {"gru_hidden_size": 256, "gru_layers": 1, "classes": len(spec.class_ids)},
                        "taxonomy": {"path": "taxonomy.json", "version": taxonomy["version"], "status": "final"},
                        "preprocessing": contract_preprocessing(preprocessing), "thresholds": "thresholds.json",
                        "metrics": {"path": "metrics.json", "validation_status": "validated", "independent_test": True},
                        "model_card": "MODEL_CARD.md", "versions": versions, "files": listed}
            validate_contract("release", manifest)
            manifest_name = "release.json"
        else:
            # K fixes weights=IMAGENET1K_V1 even for test_only. Never assert that for random weights.
            manifest = {"version": "smoke-package-v1", "release_version": release_version,
                        "intended_use": "test_only", "training_status": "untrained", "validation_status": "not_validated",
                        "actual_weights": encoder_meta["weights"], "checkpoint": "model.pt", "files": listed}
            manifest_name = "package.json"
        register(manifest_name, json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False).encode() + b"\n")
        if file_sha256(checkpoint_path) != checkpoint_sha:
            raise ValueError("training checkpoint changed during export")
        return {"kind": "model-export-v1", "manifest": manifest_name, "test_only": not production,
                "production_ready": production, "budget": budget, "release_version": release_version}
    return artifact_transaction(destination, stable_hash(request), build, max_bytes=48 * 1024**2,
                                min_free_bytes=128 * 1024**2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("checkpoint", "taxonomy", "thresholds", "metrics", "metadata", "output-dir"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--encoder-weights", type=Path)
    parser.add_argument("--encoder-sha256")
    args = parser.parse_args(argv)
    try:
        metadata = read_json(args.metadata)
        result = export_package(args.checkpoint, args.output_dir, taxonomy=read_json(args.taxonomy),
                                thresholds=read_json(args.thresholds), metrics=read_json(args.metrics),
                                versions=metadata["versions"], release_version=metadata["release_version"],
                                production=args.production, approval=None if args.approval is None else read_json(args.approval),
                                encoder_weights=args.encoder_weights, encoder_sha256=args.encoder_sha256)
        print(json.dumps(result["data"], indent=2))
        return 0
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
        parser.exit(1, f"export refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
