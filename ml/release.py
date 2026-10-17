"""Strict local model packages and atomic activation; default rejects all smoke packages."""
from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import threading

import torch

from contracts.python_ports import ModelNotReady, validate_contract
from ml.cache import CacheSpec, encoder_fingerprint
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import artifact_transaction
from ml.data.manifest import local_source
from ml.data.taxonomy import class_ids, validate_taxonomy
from ml.evaluate import validate_training_lineage
from ml.export import _production_gate, contract_preprocessing, model_budget
from ml.models import FrozenEncoder, ModelConfig, VideoActionModel
from ml.models.encoder import file_sha256, safe_torch_load
from ml.preprocessing import PreprocessConfig
from ml.thresholds import validate_thresholds


FILES = {"model.pt": "checkpoint", "config.json": "config", "taxonomy.json": "taxonomy",
         "preprocessing.json": "preprocessing", "thresholds.json": "thresholds", "metrics.json": "metrics",
         "MODEL_CARD.md": "model_card", "rules.json": "rules", "split.json": "split", "annotations.json": "annotations"}


@dataclass(frozen=True)
class LoadedRelease:
    directory: Path
    manifest_name: str
    manifest_sha256: str
    manifest: dict
    config: dict
    thresholds: dict
    model: VideoActionModel
    test_only: bool

    def descriptor(self):
        return {"path": str(self.directory), "manifest": self.manifest_name,
                "manifest_sha256": self.manifest_sha256, "release_version": self.config["release_version"],
                "test_only": self.test_only, "trained": not self.test_only, "validated": not self.test_only}


