"""One causal GRU with explicit availability and scene resets."""
from dataclasses import asdict, dataclass

import torch

from ml.models.encoder import FrozenEncoder


@dataclass(frozen=True)
class ModelConfig:
    classes: int
    version: str = "mbv3s-gru-v1"
    feature_dim: int = 576
    hidden_size: int = 256
    num_layers: int = 1
    bidirectional: bool = False
    dropout: float = 0.0

    def __post_init__(self):
        if (type(self.classes) is not int or not 1 <= self.classes <= 256
                or self.version != "mbv3s-gru-v1" or self.feature_dim != 576 or self.hidden_size != 256
                or self.num_layers != 1 or self.bidirectional is not False or self.dropout != 0.0):
            raise ValueError("unsupported baseline architecture")

    def descriptor(self):
        return asdict(self)


class TemporalHead(torch.nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.gru = torch.nn.GRU(576, 256, num_layers=1, batch_first=True)
        self.head = torch.nn.Linear(256, config.classes)

    def forward(self, features, *, image_mask=None, reset_mask=None, hidden=None):
        if (features.ndim != 3 or features.shape[-1] != 576 or features.dtype != torch.float32
                or not 1 <= features.shape[0] <= 64 or not 1 <= features.shape[1] <= 1024):
            raise ValueError("temporal features must be FP32 [B,T,576]")
        batch, steps, _ = features.shape
        image_mask = (torch.ones((batch, steps), dtype=torch.bool, device=features.device)
                      if image_mask is None else image_mask)
        reset_mask = (torch.zeros_like(image_mask) if reset_mask is None else reset_mask)
        for mask in (image_mask, reset_mask):
            if mask.shape != (batch, steps) or mask.dtype != torch.bool or mask.device != features.device:
                raise ValueError("temporal mask shape/dtype/device")
        if not bool(torch.isfinite(features[image_mask]).all()):
            raise ValueError("non-finite observed temporal features")
        if hidden is None:
            hidden = features.new_zeros((1, batch, 256))
        if (hidden.shape != (1, batch, 256) or hidden.dtype != features.dtype
                or hidden.device != features.device or not bool(torch.isfinite(hidden).all())):
            raise ValueError("invalid temporal hidden state")
        logits = []
        for time in range(steps):
            hidden = torch.where(reset_mask[:, time][None, :, None], torch.zeros_like(hidden), hidden)
            observed = image_mask[:, time]
            current = torch.where(observed[:, None], features[:, time], torch.zeros_like(features[:, time]))
            output, candidate = self.gru(current[:, None], hidden)
            hidden = torch.where(observed[None, :, None], candidate, hidden)
            prediction = self.head(output[:, 0])
            logits.append(torch.where(observed[:, None], prediction, torch.zeros_like(prediction)))
        return torch.stack(logits, dim=1), hidden


class VideoActionModel(torch.nn.Module):
    def __init__(self, encoder: FrozenEncoder, config: ModelConfig):
        super().__init__()
        self.encoder = encoder
        self.temporal = TemporalHead(config)

    def forward(self, images, *, image_mask=None, reset_mask=None, hidden=None):
        if images.ndim != 5:
            raise ValueError("video model expects [B,T,3,224,224]")
        return self.temporal(self.encoder(images, image_mask), image_mask=image_mask,
                             reset_mask=reset_mask, hidden=hidden)
