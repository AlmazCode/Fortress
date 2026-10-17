"""Read-only material inventory and CPU/runtime preflight.

Reports describe observed files and software. An inventory or synthetic shape
check never establishes annotation quality, production readiness or ML accuracy.
"""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any

VIDEO_SUFFIXES = {".mov", ".mp4", ".mkv", ".avi"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ANNOTATION_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv", ".xml"}
SKIP_DIRS = {".git", ".venv", ".aster", "__pycache__", ".pytest_cache"}
REQUIRED_CONTRACTS = ("manifest", "annotations", "objects", "dataset_readiness", "events", "release")

def sha256_file(path: Path, *, max_bytes: int = 1024**3) -> str:
    """Bounded hashing; refuse a source that changes while being read."""
    before = path.stat()
    if before.st_size > max_bytes:
        raise ValueError("file exceeds hash byte limit")
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024**2), b""):
            count += len(block)
            if count > max_bytes:
                raise ValueError("file exceeds hash byte limit")
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, count) != (after.st_size, after.st_mtime_ns, after.st_size):
        raise ValueError("source changed during hashing")
    return digest.hexdigest()

def material_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in {".pt", ".pth", ".safetensors", ".onnx"}:
        return "model_weight"
    if suffix in ANNOTATION_SUFFIXES:
        return "annotation_or_metadata"
    return "document_or_other"

def inspect_file(path: Path, *, role: str, source: str, rights: str = "unknown",
                 max_bytes: int = 1024**3) -> dict[str, Any]:
    record: dict[str, Any] = {
        "role": role, "source": source, "path": str(path.absolute()),
        "kind": material_kind(path), "rights": rights, "state": "missing",
        "size_bytes": None, "sha256": None,
        "content_validation": "not_run", "review_status": "unverified",
    }
    try:
        if path.is_symlink():
            record.update(state="unsupported", reason="symlink not followed")
        elif path.is_file():
            record["size_bytes"] = path.stat().st_size
            record["sha256"] = sha256_file(path, max_bytes=max_bytes)
            record["state"] = "available"
        elif path.exists():
            record.update(state="unsupported", reason="not a regular file")
    except (OSError, ValueError) as exc:
        record.update(state="unreadable_or_unstable", reason=str(exc))
    return record

def scan_root(directory: Path, *, role: str, rights: str = "unknown",
              max_files: int = 20000, max_bytes: int = 5*1024**3) -> dict:
    root = directory.absolute()
    result: dict[str, Any] = {"root": str(root), "role": role, "files": [], "issues": [],
                              "skipped_directories": []}
    if not root.is_dir() or root.is_symlink():
        result["issues"].append("root_missing_or_symlink")
        return result
    total = 0
    for parent, dirs, names in os.walk(root, followlinks=False):
        linked = [d for d in dirs if (Path(parent)/d).is_symlink()]
        if linked:
            result["issues"].append("directory_symlink_not_followed")
        skipped = [d for d in dirs if d in SKIP_DIRS or d.startswith(".") or d in linked]
        result["skipped_directories"].extend(str((Path(parent)/d).relative_to(root)) for d in sorted(skipped))
        dirs[:] = sorted(d for d in dirs if d not in skipped)
        for name in sorted(names):
            if len(result["files"]) >= max_files:
                result["issues"].append("file_count_limit")
                return result
            path = Path(parent)/name
            try:
                size = path.lstat().st_size
            except OSError:
                size = 0
            if total + size > max_bytes:
                result["issues"].append("total_hash_byte_limit")
                return result
            result["files"].append(inspect_file(path, role=role, source="local configured root",
                                                rights=rights, max_bytes=max_bytes-total))
            total += size
    result["hashed_bytes_budget_used"] = total
    return result