def load_package(directory: Path, *, allow_test: bool = False, expected_taxonomy: str | None = None,
                 expected_rules: str | None = None, expected_manifest_sha256: str | None = None) -> LoadedRelease:
    try:
        if type(allow_test) is not bool:
            raise ValueError("explicit boolean test opt-in required")
        root = Path(directory)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("missing/unsafe model package directory")
        root = root.resolve(strict=True)
        production = (root / "release.json").is_file()
        name = "release.json" if production else "package.json"
        if not production and not allow_test:
            raise ValueError("untrained/test-only package cannot activate production")
        before = file_sha256(root / name, max_bytes=1024**2)
        if expected_manifest_sha256 is not None and before != expected_manifest_sha256:
            raise ValueError("manifest SHA-256 mismatch")
        manifest = read_json(root / name, max_bytes=1024**2)
        if production:
            validate_contract("release", manifest)
            if (manifest["intended_use"] != "production" or manifest["training_status"] != "trained"
                    or manifest["metrics"]["validation_status"] != "validated"
                    or manifest["metrics"]["independent_test"] is not True):
                raise ValueError("release is not trained/validated production")
            if not expected_taxonomy or not expected_rules:
                raise ValueError("trusted expected taxonomy/rules versions required for production")
        elif (manifest.get("version") != "smoke-package-v1" or manifest.get("intended_use") != "test_only"
              or manifest.get("training_status") != "untrained" or manifest.get("validation_status") != "not_validated"):
            raise ValueError("unsupported software smoke package")
        entries = manifest["files"]
        if (len(entries) != len(FILES) or {r["path"]: r["role"] for r in entries} != FILES
                or len({r["path"] for r in entries}) != len(entries)):
            raise ValueError("missing/duplicate/unknown release paths or roles")
        allowed = set(FILES) | {name, "artifacts.json"}
        for count, path in enumerate(root.iterdir()):
            if count >= len(allowed) or path.name not in allowed or path.is_symlink() or not path.is_file():
                raise ValueError("unexpected or unsafe package file")
        total = 0
        for entry in entries:
            if (set(entry) != {"path", "sha256", "size_bytes", "role"}
                    or type(entry["size_bytes"]) is not int or not 0 < entry["size_bytes"] <= 16000000):
                raise ValueError("invalid artifact size/entry")
            total += entry["size_bytes"]
            if total > 48000000:
                raise ValueError("release byte budget")
            path = local_source(root, entry["path"])
            if path.stat().st_size != entry["size_bytes"] or file_sha256(path, max_bytes=16000000) != entry["sha256"]:
                raise ValueError("release artifact hash/size mismatch")
        config = read_json(root / "config.json", max_bytes=2 * 1024**2)
        taxonomy = read_json(root / "taxonomy.json", max_bytes=1024**2)
        thresholds = read_json(root / "thresholds.json", max_bytes=2 * 1024**2)
        metrics = read_json(root / "metrics.json", max_bytes=16000000)
        split = read_json(root / "split.json", max_bytes=16000000)
        annotations = read_json(root / "annotations.json", max_bytes=1024**2)
        rules = read_json(root / "rules.json", max_bytes=1024**2)
        if (config["version"] != "model-package-v1" or config["release_version"] != manifest["release_version"]
                or config["test_only"] is not (not production) or config["trained"] is not production
                or config["validated"] is not production or type(config["optimizer_steps"]) is not int
                or config["optimizer_steps"] < 1 or config["training_smoke"] is not (not production)):
            raise ValueError("release provenance/config mismatch")
        architecture = ModelConfig(**config["architecture"])
        preprocessing = PreprocessConfig(**config["preprocessing"])
        if (read_json(root / "preprocessing.json") != config["preprocessing"]
                or config["contract_preprocessing"] != contract_preprocessing(preprocessing)):
            raise ValueError("preprocessing version/normalization mismatch")
        validate_taxonomy(taxonomy)
        spec = CacheSpec.from_dict(config["training_spec"])
        if (config["class_ids"] != list(spec.class_ids) or architecture.classes != len(spec.class_ids)
                or tuple(key for key in class_ids(taxonomy, include_states=True) if key in spec.class_ids) != spec.class_ids
                or stable_hash(taxonomy) != spec.taxonomy_sha256 or stable_hash(config["encoder"]) != spec.encoder_sha256
                or preprocessing.fingerprint() != spec.preprocessing_sha256):
            raise ValueError("taxonomy/encoder/preprocessing/class lineage mismatch")
        if (expected_taxonomy is not None and taxonomy["version"] != expected_taxonomy
                or expected_rules is not None and rules["version"] != expected_rules
                or rules["version"] != config["versions"]["rules"]
                or annotations != {"version": config["versions"]["annotations"], "sha256": spec.annotation_sha256}
                or split["version"] != config["versions"]["split"] or split["sha256"] != spec.split_sha256):
            raise ValueError("incompatible rules/taxonomy/annotation/split versions")
        validate_training_lineage(spec, split["manifest"])
        if (stable_hash(split["manifest"]) != split["manifest_sha256"]
                or metrics["split_manifest"] != split["manifest"]):
            raise ValueError("split manifest mismatch")
        validate_thresholds(thresholds)
        for field, expected in (("class_ids", list(spec.class_ids)), ("dataset_sha256", spec.dataset_sha256),
                                ("taxonomy_sha256", spec.taxonomy_sha256), ("test_only", spec.test_only),
                                ("manifest_sha256", split["manifest_sha256"]),
                                ("checkpoint_sha256", config["training_checkpoint_sha256"])):
            if thresholds[field] != expected or metrics[field] != expected:
                raise ValueError("threshold/metrics/version fingerprint mismatch")
        videos = {row["video_id"]: row for row in split["manifest"]["videos"]}
        if (not thresholds["dev_video_ids"] or any(videos[k]["split"] != "dev_validation" for k in thresholds["dev_video_ids"])
                or metrics["thresholds_sha256"] != stable_hash(thresholds)):
            raise ValueError("threshold calibration must remain dev-only")
        metadata = config["encoder"]
        if production:
            _production_gate(spec, metadata, taxonomy, thresholds, metrics, config["release_approval"],
                             config["training_checkpoint_sha256"])
            if (manifest["taxonomy"] != {"path": "taxonomy.json", "version": taxonomy["version"], "status": "final"}
                    or manifest["preprocessing"] != config["contract_preprocessing"] or manifest["versions"] != config["versions"]
                    or manifest["model_config"] != {"gru_hidden_size": 256, "gru_layers": 1, "classes": architecture.classes}
                    or manifest["checkpoint"] != "model.pt" or manifest["thresholds"] != "thresholds.json"
                    or manifest["metrics"]["path"] != "metrics.json" or manifest["model_card"] != "MODEL_CARD.md"):
                raise ValueError("K manifest/config mismatch")
        elif manifest["actual_weights"] != metadata["weights"]:
            raise ValueError("smoke encoder provenance mismatch")
        # A local shape skeleton is fully overwritten before it is exposed. Never download weights.
        encoder = FrozenEncoder(test_only=True, seed=metadata.get("seed") or 42)
        model = VideoActionModel(encoder, architecture)
        checkpoint_entry = next(row for row in entries if row["path"] == "model.pt")
        state = safe_torch_load(root / "model.pt", expected_sha256=checkpoint_entry["sha256"], max_bytes=12000000)
        model.load_state_dict(state, strict=True)
        encoder.test_only, encoder.weights_sha256, encoder.seed = metadata["test_only"], metadata["weights_sha256"], metadata["seed"]
        if encoder.descriptor() != metadata or encoder_fingerprint(encoder) != metadata["state_sha256"]:
            raise ValueError("loaded encoder tensors/runtime differ from declared encoder")
        budget = model_budget(state, checkpoint_entry["size_bytes"], config["budget"]["training_checkpoint_bytes_with_optimizer"])
        if budget != config["budget"] or not budget["passed"]:
            raise ValueError("whole model size budget mismatch")
        if production and (spec.test_only or metadata["test_only"] or metadata["weights"] != "IMAGENET1K_V1"):
            raise ValueError("test encoder cannot be production")
        if file_sha256(root / name, max_bytes=1024**2) != before:
            raise ValueError("manifest changed during loading")
        for entry in entries:
            if file_sha256(root / entry["path"], max_bytes=16000000) != entry["sha256"]:
                raise ValueError("artifact changed during loading")
        model.requires_grad_(False).eval()
        return LoadedRelease(root, name, before, copy.deepcopy(manifest), copy.deepcopy(config),
                             copy.deepcopy(thresholds), model, not production)
    except ModelNotReady:
        raise
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
        raise ModelNotReady(f"model_not_ready: {error}") from error


