"""Frozen-encoder, masked AdamW training. Automatic runs are tiny CPU smoke only."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import platform

import torch
import torchvision

from ml.cache import CacheSpec, encoder_fingerprint, load_cache
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import artifact_transaction
from ml.models import FrozenEncoder, ModelConfig, VideoActionModel
from ml.models.encoder import file_sha256, safe_torch_load


@dataclass(frozen=True)
class TrainConfig:
    version: str = "masked-adamw-v1"
    seed: int = 42
    learning_rate: float = 0.001
    weight_decay: float = 0.01
    grad_clip: float = 1.0
    device: str = "cpu"
    cpu_threads: int = 1

    def __post_init__(self):
        if (self.version != "masked-adamw-v1" or type(self.seed) is not int or not 0 <= self.seed < 2**32
                or type(self.cpu_threads) is not int or not 1 <= self.cpu_threads <= 16
                or self.device not in ("cpu", "cuda")):
            raise ValueError("unsupported training config")
        for field in ("learning_rate", "weight_decay", "grad_clip"):
            value = getattr(self, field)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid optimizer hyperparameter")
        if not 0 < self.learning_rate <= 0.1 or not 0 < self.grad_clip <= 100 or self.weight_decay > 1:
            raise ValueError("optimizer hyperparameter outside supported bounds")

    def descriptor(self):
        return asdict(self)


def masked_bce(logits, targets, known_mask, image_mask, padding_mask):
    if (logits.ndim != 3 or targets.shape != logits.shape or known_mask.shape != logits.shape
            or image_mask.shape != logits.shape[:2] or padding_mask.shape != image_mask.shape
            or logits.dtype != torch.float32 or targets.dtype != torch.float32):
        raise ValueError("loss tensor shapes/dtypes")
    for mask in (known_mask, image_mask, padding_mask):
        if mask.dtype != torch.bool or mask.device != logits.device:
            raise ValueError("loss masks require boolean tensors on the same device")
    if targets.device != logits.device or (image_mask & padding_mask).any():
        raise ValueError("loss device/image/padding mismatch")
    valid = known_mask & image_mask[..., None] & ~padding_mask[..., None]
    if not valid.any():
        return None
    selected_logits, selected_targets = logits[valid], targets[valid]
    if (not bool(torch.isfinite(selected_logits).all() & torch.isfinite(selected_targets).all())
            or not bool(((selected_targets == 0) | (selected_targets == 1)).all())):
        raise ValueError("invalid supervised logit/target")
    # Selection happens before BCE, so an unknown NaN cannot contaminate a known loss.
    return torch.nn.functional.binary_cross_entropy_with_logits(selected_logits, selected_targets)


def runtime_info():
    return {"python": platform.python_version(), "torch": str(torch.__version__),
            "torchvision": str(torchvision.__version__), "cuda": torch.version.cuda,
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0}


def _gate(spec, cache, config, steps, smoke, allow_real_training, readiness):
    if spec.partition != "train":
        raise ValueError("only train partition may update weights")
    if type(steps) is not int or not 1 <= steps <= 1000000:
        raise ValueError("invalid total optimizer step budget")
    if smoke:
        if (not spec.test_only or config.device != "cpu" or steps > 4 or len(cache["arrays"]) > 4
                or len(spec.class_ids) > 8 or any(len(w["samples"]) > 32 for w in cache["windows"])):
            raise ValueError("smoke requires tiny test-only CPU data, <=4 steps/windows, <=8 classes, T<=32")
    elif (not allow_real_training or spec.test_only or not isinstance(readiness, dict)
          or readiness.get("data_ready") is not True
          or readiness.get("dataset_revision") != spec.dataset_sha256):
        raise ValueError("future training requires explicit instruction, real reviewed readiness and matching revision")
    if config.device == "cuda" and not torch.cuda.is_available():
        raise ValueError("requested CUDA runtime is unavailable")


def train(cache_dir: Path, destination: Path, *, spec: CacheSpec, encoder: FrozenEncoder,
          config: TrainConfig = TrainConfig(), steps: int = 2, resume: Path | None = None,
          smoke: bool = True, allow_real_training: bool = False, readiness: dict | None = None):
    cache = load_cache(cache_dir, spec)
    _gate(spec, cache, config, steps, smoke, allow_real_training, readiness)
    if not isinstance(encoder, FrozenEncoder) or encoder.descriptor() != cache["encoder"]:
        raise ValueError("training requires the exact frozen MobileNet encoder of this cache")
    architecture = ModelConfig(len(spec.class_ids))
    runtime = runtime_info()
    signature = {"config": config.descriptor(), "architecture": architecture.descriptor(),
                 "cache_key": spec.key(), "class_ids": list(spec.class_ids), "encoder": cache["encoder"],
                 "preprocessing": cache["preprocessing"], "runtime": runtime, "smoke": smoke,
                 "training_spec": spec.descriptor()}
    signature_sha = stable_hash(signature)
    previous = None if resume is None else safe_torch_load(resume)
    resume_sha = None if resume is None else file_sha256(resume)
    if previous is not None:
        if (set(previous) != {"checkpoint_version", "signature", "signature_sha256", "model", "optimizer",
                             "completed_steps", "losses", "sampler_state", "order", "cursor", "torch_rng", "cuda_rng"}
                or previous["checkpoint_version"] != "training-checkpoint-v1"
                or previous["signature"] != signature or previous["signature_sha256"] != signature_sha
                or type(previous["completed_steps"]) is not int or not 0 <= previous["completed_steps"] <= steps
                or len(previous["losses"]) != previous["completed_steps"]):
            raise ValueError("resume checkpoint/cache/config/runtime/classes mismatch")
    key = stable_hash({"signature": signature_sha, "total_steps": steps, "resume_sha256": resume_sha})

    def build(staging, register):
        old_threads = torch.get_num_threads()
        old_deterministic = torch.are_deterministic_algorithms_enabled()
        old_warn_only = torch.is_deterministic_algorithms_warn_only_enabled()
        devices = [] if config.device == "cpu" else [torch.cuda.current_device()]
        try:
            torch.set_num_threads(config.cpu_threads)
            torch.use_deterministic_algorithms(True)
            with torch.random.fork_rng(devices=devices):
                torch.manual_seed(config.seed)
                model = VideoActionModel(encoder, architecture).to(config.device)
                optimizer = torch.optim.AdamW(model.temporal.parameters(), lr=config.learning_rate,
                                              weight_decay=config.weight_decay)
                optimizer_options = {k: v for k, v in optimizer.param_groups[0].items() if k != "params"}
                generator = torch.Generator(device="cpu").manual_seed(config.seed)
                order, cursor, completed, losses = [], 0, 0, []
                if previous is not None:
                    model.load_state_dict(previous["model"], strict=True)
                    if encoder_fingerprint(model.encoder) != cache["encoder"]["state_sha256"]:
                        raise ValueError("resume changed frozen encoder")
                    optimizer.load_state_dict(previous["optimizer"])
                    if (len(optimizer.param_groups) != 1 or optimizer_options !=
                            {k: v for k, v in optimizer.param_groups[0].items() if k != "params"}):
                        raise ValueError("resume optimizer mismatch")
                    generator.set_state(previous["sampler_state"])
                    torch.set_rng_state(previous["torch_rng"])
                    if devices:
                        torch.cuda.set_rng_state_all(previous["cuda_rng"])
                    order, cursor = previous["order"], previous["cursor"]
                    if (sorted(order) != list(range(len(cache["arrays"])))
                            or type(cursor) is not int or not 0 <= cursor <= len(order)):
                        raise ValueError("resume sampler order/cursor mismatch")
                    completed, losses = previous["completed_steps"], list(previous["losses"])
                model.train()
                skipped, attempts = 0, 0
                eligible = sum(bool(row["known_mask"].any()) for row in cache["arrays"])
                while completed < steps and eligible:
                    if cursor >= len(order):
                        order = torch.randperm(len(cache["arrays"]), generator=generator).tolist()
                        cursor = 0
                    item = cache["arrays"][order[cursor]]
                    cursor += 1
                    attempts += 1
                    if attempts > (steps + 1) * (len(cache["arrays"]) + 1):
                        raise ValueError("training sampler attempt budget")
                    tensors = {k: torch.from_numpy(v).to(config.device)[None] for k, v in item.items()}
                    optimizer.zero_grad(set_to_none=True)
                    logits, _ = model.temporal(tensors["features"], image_mask=tensors["image_mask"])
                    loss = masked_bce(logits, tensors["targets"], tensors["known_mask"],
                                      tensors["image_mask"], tensors["padding_mask"])
                    if loss is None:
                        skipped += 1
                        continue
                    loss.backward()
                    gradients = [p.grad for p in model.temporal.parameters()]
                    if any(g is None or not bool(torch.isfinite(g).all()) for g in gradients):
                        raise ValueError("missing/non-finite temporal gradient")
                    torch.nn.utils.clip_grad_norm_(model.temporal.parameters(), config.grad_clip, error_if_nonfinite=True)
                    optimizer.step()
                    if any(not bool(torch.isfinite(p).all()) for p in model.temporal.parameters()):
                        raise ValueError("non-finite temporal parameter")
                    losses.append(float(loss.detach().cpu()))
                    completed += 1
                if not order:
                    order = list(range(len(cache["arrays"])))
                if encoder_fingerprint(model.encoder) != cache["encoder"]["state_sha256"]:
                    raise ValueError("frozen encoder mutated")
                checkpoint = {"checkpoint_version": "training-checkpoint-v1", "signature": signature,
                              "signature_sha256": signature_sha,
                              "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
                              "optimizer": optimizer.state_dict(), "completed_steps": completed, "losses": losses,
                              "sampler_state": generator.get_state(), "order": order, "cursor": cursor,
                              "torch_rng": torch.get_rng_state(),
                              "cuda_rng": torch.cuda.get_rng_state_all() if devices else []}
                torch.save(checkpoint, staging / "checkpoint.pt")
                register("checkpoint.pt")
                report = {"kind": "training-smoke" if smoke else "training-run", "signature": signature,
                          "signature_sha256": signature_sha, "requested_total_steps": steps,
                          "completed_steps": completed, "losses": losses, "resumed": resume is not None,
                          "skipped_windows_this_run": skipped, "all_unknown": eligible == 0,
                          "frozen_encoder_unchanged": True, "test_only": spec.test_only,
                          "trained": False, "validated": False, "production_ready": False,
                          "reason": "Optimizer smoke is not a trained/validated production release." if smoke
                          else "Training completion requires independent evaluation and explicit release validation."}
                register("training_report.json", json.dumps(report, indent=2, allow_nan=False).encode() + b"\n")
                return report
        finally:
            torch.set_num_threads(old_threads)
            torch.use_deterministic_algorithms(old_deterministic, warn_only=old_warn_only)
    return artifact_transaction(destination, key, build, max_bytes=96 * 1024**2, min_free_bytes=128 * 1024**2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="TrainConfig JSON; total step budget is separate")
    parser.add_argument("--steps", type=int, default=2, help="total optimizer steps, including resumed steps")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--allow-real-training", action="store_true")
    parser.add_argument("--readiness", type=Path)
    parser.add_argument("--encoder-weights", type=Path)
    parser.add_argument("--encoder-sha256")
    args = parser.parse_args(argv)
    try:
        spec = CacheSpec.from_dict(read_json(args.cache / "cache.json")["spec"])
        metadata = read_json(args.cache / "cache.json")["encoder"]
        config = TrainConfig(**({} if args.config is None else read_json(args.config)))
        encoder = FrozenEncoder(test_only=spec.test_only, seed=metadata.get("seed", 42),
                                weights_path=args.encoder_weights, weights_sha256=args.encoder_sha256)
        result = train(args.cache, args.output_dir, spec=spec, encoder=encoder, config=config,
                       steps=args.steps, resume=args.resume, smoke=args.smoke,
                       allow_real_training=args.allow_real_training,
                       readiness=None if args.readiness is None else read_json(args.readiness))
        print(json.dumps(result["data"], indent=2))
        return 0
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
        parser.exit(1, f"train refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
