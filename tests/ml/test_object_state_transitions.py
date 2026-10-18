import torch
from ml import object_state_transitions as transition


def test_constant_uncertain_presence_is_not_an_observed_departure():
    scores=torch.zeros(20,20);scores[:,7]=.7;scores[:,19]=.99;scores[:,18]=.99;scores[:,8]=.01
    support=torch.ones(20,dtype=torch.bool);risk,available=transition.probes(scores,support)
    assert available.all() and (risk[:3]==0).all()
    scores[:6,7]=.98;scores[6:,7]=.02
    risk,_=transition.probes(scores,support);assert risk[0]>.7 and risk[2]>.7


def test_storage_and_door_need_visible_changes_and_missing_context_stays_unknown():
    scores=torch.zeros(20,20);scores[:,7]=.9;scores[:,9]=.8;scores[:,13]=.8;scores[:,5]=.9
    support=torch.ones(20,dtype=torch.bool);risk,_=transition.probes(scores,support)
    assert risk[1]==0 and risk[3]==0
    scores[:4,9]=.1;scores[:4,13]=.1;scores[-8:,7]=.05
    risk,_=transition.probes(scores,support);assert risk[1]>.1 and risk[3]>.01
    support[7]=False;risk,available=transition.probes(scores,support)
    assert not available.any() and (risk==0).all()
    _,available=transition.probes(scores[:2],torch.ones(20,dtype=torch.bool));assert not available.any()
