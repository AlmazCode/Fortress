"""Versioned grid calibration restricted to the immutable dev partition."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.evaluate import binary_metrics, validate_packet, write_new_json


def calibrate(packet, *, grid=tuple(n / 10 for n in range(1, 10))):
    validate_packet(packet)
    if packet["split"] != "dev_validation":
        raise ValueError("thresholds may be selected only on dev_validation, never train/final")
    if (not 1 <= len(grid) <= 101 or len(set(grid)) != len(grid)
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v < 1 for v in grid)):
        raise ValueError("invalid predeclared calibration grid")
    values, evidence = {}, {}
    for column, key in enumerate(packet["class_ids"]):
        rows = [(r["targets"][column], r["scores"][column]) for r in packet["samples"]
                if r["targets"][column] is not None and r["scores"][column] is not None]
        positives, negatives = sum(y for y, _ in rows), sum(not y for y, _ in rows)
        evidence[key] = {"known_positive": positives, "known_negative": negatives}
        if not positives or not negatives:
            values[key] = None
            evidence[key]["status"] = "uncalibrated_missing_positive_or_negative"
            continue
        candidates = []
        for threshold in grid:
            metric = binary_metrics([y for y, _ in rows], [score >= threshold for _, score in rows])
            f1 = metric["per_class"][1]["f1"]
            candidates.append((f1, -abs(threshold - .5), threshold))
        best = max(candidates)
        values[key] = best[-1]
        evidence[key].update(status="calibrated_dev_only", positive_f1=best[0])
    return {"version": "threshold-grid-v1", "selected_on": "dev_validation", "values": values,
            "class_ids": list(packet["class_ids"]), "grid": list(grid), "evidence": evidence,
            "objective": "positive_f1_then_closest_to_0.5_then_higher_threshold",
            "input_sha256": stable_hash(packet), "manifest_sha256": packet["manifest_sha256"],
            "dataset_sha256": packet["dataset_sha256"], "taxonomy_sha256": packet["taxonomy_sha256"],
            "checkpoint_sha256": packet["checkpoint_sha256"], "test_only": packet["test_only"],
            "event_protocol": dict(packet["event_protocol"]),
            "dev_video_ids": sorted({r["video_id"] for r in packet["samples"]})}


def validate_thresholds(document, packet=None):
    if (document["version"] != "threshold-grid-v1" or document["selected_on"] != "dev_validation"
            or type(document["test_only"]) is not bool or document["class_ids"] != list(document["values"])
            or not 1 <= len(document["class_ids"]) <= 256):
        raise ValueError("invalid threshold version/partition/class order")
    for value in document["values"].values():
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 1):
            raise ValueError("threshold must be a probability or uncalibrated/null")
    for field in ("input_sha256", "manifest_sha256", "dataset_sha256", "taxonomy_sha256", "checkpoint_sha256"):
        if not isinstance(document[field], str) or re.fullmatch(r"[a-f0-9]{64}", document[field]) is None:
            raise ValueError("threshold provenance needs full SHA-256")
    if packet is not None:
        for field in ("class_ids", "manifest_sha256", "dataset_sha256", "taxonomy_sha256", "checkpoint_sha256",
                      "test_only", "event_protocol"):
            if document[field] != packet[field]:
                raise ValueError("threshold/evaluation model, dataset, protocol or taxonomy mismatch")
        rows = {r["video_id"]: r for r in packet["manifest"]["videos"]}
        if not document["dev_video_ids"] or any(rows[k]["split"] != "dev_validation" for k in document["dev_video_ids"]):
            raise ValueError("threshold provenance does not identify dev-only sources")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = calibrate(read_json(args.input))
        validate_thresholds(result)
        write_new_json(args.output, result)
        print(json.dumps({"selected_on": result["selected_on"], "values": result["values"],
                          "production_ready": False}))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"calibration refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