def material_inventory(project_root: Path, *, data_roots: tuple[Path, ...] = (),
                       annotation_roots: tuple[Path, ...] = (), case: Path | None = None,
                       release_root: Path | None = None, rights: str = "unknown") -> dict:
    project = project_root.resolve()
    required = [
        ("original_technical_spec", project/"TECHNICAL_SPEC.md"),
        ("active_product_requirements", project/"docs/github-plan/REQUIREMENTS.md"),
        ("training_appendix", project/"DATA_AND_TRAINING.md"),
        ("case_coverage_appendix", project/"CASE_COVERAGE.md"),
        ("original_case", case or project/"Кейс_ForteBank.docx"),
        ("taxonomy", project/"contracts/taxonomy.draft.json"),
        ("dependency_manifest", project/"pyproject.toml"),
        ("dependency_lock", project/"uv.lock"),
    ]
    required += [("contract", project/f"contracts/{name}.schema.json") for name in REQUIRED_CONTRACTS]
    materials = [inspect_file(path, role=role, source="project or explicitly configured source")
                 for role, path in required]
    roots = [scan_root(path, role="source_media", rights=rights) for path in data_roots]
    roots += [scan_root(path, role="annotation_assets", rights=rights) for path in annotation_roots]
    if release_root is not None:
        roots.append(scan_root(release_root, role="release_candidate", rights=rights))
    counts: Counter = Counter()
    for result in roots:
        for entry in result["files"]:
            if entry["state"] == "available":
                counts[entry["kind"]] += 1
    draft = None
    taxonomy = project/"contracts/taxonomy.draft.json"
    if taxonomy.is_file():
        try:
            draft = json.loads(taxonomy.read_text(encoding="utf-8")).get("status")
        except (ValueError, OSError):
            draft = "invalid_or_unreadable"
    return {
        "scope": "D1 inventory only; media decode, labels and split not validated",
        "materials": materials, "roots": roots, "counts": dict(counts),
        "taxonomy_status": draft,
        "limitations": [
            "annotation_or_metadata counts include templates and metadata; no human review inferred",
            "unordered images do not establish temporal GRU training sequences",
            "raw model weights do not establish a validated production release",
            "actual media decode, labels, grouped split and rights require separate validation",
            "hidden/tooling directories are excluded and listed in skipped_directories; configure an explicit root to inventory one",
        ],
    }

def memory_info() -> dict:
    result = {"total_ram_bytes": None, "available_ram_bytes": None}
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ("total", "available", "total_page", "available_page", "total_virtual", "available_virtual", "extended")]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            result.update(total_ram_bytes=status.total, available_ram_bytes=status.available)
    elif Path("/proc/meminfo").is_file():
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])*1024
        result.update(total_ram_bytes=values.get("MemTotal"), available_ram_bytes=values.get("MemAvailable"))
    else:
        try:
            result["total_ram_bytes"] = os.sysconf("SC_PAGE_SIZE")*os.sysconf("SC_PHYS_PAGES")
            result["available_ram_bytes"] = os.sysconf("SC_PAGE_SIZE")*os.sysconf("SC_AVPHYS_PAGES")
        except (OSError, ValueError, AttributeError):
            pass
    return result

