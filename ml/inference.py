"""Deadline-bounded offline inference through the same PTS/preprocessing baseline."""
from __future__ import annotations

from pathlib import Path
import math
import time

import numpy as np
import torch

from contracts.python_ports import ModelNotReady
from ml.data.manifest import ProbeLimits, build_manifest
from ml.data.pts_index import build_index, iter_indexed_frames, validate_index
from ml.data.scenes import define_scenes, validate_scenes
from ml.intervals import timeline_from_scores
from ml.preprocessing import PreprocessConfig, preprocess_image
from ml.release import ReleaseManager
from ml.windows import labelled_windows, merge_scores, sample_key


class InferenceFailed(RuntimeError):
    """After admission this is a failed job, never a clean result."""


def check_deadline(deadline):
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or time.monotonic() >= deadline:
        raise InferenceFailed("analysis_deadline_exceeded")


class TimelineAdapter:
    def __init__(self, releases: ReleaseManager, *, allow_test=False, visibility_provider=None):
        if type(allow_test) is not bool:
            raise ValueError("explicit boolean test inference opt-in required")
        self.releases = releases
        self.allow_test = allow_test
        # Optional independently established context; a high CNN score cannot supply it.
        self.visibility_provider = visibility_provider

    def _snapshot(self):
        snapshot = self.releases.snapshot()
        if snapshot.test_only and not self.allow_test:
            raise ModelNotReady("model_not_ready: test package is not production inference")
        return snapshot

    def infer(self, path: Path, *, deadline_monotonic: float):
        snapshot = self._snapshot()
        check_deadline(deadline_monotonic)
        path = Path(path)
        try:
            limits = ProbeLimits(max_decode_seconds=min(120., max(.001, deadline_monotonic - time.monotonic())))
            bundle = build_manifest(path.parent, [{"path": path.name, "source_id": "inference-local-original",
                                    "group_id": "inference-local-original", "kind": "original", "rights": "unknown"}],
                                    dataset_version="inference-only-not-training-v1", limits=limits)
            if not bundle["manifest"]:
                raise InferenceFailed("decode_unsupported_or_corrupt")
            record = bundle["manifest"]["videos"][0]
            check_deadline(deadline_monotonic)
            index = build_index(path.parent, record, dataset_version="inference-only-not-training-v1",
                                split_version="excluded-from-training", limits=limits)
            scenes = define_scenes(index)
            # Unreviewed raw input defaults to one scene; supplied reviewed cuts can use infer_indexed.
            return self.infer_indexed(path.parent, index, scenes, deadline_monotonic=deadline_monotonic,
                                      _snapshot=snapshot)
        except (InferenceFailed, ModelNotReady):
            raise
        except Exception as error:
            raise InferenceFailed(f"decode_or_inference_failed:{type(error).__name__}") from error

    def infer_indexed(self, source_root, index, scenes, *, deadline_monotonic, _snapshot=None):
        snapshot = self._snapshot() if _snapshot is None else _snapshot
        if snapshot.test_only and not self.allow_test:
            raise ModelNotReady("model_not_ready: test package is not production inference")
        check_deadline(deadline_monotonic)
        try:
            validate_index(index)
            validate_scenes(index, scenes)
            classes = snapshot.config["class_ids"]
            windows = labelled_windows(index, scenes, {"records": []}, classes, max_samples=4096)
            if len(windows) > 256:
                raise ValueError("inference window budget")
            wanted = {sample_key(w, s) for w in windows for s in w["samples"] if s is not None and s["image_mask"]}
            memo = {}
            preprocessing = PreprocessConfig(**snapshot.config["preprocessing"])
            with torch.inference_mode():
                for row, frame in iter_indexed_frames(source_root, index):
                    check_deadline(deadline_monotonic)
                    scene = next(s for s in scenes["scenes"] if s["start_ordinal"] <= row["ordinal"] < s["end_ordinal"])
                    key = (index["video_id"], scene["scene_id"], index["split"], row["source_pts"])
                    if key in wanted:
                        image = preprocess_image(frame.to_image(), rotation=index["rotation"], config=preprocessing)["tensor"]
                        feature = snapshot.model.encoder(image[None])[0]
                        if feature.shape != (576,) or not bool(torch.isfinite(feature).all()):
                            raise ValueError("invalid inference features")
                        memo[key] = feature.numpy().copy()
                if set(memo) != wanted:
                    raise ValueError("missing decoded source PTS")
                scores = []
                for window in windows:
                    check_deadline(deadline_monotonic)
                    features = np.zeros((len(window["samples"]), 576), dtype=np.float32)
                    for n, sample in enumerate(window["samples"]):
                        if sample is not None and sample["image_mask"]:
                            features[n] = memo[sample_key(window, sample)]
                    # Each window starts fresh and is wholly within one scene. No job/session state leaks.
                    logits, _ = snapshot.model.temporal(torch.from_numpy(features)[None],
                                image_mask=torch.tensor(window["image_mask"], dtype=torch.bool)[None])
                    scores.append(torch.sigmoid(logits[0]).numpy())
                merged = merge_scores(windows, scores)
            check_deadline(deadline_monotonic)
            timeline = timeline_from_scores(merged, scenes, video_id=index["video_id"], class_ids=classes,
                                        thresholds=snapshot.thresholds["values"], model_version=snapshot.config["release_version"],
                                        preprocessing_version=preprocessing.version,
                                        visibility_provider=self.visibility_provider)
            check_deadline(deadline_monotonic)
            return timeline
        except (InferenceFailed, ModelNotReady):
            raise
        except Exception as error:
            raise InferenceFailed(f"decode_or_inference_failed:{type(error).__name__}") from error
