import torch
import pytest

from ml import action_focus as training
from ml import action_focus_infer as inference
from ml.models.encoder import FrozenEncoder
from ml.video_baseline import atomic_checkpoint,atomic_json


def test_exported_encoder_matches_original_feature_path():
    torch.set_num_threads(2)
    original=FrozenEncoder(test_only=True)
    portable=inference.FeatureEncoder(original.features.state_dict())
    image=torch.randn(2,3,224,224)
    with torch.inference_mode():torch.testing.assert_close(original(image),portable(image),rtol=0,atol=0)


def test_portable_bundle_load_and_hash_rejection(tmp_path):
    torch.set_num_threads(2)
    encoder=FrozenEncoder(test_only=True);model=training.ActionFirstGRU()
    payload={"format":inference.VERSION,"encoder":dict(encoder.features.state_dict()),"model":dict(model.state_dict()),
             "normalization":{"mean":torch.zeros(576),"std":torch.ones(576)},"auxiliary_weights":[]}
    atomic_checkpoint(tmp_path/"weights.pt",payload)
    metadata={"version":inference.VERSION,"arm":"roi_joint","config":training.CONFIG,"threshold":.5,
              "weights_sha256":inference.file_sha256(tmp_path/"weights.pt"),"inference_code_sha256":inference.code_hash(),
              "training_code_sha256":training.code_hash(),"roi":list(inference.inputs.ROI),
              "taxonomy":list(inference.inputs.TAXONOMY),"production_ready":False}
    atomic_json(tmp_path/"bundle.json",metadata)
    loaded=inference.Predictor(tmp_path,"cpu")
    assert loaded.metadata["production_ready"] is False
    with (tmp_path/"weights.pt").open("ab") as f:f.write(b"changed")
    with pytest.raises(ValueError,match="SHA-256 mismatch"):inference.Predictor(tmp_path,"cpu")
