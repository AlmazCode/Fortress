from types import SimpleNamespace
import torch
from ml.hidden_risk import Experiment
from ml import temporal_risk as parent


def test_hidden_variant_preserves_the_original_gru_and_never_uses_detail_dimensions():
    torch.set_num_threads(1);torch.manual_seed(21)
    original={'v':{'features':torch.randn(5,parent.DIM),'score':.7}}
    before=original['v']['features'].clone()
    experiment=object.__new__(Experiment)
    experiment.parent=SimpleNamespace(representations=lambda ids,seed:original)
    result=experiment.representations(['v'],42)
    assert torch.equal(result['v']['features'][:,:256],before[:,:256])
    assert result['v']['features'][:,256:].count_nonzero()==0
    assert torch.equal(original['v']['features'],before)
