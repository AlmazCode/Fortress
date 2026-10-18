from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
import torch
from ml import object_rules as rules
from ml.video_baseline import atomic_checkpoint
from ml.models.encoder import file_sha256,safe_torch_load


def test_weighted_bce_inverse_recovers_the_unweighted_conditional_probability():
    p=torch.tensor([.01,.2,.5,.9]);weight=torch.tensor([10.,4.,.5,.1])
    q=weight*p/(weight*p+1-p)
    torch.testing.assert_close(rules.correct(q,weight.log()),p)


def test_corrected_readout_trains_only_requested_sources_and_roundtrips(tmp_path):
    torch.set_num_threads(2)
    neural=tmp_path/'neural.pt';atomic_checkpoint(neural,{'spatial':str(tmp_path/'spatial.pt'),'spatial_sha256':'a'*64})
    targets=torch.full((4,18),-1.);targets[:,0]=torch.tensor([0,0,0,1]);targets[:,7]=torch.tensor([1,1,0,0])
    observed=[{'states':torch.ones(4,18)*.4,'objects':torch.ones(4,10)*.3,'prior':torch.zeros(4,14,14),
               'support':torch.ones(18,dtype=torch.bool),'object_support':torch.ones(10,dtype=torch.bool)}]*2
    experiment=object.__new__(rules.Experiment);experiment.fits=tmp_path/'heads';experiment.fits.mkdir()
    experiment.plan={'protocol_sha256':'f'*64}
    experiment.base=SimpleNamespace(rows={'a':{'actions':targets,'target':0},'b':{'actions':targets,'target':1}},observations=lambda p,ids:observed)
    experiment.neural=lambda ids,seed,final=False:neural
    path=experiment.fit(['a','b'],42);state=safe_torch_load(path)
    assert state['identity']['ids']==['a','b'] and state['identity']['neural_sha256']==file_sha256(neural)
    assert state['log_weight'][0]==pytest.approx(torch.tensor(3.).log().item())
    assert torch.isfinite(state['std']).all() and (state['std']>=.05).all()


def test_neural_lookup_rejects_reserved_before_checkpoint_read(tmp_path):
    experiment=object.__new__(rules.Experiment)
    def guard(ids):
        if not set(ids)<={'a','b'}:raise ValueError('development only')
    experiment.base=SimpleNamespace(guard_ids=guard,fits=tmp_path,plan={})
    with pytest.raises(ValueError,match='development only'):experiment.neural(['reserved'],42)