def runtime_info() -> dict:
    packages = {}
    for name in ("torch", "torchvision", "numpy", "av", "Pillow"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    result: dict[str, Any] = {
        "python": platform.python_version(), "python_3_11": sys.version_info[:2] == (3, 11),
        "platform": platform.system(), "machine": platform.machine(),
        "packages": packages, "memory": memory_info(),
        "cuda": {"available": False, "build_version": None, "devices": [], "reason": "unverified"},
    }
    try:
        torch = importlib.import_module("torch")
        available = torch.cuda.is_available()
        result["cuda"].update(available=available, build_version=torch.version.cuda,
                              reason=None if available else "CUDA not available to this installed torch build")
        if available:
            for i in range(torch.cuda.device_count()):
                device = torch.cuda.get_device_properties(i)
                free, total = torch.cuda.mem_get_info(i)
                result["cuda"]["devices"].append({"index": i, "name": device.name,
                    "total_vram_bytes": total, "available_vram_bytes": free,
                    "capability": list(torch.cuda.get_device_capability(i))})
    except Exception as exc:
        result["cuda"]["reason"] = f"torch runtime unavailable: {type(exc).__name__}"
    return result

def cpu_self_test() -> dict:
    """Random-init features only, never a production recognizer or download."""
    try:
        torch = importlib.import_module("torch")
        vision = importlib.import_module("torchvision")
        old_threads = torch.get_num_threads()
        try:
            torch.set_num_threads(min(2, old_threads))
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(42)
                with torch.inference_mode():
                    encoder = vision.models.mobilenet_v3_small(weights=None).features.eval()
                    output = encoder(torch.zeros(1, 3, 224, 224)).mean(dim=(-2, -1))
                    if tuple(output.shape) != (1, 576) or not bool(torch.isfinite(output).all()):
                        raise ValueError("MobileNetV3-Small feature shape/finite assertion failed")
            return {"status": "passed", "device": "cpu", "input_shape": [1, 3, 224, 224],
                    "feature_shape": [1, 576], "weights": "None", "test_only": True,
                    "meaning": "software shape check; not training, production weights or ML quality"}
        finally:
            torch.set_num_threads(old_threads)
    except Exception as exc:
        return {"status": "failed", "device": "cpu", "test_only": True,
                "error": f"{type(exc).__name__}: {exc}"}

def build_report(project_root: Path, *, self_test: bool = False, **inventory_options) -> dict:
    inventory = material_inventory(project_root, **inventory_options)
    runtime = runtime_info()
    smoke = cpu_self_test() if self_test else {"status": "not_run", "test_only": True}
    counts = inventory["counts"]
    missing = [r["role"] for r in inventory["materials"] if r["state"] != "available"]
    reasons = ["annotation_validation_not_run", "grouped_split_validation_not_run",
               "production_release_not_validated", "target_training_pc_not_verified"]
    if not counts.get("video"):
        reasons.append("data_missing")
    annotation_files_present = bool(counts.get("annotation_or_metadata"))
    if not annotation_files_present:
        reasons.append("annotation_missing")
    rights = inventory_options.get("rights", "unknown")
    if rights == "unknown":
        reasons.append("license_unknown")
    elif rights == "restricted":
        reasons.append("license_restricted")
    return {
        "schema_version": "preflight-1", "inventory": inventory, "runtime": runtime, "self_test": smoke,
        "readiness": {
            "scope": "D1 preflight tools only",
            "tools_ready": smoke["status"] == "passed" and runtime["python_3_11"] and "contract" not in missing,
            "data_missing": not bool(counts.get("video")),
            "annotation_files_present": annotation_files_present,
            "annotation_missing": None if annotation_files_present else True,
            "annotation_review": "unverified", "hardware_unverified": True,
            "license_state": rights,
            "license_unknown": "license_unknown" in reasons,
            "training_ready": False, "reasons": reasons,
        },
    }

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, action="append", default=[])
    parser.add_argument("--annotation-root", type=Path, action="append", default=[])
    parser.add_argument("--case", type=Path)
    parser.add_argument("--release-root", type=Path)
    parser.add_argument("--rights", choices=["unknown", "confirmed", "restricted"], default="unknown",
                        help="user-declared rights; does not validate labels or authorize training")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path, help="new local JSON report, outside tracked code")
    args = parser.parse_args(argv)
    report = build_report(args.project_root, self_test=args.self_test,
        data_roots=tuple(args.data_root), annotation_roots=tuple(args.annotation_root),
        case=args.case, release_root=args.release_root, rights=args.rights)
    body = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(body)
    else:
        print(body, end="")
    return 1 if args.self_test and report["self_test"]["status"] != "passed" else 0

if __name__ == "__main__":
    raise SystemExit(main())