class ReleaseManager:
    def __init__(self, *, allow_test=False, expected_taxonomy=None, expected_rules=None):
        if type(allow_test) is not bool:
            raise ValueError("explicit boolean test opt-in required")
        self.options = {"allow_test": allow_test, "expected_taxonomy": expected_taxonomy, "expected_rules": expected_rules}
        self._active = None
        self._lock = threading.RLock()

    def readiness(self):
        with self._lock:
            active = self._active
        ready = active is not None and not active.test_only
        return {"schema_version": "1.0", "status": "ready" if ready else "not_ready",
                "reason": None if ready else "model_not_ready: no trained and validated production release",
                "release_version": None if active is None else active.config["release_version"],
                "trained": ready, "validated": ready, "test_only": bool(active and active.test_only),
                "limitations": [] if ready else ["Software smoke does not establish real model quality."]}

    def snapshot(self):
        with self._lock:
            if self._active is None:
                raise ModelNotReady("model_not_ready: release is absent")
            return self._active

    def load(self, directory, *, expected_manifest_sha256=None, pointer=None):
        candidate = load_package(directory, expected_manifest_sha256=expected_manifest_sha256, **self.options)
        with self._lock:
            old = self._active
            if pointer is not None:
                pointer = Path(pointer)
                if pointer.is_symlink() or (pointer.exists() and not pointer.is_file()):
                    raise ModelNotReady("model_not_ready: unsafe active pointer")
                parent = pointer.parent.resolve(strict=True)
                old_descriptor = None if old is None else old.descriptor()
                if old_descriptor is None and pointer.exists():
                    prior = read_json(pointer, max_bytes=65536)
                    if prior["version"] != "active-release-v1":
                        raise ModelNotReady("model_not_ready: unsupported existing pointer")
                    old_descriptor = prior["active"]
                descriptor = {"version": "active-release-v1", "active": candidate.descriptor(),
                              "previous": old_descriptor}
                handle, temporary = tempfile.mkstemp(prefix=".fortress-release-", dir=parent)
                temp = Path(temporary)
                try:
                    with os.fdopen(handle, "wb") as output:
                        output.write(json.dumps(descriptor, indent=2, allow_nan=False).encode() + b"\n")
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temp, parent / pointer.name)
                finally:
                    if temp.parent == parent and temp.name.startswith(".fortress-release-"):
                        temp.unlink(missing_ok=True)
            self._active = candidate
        return candidate.descriptor()

    def restore_pointer(self, pointer, *, previous=False):
        document = read_json(pointer, max_bytes=65536)
        if document["version"] != "active-release-v1":
            raise ModelNotReady("model_not_ready: active pointer version")
        target = document["previous" if previous else "active"]
        if not target:
            raise ModelNotReady("model_not_ready: rollback target absent")
        return self.load(target["path"], expected_manifest_sha256=target["manifest_sha256"],
                         pointer=pointer if previous else None)


def import_package(source, destination, **options):
    options = dict(options)
    expected_manifest = options.pop("expected_manifest_sha256", None)
    loaded = load_package(source, expected_manifest_sha256=expected_manifest, **options)
    names = list(FILES) + [loaded.manifest_name]
    def build(staging, register):
        for name in names:
            register(name, (loaded.directory / name).read_bytes())
        copied = load_package(staging, expected_manifest_sha256=loaded.manifest_sha256, **options)
        return {"kind": "model-import-v1", "manifest_sha256": copied.manifest_sha256,
                "release_version": copied.config["release_version"], "test_only": copied.test_only,
                "production_ready": not copied.test_only}
    return artifact_transaction(destination, loaded.manifest_sha256, build,
                                max_bytes=48000000, min_free_bytes=128 * 1024**2)
