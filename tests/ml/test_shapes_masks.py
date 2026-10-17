from dataclasses import replace

import pytest
import torch

from ml.models import FrozenEncoder, ModelConfig, TemporalHead, VideoActionModel
from ml.models.encoder import file_sha256
from ml.train import masked_bce


@pytest.fixture(scope="module", autouse=True)
def cpu_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


def test_actual_frozen_encoder_video_shapes_and_temporal_gradients():
    encoder = FrozenEncoder(test_only=True)
    before = {k: v.clone() for k, v in encoder.state_dict().items()}
    model = VideoActionModel(encoder, ModelConfig(3)).train()
    images = torch.zeros(1, 2, 3, 224, 224)
    mask = torch.tensor([[True, False]])
    features = encoder(images, mask)
    logits, hidden = model(images, image_mask=mask)
    assert features.shape == (1, 2, 576) and logits.shape == (1, 2, 3) and hidden.shape == (1, 1, 256)
    assert encoder(images[:, 0]).shape == (1, 576)
    assert not features[:, 1].any() and not logits[:, 1].any() and not encoder.training
    logits[:, 0].sum().backward()
    assert all(p.grad is None and not p.requires_grad for p in encoder.parameters())
    assert all(torch.equal(v, before[k]) for k, v in encoder.state_dict().items())
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.temporal.parameters())
    assert not any("classifier" in key for key in model.state_dict())
    assert encoder.descriptor()["test_only"] and encoder.descriptor()["weights"] == "None"


def test_random_encoder_does_not_change_parent_rng_and_is_seeded():
    state = torch.get_rng_state().clone()
    first = FrozenEncoder(test_only=True, seed=18)
    assert torch.equal(state, torch.get_rng_state())
    assert first.descriptor() == FrozenEncoder(test_only=True, seed=18).descriptor()
    assert first.descriptor() != FrozenEncoder(test_only=True, seed=19).descriptor()


def test_no_download_or_random_pretrained_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.hub, "download_url_to_file", lambda *a, **k: pytest.fail("runtime download"))
    with pytest.raises(ValueError, match="local IMAGENET"):
        FrozenEncoder()
    path = tmp_path / "random.pt"
    torch.save(FrozenEncoder(test_only=True).state_dict(), path)
    with pytest.raises(ValueError, match="publisher hash"):
        FrozenEncoder(weights_path=path, weights_sha256=file_sha256(path))
    with pytest.raises(ValueError, match="cannot claim"):
        FrozenEncoder(test_only=True, weights_path=path)


def test_scene_reset_and_missing_frame_preserve_correct_hidden_state():
    torch.manual_seed(5)
    head = TemporalHead(ModelConfig(2)).eval()
    values = torch.randn(1, 5, 576)
    resets = torch.tensor([[False, False, True, False, False]])
    whole, state = head(values, reset_mask=resets)
    suffix, fresh_state = head(values[:, 2:])
    assert torch.equal(whole[:, 2:], suffix) and torch.equal(state, fresh_state)
    _, first = head(values[:, :1])
    absent = torch.full((1, 1, 576), float("nan"))
    out, missing = head(absent, hidden=first, image_mask=torch.tensor([[False]]))
    assert not out.any() and torch.equal(missing, first)
    _, reset_missing = head(absent, hidden=first, image_mask=torch.tensor([[False]]),
                            reset_mask=torch.tensor([[True]]))
    assert not reset_missing.any()


@pytest.mark.parametrize("bad", [torch.zeros(1, 2, 575), torch.zeros(1, 2, 576, dtype=torch.float64),
                                  torch.zeros(0, 2, 576)])
def test_temporal_shape_assertions(bad):
    with pytest.raises(ValueError):
        TemporalHead(ModelConfig(2))(bad)


def test_baseline_architecture_and_mask_assertions():
    for field, value in (("feature_dim", 577), ("hidden_size", 128), ("num_layers", 2),
                         ("bidirectional", True), ("dropout", .2), ("classes", 0)):
        with pytest.raises(ValueError):
            replace(ModelConfig(2), **{field: value})
    with pytest.raises(ValueError, match="mask"):
        TemporalHead(ModelConfig(2))(torch.zeros(1, 2, 576), image_mask=torch.ones(1, 2))
    with pytest.raises(ValueError, match="expects bounded"):
        FrozenEncoder(test_only=True)(torch.zeros(1, 3, 225, 224))


def test_loss_selects_known_observed_only_and_all_unknown_skips():
    logits = torch.tensor([[[0., float("nan")], [float("nan"), float("nan")]]], requires_grad=True)
    targets = torch.tensor([[[1., float("nan")], [float("nan"), float("nan")]]])
    known = torch.tensor([[[True, False], [True, True]]])
    image, padding = torch.tensor([[True, False]]), torch.tensor([[False, True]])
    loss = masked_bce(logits, targets, known, image, padding)
    assert loss.item() == pytest.approx(.69314718)
    loss.backward()
    assert torch.equal(logits.grad, torch.tensor([[[-.5, 0.], [0., 0.]]]))
    assert masked_bce(logits, targets, torch.zeros_like(known), image, padding) is None
    with pytest.raises(ValueError, match="supervised"):
        masked_bce(logits, targets, torch.ones_like(known), image, padding)
