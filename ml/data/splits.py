"""Deterministic partitions over transitive source/scene/duplicate groups."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from contracts.python_ports import validate_contract
from ml.data.deduplicate import stable_hash


def _components(records: list[dict], near_candidates: list[dict]) -> list[list[str]]:
    ids = {row["video_id"] for row in records}
    parent = {key: key for key in ids}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def join(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    seen = {}
    for row in records:
        for field, value in (("canonical", row["canonical_id"]), ("group", row["group_id"]),
                             ("source", row["provenance"]["source_id"]), ("sha256", row["sha256"]),
                             ("scene", row["scene_id"])):
            identity = (field, value)
            if identity in seen:
                join(row["video_id"], seen[identity])
            else:
                seen[identity] = row["video_id"]
    for candidate in near_candidates:
        pair = candidate["video_ids"]
        if len(pair) != 2 or not set(pair) <= ids:
            raise ValueError("near-duplicate edge references unknown videos")
        join(*pair)
    groups = {}
    for key in sorted(ids):
        groups.setdefault(find(key), []).append(key)
    return sorted(groups.values())


def validate_splits(manifest: dict, *, near_candidates: list[dict] = ()) -> None:
    validate_contract("manifest", manifest)
    rows = {row["video_id"]: row for row in manifest["videos"]}
    for group in _components(manifest["videos"], near_candidates):
        if len({rows[key]["split"] for key in group}) != 1:
            raise ValueError("source/scene/duplicate cluster crosses partitions, including excluded")


def assign_splits(manifest: dict, *, eligible_video_ids: list[str], seed: int,
                  dev_fraction: float = 0.2, final_video_ids: list[str] = (),
                  near_candidates: list[dict] = (), final_independence_evidence: str | None = None) -> dict:
    validate_contract("manifest", manifest)
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= dev_fraction < 1:
        raise ValueError("integer seed and dev_fraction in [0,1) required")
    result = copy.deepcopy(manifest)
    records = result["videos"]
    ids = {row["video_id"] for row in records}
    eligible, final = set(eligible_video_ids), set(final_video_ids)
    if not eligible <= ids or not final <= eligible:
        raise ValueError("eligible/final IDs must reference eligible manifest videos")
    groups = _components(records, near_candidates)
    by_id = {row["video_id"]: row for row in records}
    # Ignore old assignment and input row order in the reproducible key.
    normalized = sorted(({**row, "split": "excluded"} for row in records), key=lambda r: r["video_id"])
    key = {"algorithm": "grouped-v1", "seed": seed, "manifest": normalized,
           "eligible": sorted(eligible), "final": sorted(final), "dev_fraction": dev_fraction,
           "components": groups, "final_independence_evidence": final_independence_evidence}
    working, held, excluded = [], [], []
    for group in groups:
        if not set(group) <= eligible:
            if set(group) & final:
                raise ValueError("final group has ineligible members; resolve rights/identity first")
            excluded.append(group)
        elif set(group) & final:
            held.append(group)
        else:
            working.append(group)
    working.sort(key=lambda group: stable_hash({"seed": seed, "group": group}))
    # Group counts, never a fabricated fixed video ratio. Small sets can have no dev.
    count_dev = int(len(working) * dev_fraction)
    if dev_fraction > 0 and len(working) >= 2:
        count_dev = max(1, min(count_dev, len(working) - 1))
    for split, partitions in (("excluded", excluded), ("independent_test", held),
                              ("dev_validation", working[:count_dev]), ("train", working[count_dev:])):
        for group in partitions:
            for video_id in group:
                by_id[video_id]["split"] = split
    result["videos"] = sorted(records, key=lambda r: r["video_id"])
    result["split_version"] = "grouped-v1-" + stable_hash(key)
    validate_splits(result, near_candidates=near_candidates)
    counts = {split: sum(r["split"] == split for r in records)
              for split in ("train", "dev_validation", "independent_test", "excluded")}
    limitations = ["Reviewed annotations and data rights must be checked again before training."]
    if not held:
        limitations.append("No independent final groups selected.")
    if not final_independence_evidence:
        limitations.append("Independence of final viewpoint/unseen sources is unverified.")
    if not counts["train"] or not counts["dev_validation"]:
        limitations.append("Insufficient eligible groups for both train and dev.")
    if any(row["provenance"]["kind"] == "synthetic" for row in records):
        limitations.append("Synthetic fixtures test code only; they do not establish a real dataset.")
    return {"manifest": result, "audit": {"split_algorithm": "grouped-v1", "seed": seed,
            "input_sha256": stable_hash(key), "components": groups, "counts": counts,
            "final_independence_evidence": final_independence_evidence,
            "final_independence": "human_asserted_not_verified" if final_independence_evidence else "unverified",
            "data_state": "split_candidate" if eligible else "data_not_ready",
            "training_ready": False, "limitations": limitations}}


def records_for(manifest: dict, *, purpose: str, near_candidates: list[dict] = ()) -> list[dict]:
    validate_splits(manifest, near_candidates=near_candidates)
    purposes = {"training": "train", "threshold_calibration": "dev_validation",
                "final_evaluation": "independent_test"}
    if purpose not in purposes:
        raise ValueError("explicit training/threshold_calibration/final_evaluation purpose required")
    return [copy.deepcopy(row) for row in manifest["videos"] if row["split"] == purposes[purpose]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="import bundle from ml.data.manifest")
    parser.add_argument("--output", required=True, type=Path, help="new JSON bundle; never overwrite")
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--dev-fraction", type=float, default=0.2)
    parser.add_argument("--final-video-id", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        bundle = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if bundle["manifest"] is None:
            raise ValueError("data_not_ready: no valid videos")
        eligible = [row["video_id"] for row in bundle["audit"]["sources"] if row["eligible_for_split"]]
        result = assign_splits(bundle["manifest"], eligible_video_ids=eligible, seed=args.seed,
                               dev_fraction=args.dev_fraction, final_video_ids=args.final_video_id,
                               near_candidates=bundle["duplicates"]["near_candidates"])
        bundle["manifest"] = result["manifest"]
        bundle["split_audit"] = result["audit"]
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(bundle, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({"counts": result["audit"]["counts"], "training_ready": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
