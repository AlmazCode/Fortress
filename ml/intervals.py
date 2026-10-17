"""Source-time intervals with explicit unknown coverage; scores do not infer visibility."""
from __future__ import annotations

import math

from contracts.python_ports import validate_contract


def timeline_from_scores(points, scenes, *, video_id, class_ids, thresholds, model_version,
                         preprocessing_version, visibility_provider=None, step_sec=.5, max_observations=100000):
    if (not 0 < step_sec <= 1 or not math.isfinite(step_sec) or not class_ids
            or len(class_ids) != len(set(class_ids)) or set(class_ids) != set(thresholds)):
        raise ValueError("invalid interval classes/step/thresholds")
    scene_map = {s["scene_id"]: s for s in scenes["scenes"]}
    grouped = {key: [] for key in scene_map}
    seen = set()
    for point in points:
        timestamp = point["time"]["timestamp_sec"]
        key = (point["scene_id"], timestamp)
        if (point["video_id"] != video_id or key in seen or point["scene_id"] not in grouped
                or len(point["scores"]) != len(class_ids) or not point["time"]["valid"]):
            raise ValueError("invalid/duplicate source score point")
        scene = scene_map[point["scene_id"]]
        if not scene["start_sec"] <= timestamp < scene["end_sec"]:
            raise ValueError("score point crosses scene bounds")
        seen.add(key)
        grouped[point["scene_id"]].append(point)
    observations = []

    def append(class_id, scene_id, start, end, score=None, state="unknown", visibility="unknown"):
        if end <= start + 1e-9:
            return
        row = {"class_id": class_id, "interval": {"start_sec": start, "end_sec": end, "scene_id": scene_id},
               "score": score, "state": state, "known_mask": state in ("present", "absent_verified"),
               "visibility": visibility, "actor_id": None,
               "relations": [{"kind": "action_participants", "subject_id": None, "object_id": None, "known": False}]}
        if observations:
            previous = observations[-1]
            if (all(previous[k] == row[k] for k in ("class_id", "state", "known_mask", "visibility", "score"))
                    and previous["interval"]["scene_id"] == scene_id
                    and math.isclose(previous["interval"]["end_sec"], start, abs_tol=1e-9)):
                previous["interval"]["end_sec"] = end
                return
        observations.append(row)
        if len(observations) > max_observations:
            raise ValueError("timeline observation budget")

    for scene_id, scene in scene_map.items():
        ordered = sorted(grouped[scene_id], key=lambda p: p["time"]["timestamp_sec"])
        for column, class_id in enumerate(class_ids):
            cursor = scene["start_sec"]
            for n, point in enumerate(ordered):
                start = point["time"]["timestamp_sec"]
                append(class_id, scene_id, cursor, start)
                end = min(start + step_sec, scene["end_sec"],
                          ordered[n + 1]["time"]["timestamp_sec"] if n + 1 < len(ordered) else scene["end_sec"])
                score, threshold = point["scores"][column], thresholds[class_id]
                if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1):
                    raise ValueError("invalid interval score")
                context = None if visibility_provider is None else visibility_provider(point, class_id)
                visibility = "unknown" if context is None else context["visibility"]
                complete = False if context is None else context["interval_complete"]
                if visibility not in ("visible", "partial", "occluded", "unknown") or type(complete) is not bool:
                    raise ValueError("invalid independent observability context")
                state = "unknown"
                if score is not None and threshold is not None and visibility in ("visible", "partial"):
                    if score >= threshold:
                        state = "present"
                    elif visibility == "visible" and complete:
                        state = "absent_verified"
                append(class_id, scene_id, start, end, score=score, state=state, visibility=visibility)
                cursor = end
            append(class_id, scene_id, cursor, scene["end_sec"])
    known = sum(row["known_mask"] for row in observations)
    timeline = {"schema_version": "1.0", "video_id": video_id, "scene_id": video_id + ":all-scenes",
                "preprocessing_version": preprocessing_version, "model_version": model_version,
                "coverage": "none" if not known else ("full" if known == len(observations) else "partial"),
                "observations": observations, "findings": []}
    validate_contract("events", timeline)
    return timeline
