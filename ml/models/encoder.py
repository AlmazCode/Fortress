"""Local-only encoder construction and bounded tensor checkpoint reads."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
import zipfile

import torch
import torchvision

from ml.cache import encoder_fingerprint


def file_sha256(path: Path, *, max_bytes: int = 96 * 1024**2) -> str:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= max_bytes:
        raise ValueError("checkpoint must be a bounded regular local file")
    digest = hashlib.sha256()
    with path.open("rb") as incoming:
        for chunk in iter(lambda: incoming.read(1024**2), b""):
            digest.update(chunk)
            if incoming.tell() > max_bytes:
                raise ValueError("checkpoint grew beyond byte budget")
    return digest.hexdigest()


def safe_torch_load(path: Path, *, expected_sha256: str | None = None,
                    max_bytes: int = 96 * 1024**2):
    """No executable globals/legacy pickle fallback. Limits reduce, not eliminate, DoS."""
    path = Path(path)
    before = file_sha256(path, max_bytes=max_bytes)
    if expected_sha256 is not None and (re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None
                                         or before != expected_sha256):
        raise ValueError("checkpoint SHA-256 mismatch")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > 4096 or sum(i.file_size for i in infos) > max_bytes:
                raise ValueError("checkpoint archive structure/byte budget")
            names = [i.filename for i in infos]
            roots = {name.split("/")[0] for name in names}
            if len(roots) != 1 or len(names) != len(set(names)):
                raise ValueError("checkpoint archive roots/duplicate entries")
            for info in infos:
                if (info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1
                        or "\\" in info.filename or ":" in info.filename
                        or any(p in ("", ".", "..") for p in info.filename.split("/"))):
                    raise ValueError("unsupported checkpoint archive entry")
                if info.filename.endswith("/data.pkl") and info.file_size > 2 * 1024**2:
                    raise ValueError("checkpoint metadata byte budget")
            if sum(n.endswith("/data.pkl") for n in names) != 1:
                raise ValueError("missing checkpoint metadata")
        value = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    except (ValueError, OSError):
        raise
    except Exception as error:
        raise ValueError("unsupported tensor checkpoint") from error
    count = 0
    tensor_bytes = 0

    def inspect(item, depth=0):
        nonlocal count, tensor_bytes
        count += 1
        if count > 20000 or depth > 16:
            raise ValueError("checkpoint tree budget")
        if isinstance(item, torch.Tensor):
            if (type(item) is not torch.Tensor or item.layout != torch.strided
                    or item.dtype not in (torch.float32, torch.int64, torch.int32, torch.uint8, torch.bool)
                    or item.ndim > 6 or item.numel() > 16 * 1024**2):
                raise ValueError("unsupported checkpoint tensor")
            tensor_bytes += item.numel() * item.element_size()
            if tensor_bytes > max_bytes or (item.is_floating_point() and not bool(torch.isfinite(item).all())):
                raise ValueError("checkpoint non-finite tensors/byte budget")
        elif isinstance(item, dict):
            if len(item) > 4096:
                raise ValueError("checkpoint mapping budget")
            for key, child in item.items():
                if type(key) not in (str, int) or (isinstance(key, str) and len(key) > 4096):
                    raise ValueError("unsupported checkpoint key")
                inspect(child, depth + 1)
        elif type(item) in (list, tuple):
            if len(item) > 8192:
                raise ValueError("checkpoint sequence budget")
            for child in item:
                inspect(child, depth + 1)
        elif item is None or type(item) in (str, int, float, bool):
            if (isinstance(item, str) and len(item) > 65536
                    or type(item) is float and not math.isfinite(item)):
                raise ValueError("invalid checkpoint scalar")
        else:
            raise ValueError("unsupported checkpoint value")

    inspect(value)
    if file_sha256(path, max_bytes=max_bytes) != before:
        raise ValueError("checkpoint changed while loading")
    return value


class FrozenEncoder(torch.nn.Module):
    feature_dim = 576

    def __init__(self, *, weights_path: Path | None = None, weights_sha256: str | None = None,
                 test_only: bool = False, seed: int = 42):
        super().__init__()
        if type(test_only) is not bool or type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("invalid encoder provenance/seed")
        if test_only and (weights_path is not None or weights_sha256 is not None):
            raise ValueError("random smoke encoder cannot claim pretrained weights")
        if not test_only and (weights_path is None or weights_sha256 is None):
            raise ValueError("local IMAGENET1K_V1 file and trusted full SHA-256 required")
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            model = torchvision.models.mobilenet_v3_small(weights=None)
        if not test_only:
            actual = file_sha256(weights_path, max_bytes=16 * 1024**2)
            url = torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1.url
            publisher_prefix = Path(url).stem.rsplit("-", 1)[-1]
            if actual != weights_sha256 or not actual.startswith(publisher_prefix):
                raise ValueError("local IMAGENET1K_V1 hash does not match prepared/publisher hash")
            model.load_state_dict(safe_torch_load(weights_path, expected_sha256=actual,
                                                  max_bytes=16 * 1024**2), strict=True)
        self.features = model.features
        self.test_only = test_only
        self.weights_sha256 = weights_sha256
        self.seed = seed if test_only else None
        self.requires_grad_(False)
        self.train(False)

    def train(self, mode: bool = True):
        # Keep BatchNorm statistics frozen when the enclosing temporal model trains.
        return super().train(False)

    def descriptor(self) -> dict:
        return {"backbone": "mobilenet_v3_small", "feature_dim": 576, "pooling": "spatial_mean",
                "weights": "None" if self.test_only else "IMAGENET1K_V1", "test_only": self.test_only,
                "weights_sha256": self.weights_sha256, "seed": self.seed,
                "state_sha256": encoder_fingerprint(self), "device": str(next(self.parameters()).device),
                "torch": str(torch.__version__), "torchvision": str(torchvision.__version__)}

    def forward(self, images: torch.Tensor, image_mask: torch.Tensor | None = None):
        if (images.ndim not in (4, 5) or tuple(images.shape[-3:]) != (3, 224, 224)
                or images.dtype != torch.float32 or images.numel() > 64 * 3 * 224 * 224):
            raise ValueError("encoder expects bounded FP32 [B,T,3,224,224] or [B,3,224,224]")
        shape = images.shape[:-3]
        if not all(shape):
            raise ValueError("empty image batch")
        mask = torch.ones(shape, dtype=torch.bool, device=images.device) if image_mask is None else image_mask
        if mask.shape != shape or mask.dtype != torch.bool or mask.device != images.device:
            raise ValueError("encoder image mask shape/dtype/device")
        flattened = images.reshape(-1, 3, 224, 224)
        selected = mask.reshape(-1)
        result = images.new_zeros((flattened.shape[0], 576))
        if selected.any():
            pixels = flattened[selected]
            if not bool(torch.isfinite(pixels).all()):
                raise ValueError("non-finite observed pixels")
            with torch.no_grad():
                result[selected] = self.features(pixels).mean(dim=(-2, -1))
        if not bool(torch.isfinite(result).all()):
            raise ValueError("non-finite encoder features")
        return result.reshape(*shape, 576)
