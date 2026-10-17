"""Fortress local data/ML commands. Full training requires a separate explicit instruction."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import time


def cache_dataset(destination, *, source_root, manifest, source_audit, pairs, contexts, objects, actions,
                  object_taxonomy, action_taxonomy, asset_root, partition, classes=None,
                  test_only=False, encoder_weights=None, encoder_sha256=None, seed=42, readiness_evidence=None):
    from ml.cache import CacheSpec, build_cache, cache_configuration
    from ml.data.deduplicate import stable_hash
    from ml.data.pts_index import iter_indexed_frames, validate_index
    from ml.data.scenes import validate_scenes
    from ml.data.splits import validate_splits
    from ml.data.taxonomy import class_ids
    from ml.data_cli import data_report
    from ml.models import FrozenEncoder
    from ml.preprocessing import PreprocessConfig
    from ml.windows import labelled_windows
    validate_splits(manifest)
    available = class_ids(action_taxonomy, include_states=True)
    classes = tuple(available if classes is None else classes)
    if (not classes or len(set(classes)) != len(classes)
            or tuple(k for k in available if k in classes) != classes):
        raise ValueError("ordered taxonomy subset required")
    active = [r for r in manifest["videos"] if r["split"] != "excluded"]
    if test_only and any(r["provenance"]["kind"] != "synthetic" for r in active):
        raise ValueError("random test cache is restricted to explicit synthetic sources")
    report = data_report(manifest=manifest, source_audit=source_audit, objects=objects, actions=actions,
                         contexts=contexts, object_taxonomy=object_taxonomy, action_taxonomy=action_taxonomy,
                         asset_root=asset_root, source_root=source_root, readiness_evidence=readiness_evidence)
    if not report["validation_passed"]:
        raise ValueError("data QA failed: " + "; ".join(report["qa"]["errors"]))
    selected = {r["video_id"]: r for r in manifest["videos"] if r["split"] == partition}
    if not selected or {p["index"]["video_id"] for p in pairs} != set(selected) or len(pairs) != len(selected):
        raise ValueError("one index/scenes pair for every source in the selected partition required")
    windows = []
    filtered = {**actions, "records": [r for r in actions["records"] if r["event_type"] in classes]}
    for pair in pairs:
        index, scenes = pair["index"], pair["scenes"]
        row = selected[index["video_id"]]
        validate_index(index)
        validate_scenes(index, scenes)
        if (index["source_sha256"] != row["sha256"] or index["split"] != partition
                or index["dataset_version"] != manifest["dataset_version"] or index["split_version"] != manifest["split_version"]):
            raise ValueError("index does not match current manifest/version/split")
        for scene in scenes["scenes"]:
            context = contexts[scene["scene_id"]]
            if (context["index_sha256"] != index["index_sha256"] or context["start_sec"] != scene["start_sec"]
                    or context["end_sec"] != scene["end_sec"]):
                raise ValueError("annotation context/cuts differ from extracted source index")
        windows.extend(labelled_windows(index, scenes, filtered, list(classes)))
    encoder = FrozenEncoder(test_only=test_only, seed=seed, weights_path=encoder_weights, weights_sha256=encoder_sha256)
    metadata = encoder.descriptor()
    preprocessing = PreprocessConfig()
    inputs = {"dataset_sha256": stable_hash(manifest), "split_sha256": stable_hash(manifest["split_version"]),
              "annotation_sha256": stable_hash(actions), "taxonomy_sha256": stable_hash(action_taxonomy)}
    binding = {"version": "training-data-binding-v1", "inputs": inputs, "qa_revision": report["qa"]["dataset_revision"],
               "report": report}
    spec = CacheSpec(**inputs, source_sha256=stable_hash({w["video_id"]: w["source_sha256"] for w in windows}),
                     encoder_sha256=stable_hash(metadata), preprocessing_sha256=preprocessing.fingerprint(),
                     config_sha256=stable_hash(cache_configuration(classes, binding)), windows_sha256=stable_hash(windows),
                     class_ids=classes, partition=partition, test_only=test_only)
    def frames():
        for pair in pairs:
            index, scenes = pair["index"], pair["scenes"]
            for row, frame in iter_indexed_frames(source_root, index):
                scene = next(s for s in scenes["scenes"] if s["start_ordinal"] <= row["ordinal"] < s["end_ordinal"])
                yield (index["video_id"], scene["scene_id"], index["split"], row["source_pts"]), frame.to_image(), index["rotation"]
    return build_cache(destination, source_root=source_root, spec=spec, windows=windows, frames=frames(),
                       encoder=encoder, encoder_metadata=metadata, readiness_binding=binding)


def cache_main(argv):
    from ml.data.annotation_tasks import read_json
    from ml.data.taxonomy import load_taxonomy
    from ml.data_cli import load_context, manifest_input
    parser = argparse.ArgumentParser(description="Build a PTS feature cache and recompute/bind current annotation QA")
    for field in ("manifest", "source-root", "tasks", "objects", "actions", "asset-root", "object-taxonomy", "action-taxonomy", "output-dir"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--index", type=Path, action="append", required=True)
    parser.add_argument("--scenes", type=Path, action="append", required=True)
    parser.add_argument("--partition", choices=["train", "dev_validation", "independent_test"], required=True)
    parser.add_argument("--class", dest="classes", action="append")
    parser.add_argument("--test-only", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--encoder-weights", type=Path)
    parser.add_argument("--encoder-sha256")
    parser.add_argument("--readiness-evidence", type=Path)
    args = parser.parse_args(argv)
    if len(args.index) != len(args.scenes):
        parser.error("--index/--scenes counts must match in the same order")
    manifest, audit = manifest_input(args.manifest)
    return cache_dataset(args.output_dir, source_root=args.source_root, manifest=manifest, source_audit=audit,
                         pairs=[{"index": read_json(i), "scenes": read_json(s)} for i, s in zip(args.index, args.scenes)],
                         contexts=load_context(args.tasks, manifest), objects=read_json(args.objects), actions=read_json(args.actions),
                         object_taxonomy=load_taxonomy(args.object_taxonomy), action_taxonomy=load_taxonomy(args.action_taxonomy),
                         asset_root=args.asset_root, partition=args.partition, classes=args.classes, test_only=args.test_only,
                         seed=args.seed, encoder_weights=args.encoder_weights, encoder_sha256=args.encoder_sha256,
                         readiness_evidence=None if args.readiness_evidence is None else read_json(args.readiness_evidence))


def release_main(command, argv):
    from ml.data.annotation_tasks import read_json
    from ml.evaluate import write_new_json
    from ml.inference import TimelineAdapter
    from ml.release import ReleaseManager, import_package
    parser = argparse.ArgumentParser(description=f"Local model {command}; test-only never enables production readiness")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--expected-taxonomy")
    parser.add_argument("--expected-rules")
    if command != "rollback":
        parser.add_argument("--package", required=True, type=Path)
        parser.add_argument("--manifest-sha256")
    if command == "import":
        parser.add_argument("--output-dir", required=True, type=Path)
    elif command in ("activate", "rollback"):
        parser.add_argument("--pointer", required=True, type=Path)
    elif command == "infer":
        parser.add_argument("--video", required=True, type=Path)
        parser.add_argument("--output", required=True, type=Path)
        parser.add_argument("--deadline-seconds", type=float, default=120.)
    args = parser.parse_args(argv)
    options = {"allow_test": args.allow_test, "expected_taxonomy": args.expected_taxonomy, "expected_rules": args.expected_rules}
    if command == "import":
        if not args.allow_test and args.manifest_sha256 is None:
            parser.error("production transfer requires a trusted --manifest-sha256")
        return import_package(args.package, args.output_dir, expected_manifest_sha256=args.manifest_sha256, **options)
    manager = ReleaseManager(**options)
    if command == "rollback":
        result = manager.restore_pointer(args.pointer, previous=True)
    else:
        result = manager.load(args.package, expected_manifest_sha256=args.manifest_sha256,
                              pointer=args.pointer if command == "activate" else None)
    if command == "infer":
        if not 0 < args.deadline_seconds <= 300:
            raise ValueError("deadline seconds must be in (0,300]")
        result = TimelineAdapter(manager, allow_test=args.allow_test).infer(args.video,
                      deadline_monotonic=time.monotonic() + args.deadline_seconds)
        write_new_json(args.output, result)
    return {"result": result, "readiness": manager.readiness()}


def smoke_pipeline(destination):
    """Three tiny generated sources, <=2 CPU optimizer steps. No real data or downloads."""
    from fractions import Fraction
    import av
    import numpy as np
    import torch
    from ml.cache import CacheSpec
    from ml.data.annotation_tasks import prepare_tasks, read_json
    from ml.data.deduplicate import stable_hash
    from ml.data.extract_frames import artifact_transaction, export_frames
    from ml.data.manifest import build_manifest
    from ml.data.pts_index import build_index
    from ml.data.scenes import define_scenes
    from ml.data.splits import assign_splits
    from ml.data.taxonomy import load_taxonomy
    from ml.evaluate import evaluate, score_cache
    from ml.export import export_package
    from ml.inference import TimelineAdapter
    from ml.models import FrozenEncoder
    from ml.release import ReleaseManager, import_package
    from ml.thresholds import calibrate
    from ml.train import train
    root = Path(__file__).resolve().parents[1]
    object_taxonomy = load_taxonomy(root / "ml/config/object_taxonomy.draft.json")
    action_taxonomy = load_taxonomy(root / "ml/config/action_taxonomy.draft.json")
    request = {"kind": "tiny-software-smoke-v1", "object_taxonomy": object_taxonomy, "action_taxonomy": action_taxonomy}
    def build(staging, register):
        previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        try:
            sources = staging / "sources"
            sources.mkdir()
            entries = []
            for video in range(3):
                name = f"synthetic-{video}.mkv"
                with av.open(str(sources / name), "w") as output:
                    stream = output.add_stream("ffv1", rate=2)
                    stream.width, stream.height, stream.pix_fmt = 32, 24, "yuv420p"
                    stream.time_base = stream.codec_context.time_base = Fraction(1, 2)
                    for n, pts in enumerate((4, 5, 7, 8)):
                        pixels = np.random.default_rng(video * 100 + n).integers(0, 256, (24, 32, 3), dtype=np.uint8)
                        frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                        frame.pts, frame.time_base = pts, Fraction(1, 2)
                        for packet in stream.encode(frame):
                            output.mux(packet)
                    for packet in stream.encode():
                        output.mux(packet)
                entries.append({"path": name, "source_id": name, "group_id": name, "kind": "synthetic", "rights": "confirmed"})
            bundle = build_manifest(sources, entries, dataset_version="synthetic-code-smoke-v1")
            split = assign_splits(bundle["manifest"], eligible_video_ids=[r["video_id"] for r in bundle["manifest"]["videos"]],
                                  seed=17, final_video_ids=[bundle["manifest"]["videos"][0]["video_id"]],
                                  near_candidates=bundle["duplicates"]["near_candidates"])
            manifest = split["manifest"]
            bundle.update(manifest=manifest, split_audit=split["audit"])
            pairs, directories = [], []
            for n, row in enumerate(manifest["videos"]):
                index = build_index(sources, row, dataset_version=manifest["dataset_version"], split_version=manifest["split_version"])
                scenes = define_scenes(index)
                pairs.append({"index": index, "scenes": scenes})
                directories.append(staging / f"frames-{n}")
                export_frames(sources, index, scenes, directories[-1])
            prepare_tasks(staging / "tasks", manifest=manifest, pairs=pairs, frame_directories=directories,
                          object_taxonomy=object_taxonomy, action_taxonomy=action_taxonomy, annotation_version="artificial-smoke-v1")
            contexts = read_json(staging / "tasks/tasks.json")["scene_context"]
            objects = read_json(staging / "tasks/objects.json")
            actions = read_json(staging / "tasks/actions.json")
            classes = [row["id"] for row in action_taxonomy["classes"][:2]]
            for scene_id, scene in contexts.items():
                for column, key in enumerate(classes):
                    for start, end, positive in ((0., 1., column == 0), (1., scene["end_sec"], column != 0)):
                        actions["records"].append({"annotation_id": f"artificial-{len(actions['records'])}",
                            "video_id": scene["video_id"], "scene_id": scene_id, "source_sha256": scene["source_sha256"],
                            "split": scene["split"], "event_type": key, "taxonomy_version": action_taxonomy["version"],
                            "start_sec": start, "end_sec": end, "state": "present" if positive else "absent_verified",
                            "known_mask": True, "visibility": "visible", "interval_complete": True, "actor_id": None,
                            "relations": [], "annotator": "artificial-code-fixture", "reviewer": "simulated-review-not-human-gold",
                            "review_status": "reviewed", "human_approved": True, "label_origin": "manual"})
            def save(name, document):
                (staging / name).write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            save("manifest.json", bundle)
            save("artificial-actions.json", actions)
            save("object-taxonomy.json", object_taxonomy)
            save("action-taxonomy.json", action_taxonomy)
            for n, pair in enumerate(pairs):
                save(f"index-{n}.json", pair["index"])
                save(f"scenes-{n}.json", pair["scenes"])
            specs = {}
            for partition in ("train", "dev_validation", "independent_test"):
                cache_dataset(staging / ("cache-" + partition), source_root=sources, manifest=manifest,
                              source_audit=bundle["audit"], pairs=[p for p in pairs if p["index"]["split"] == partition],
                              contexts=contexts, objects=objects, actions=actions, object_taxonomy=object_taxonomy,
                              action_taxonomy=action_taxonomy, asset_root=staging / "tasks", partition=partition,
                              classes=classes, test_only=True)
                specs[partition] = CacheSpec.from_dict(read_json(staging / ("cache-" + partition) / "cache.json")["spec"])
            train(staging / "cache-train", staging / "train-first", spec=specs["train"], encoder=FrozenEncoder(test_only=True), steps=1)
            train(staging / "cache-train", staging / "train-resumed", spec=specs["train"], encoder=FrozenEncoder(test_only=True), steps=2,
                  resume=staging / "train-first/checkpoint.pt")
            checkpoint = staging / "train-resumed/checkpoint.pt"
            dev = score_cache(staging / "cache-dev_validation", checkpoint, manifest)
            thresholds = calibrate(dev)
            final = score_cache(staging / "cache-independent_test", checkpoint, manifest)
            metrics = evaluate(final, thresholds)
            save("dev-scores.json", dev)
            save("final-scores.json", final)
            save("thresholds.json", thresholds)
            save("metrics.json", metrics)
            versions = {"dataset": manifest["dataset_version"], "split": manifest["split_version"],
                        "annotations": actions["annotation_version"], "rules": "unverified-no-production-rules"}
            metadata = {"release_version": "tiny-software-smoke-v1", "versions": versions}
            save("export-metadata.json", metadata)
            exported = export_package(checkpoint, staging / "exported", taxonomy=action_taxonomy, thresholds=thresholds,
                                      metrics=metrics, **metadata)
            import_package(staging / "exported", staging / "imported", allow_test=True)
            manager = ReleaseManager(allow_test=True)
            manager.load(staging / "imported")
            pair = pairs[0]
            timeline = TimelineAdapter(manager, allow_test=True).infer_indexed(sources, pair["index"], pair["scenes"],
                                                                            deadline_monotonic=time.monotonic() + 30)
            save("timeline.json", timeline)
            save("model-readiness.json", manager.readiness())
            binding = read_json(staging / "cache-train/cache.json")["readiness_binding"]
            save("DATA_READINESS.json", binding["report"])
            summary = {"kind": "tiny-software-smoke-v1", "test_only": True, "source_videos": 3,
                       "optimizer_total_steps": 2, "resumed": True, "trained": False, "validated": False,
                       "production_ready": False, "data_ready": binding["report"]["data_ready"],
                       "calibration_partition": thresholds["selected_on"], "evaluation_partition": final["split"],
                       "verdict_metrics": metrics["verdict_metrics"], "timeline_coverage": timeline["coverage"],
                       "budget": exported["data"]["budget"], "limitations": ["Generated pixels/artificial labels test code only.",
                       "No real dataset evaluation, pretrained download, full training, CUDA, legal verdict or production activation."]}
            save("summary.json", summary)
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    register(path.relative_to(staging).as_posix())
            return summary
        finally:
            torch.set_num_threads(previous_threads)
    return artifact_transaction(destination, stable_hash(request),
                                build, max_bytes=128 * 1024**2, min_free_bytes=256 * 1024**2)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    delegated = {"data": "ml.data_cli", "preflight": "ml.preflight", "train": "ml.train", "resume": "ml.train",
                 "evaluate": "ml.evaluate", "thresholds": "ml.thresholds", "export": "ml.export"}
    names = [*delegated, "cache", "import", "activate", "rollback", "infer", "smoke"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=names)
    if not arguments or arguments[0] in ("-h", "--help"):
        parser.print_help()
        return 0
    parsed = parser.parse_args(arguments[:1])
    command, remainder = parsed.command, arguments[1:]
    try:
        if command in delegated:
            if command == "resume" and "--resume" not in remainder and not any(v in remainder for v in ("-h", "--help")):
                parser.error("resume requires --resume <previous checkpoint.pt>")
            return importlib.import_module(delegated[command]).main(remainder)
        if command == "cache":
            result = cache_main(remainder)
        elif command == "smoke":
            smoke = argparse.ArgumentParser(description="Generate only tiny synthetic CPU code fixtures outside Git")
            smoke.add_argument("--output-dir", type=Path, required=True)
            result = smoke_pipeline(smoke.parse_args(remainder).output_dir)
        else:
            result = release_main(command, remainder)
        print(json.dumps(result.get("data", result), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
        parser.exit(1, f"{command} refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
