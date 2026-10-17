"""Versioned project candidates; these are not the undisclosed official IDs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

CASE_IDS = frozenset(f"C{i:02d}" for i in range(1, 16))
VISIBILITY = frozenset(("visible", "partial", "occluded", "unknown"))

def validate_taxonomy(document: dict, *, previous: dict | None = None) -> None:
    if document.get("schema_version") != "1.0" or document.get("kind") not in ("objects", "actions"):
        raise ValueError("unsupported taxonomy schema/kind")
    if not isinstance(document.get("version"), str) or not document["version"].strip():
        raise ValueError("taxonomy needs an explicit version")
    if document.get("authority") != "project_candidates" or document.get("official_class_ids") is not None:
        raise ValueError("do not claim undisclosed official class IDs")
    status = document.get("status")
    if status not in ("draft", "reviewed"):
        raise ValueError("unsupported review state")
    if status == "draft" and document.get("production_ready") is not False:
        raise ValueError("draft cannot be production ready")
    if status == "reviewed" and (not isinstance(document.get("reviewer"), str) or not document["reviewer"].strip()):
        raise ValueError("reviewed taxonomy requires an identified human reviewer")
    classes = document.get("classes")
    states = document.get("states")
    if not isinstance(classes, list) or not classes or not isinstance(states, list):
        raise ValueError("classes must be nonempty; states must be an explicit list")
    all_ids = set()
    for is_state, rows in ((False, classes), (True, states)):
        prefix = "state" if is_state else ("object" if document["kind"] == "objects" else "action")
        for row in rows:
            key = row.get("id")
            if not isinstance(key, str) or not re.fullmatch(prefix+r"\.[a-z][a-z0-9_]*", key) or key in all_ids:
                raise ValueError("invalid or duplicate candidate ID")
            all_ids.add(key)
            if not isinstance(row.get("label"), str) or not row["label"].strip():
                raise ValueError("missing label")
            for field in ("includes", "excludes", "hard_negatives", "unobservable", "case_refs"):
                values = row.get(field)
                if not isinstance(values, list) or not values or any(not isinstance(v,str) or not v.strip() for v in values):
                    raise ValueError(f"{key}: missing {field}")
            if not set(row["case_refs"]) <= CASE_IDS:
                raise ValueError("unknown case route")
            if set(row.get("visibility_policy", {})) != VISIBILITY:
                raise ValueError("visibility/unknown policy is required")
            limit = row.get("small_object_limit")
            if (not isinstance(limit,dict) or not limit.get("unknown_when")
                    or limit.get("verified_min_pixels") is not None):
                raise ValueError("unmeasured pixel thresholds cannot be claimed verified")
            if not row.get("truncation_policy") or row.get("human_review_required") is not True:
                raise ValueError("truncation and human review policy required")
    if previous is not None:
        if previous["kind"] != document["kind"]:
            raise ValueError("taxonomy kind changed")
        for field in ("classes", "states"):
            old, new = previous[field], document[field]
            if [c["id"] for c in new[:len(old)]] != [c["id"] for c in old]:
                raise ValueError("IDs are append-only and ordered")
            for before, after in zip(old, new):
                if (before["label"], before["includes"]) != (after["label"], after["includes"]):
                    raise ValueError("existing ID meaning cannot be repurposed")
        if document != previous and document["version"] == previous["version"]:
            raise ValueError("changed taxonomy needs a new version")

def load_taxonomy(path: Path, *, previous: dict | None = None) -> dict:
    if path.stat().st_size > 1024**2:
        raise ValueError("taxonomy exceeds 1 MiB")
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_taxonomy(document, previous=previous)
    return document

def class_ids(document: dict, *, include_states: bool = False) -> tuple[str, ...]:
    validate_taxonomy(document)
    rows = document["classes"] + (document["states"] if include_states else [])
    return tuple(row["id"] for row in rows)

def annotation_decision(observed: bool | None, *, visibility: str, reviewed: bool,
                        interval_complete: bool) -> tuple[str, bool]:
    """Explicit negatives need reviewed, complete, visible relevant coverage."""
    if visibility not in VISIBILITY:
        raise ValueError("unknown visibility enum")
    if not reviewed:
        return "unreviewed", False
    if observed is True and visibility in ("visible", "partial"):
        return "present", True
    if observed is False and visibility == "visible" and interval_complete:
        return "absent_verified", True
    return "unknown", False

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path",type=Path)
    parser.add_argument("--previous",type=Path)
    args = parser.parse_args(argv)
    try:
        previous = load_taxonomy(args.previous) if args.previous else None
        result = load_taxonomy(args.path,previous=previous)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({"version":result["version"],"status":result["status"],
                      "classes":len(result["classes"]),"states":len(result["states"]),
                      "official_ids":"not supplied"},ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
