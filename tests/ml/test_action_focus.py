"""Behavioral guards for the local action-first experiment."""
import copy

import numpy as np
import pytest
import torch

from ml import action_focus as focus
from ml import action_focus_inputs as inputs
from ml import action_refinement as previous
from ml.small_data import fit_norm


def test_exact_source_observations_never_fill_between_frames():
    index={"frames":[{"source_pts":p,"timestamp_sec":p/10} for p in (0,1,2)]}
    observed=[{"source_pts":1,"timestamp_sec":.1,"values":[1]*len(inputs.TAXONOMY)}]
    target=inputs.exact_targets(observed,[0,1,2],index)
    assert (target[0]==-1).all() and (target[2]==-1).all() and (target[1]==1).all()
    with pytest.raises(ValueError):inputs.exact_targets(observed*2,[0,1,2],index)
    with pytest.raises(ValueError):inputs.exact_targets([{**observed[0],"timestamp_sec":.2}],[0,1,2],index)


def test_projection_keeps_evidence_and_old_values_without_mutating_source():
    names=list(inputs.TAXONOMY)
    original={"version":inputs.REVIEW_VERSION,"taxonomy":names,"class_definitions":{n:n for n in names},
              "videos":[{"evidence":[{"path":"local","source_pts":12}],"observations":[{"values":list(range(15))}]}]}
    saved=copy.deepcopy(original);projected=inputs.project_review(original)
    assert original==saved
    assert projected["version"]==previous.VERSION
    assert projected["videos"][0]["evidence"]==original["videos"][0]["evidence"]
    assert projected["videos"][0]["observations"][0]["values"]==list(range(11))


def test_unknown_labels_have_zero_gradient_and_unsupported_class_is_disabled():
    logits=torch.zeros(1,3,15,requires_grad=True)
    targets=torch.full((1,3,15),-1.)
    targets[0,0,0]=0;targets[0,1,0]=1;targets[0,2,1]=1
    weights=previous.auxiliary_weights(targets)
    focus.masked_loss(logits,targets,weights).backward()
    assert logits.grad[0,0,0]!=0 and logits.grad[0,1,0]!=0
    assert logits.grad[0,2,0]==0 and (logits.grad[:,:,1:]==0).all()


@pytest.mark.parametrize("bottleneck",[False,True])
def test_padding_does_not_change_video_or_observed_action_outputs(bottleneck):
    torch.manual_seed(2)
    model=focus.ActionFirstGRU(0,bottleneck).eval()
    values=torch.randn(2,8,576);lengths=torch.tensor([3,8])
    with torch.no_grad():
        v,a,o=model(values,lengths)
        changed=values.clone();changed[0,3:]=1e5
        vv,aa,oo=model(changed,lengths)
    torch.testing.assert_close(v,vv)
    torch.testing.assert_close(a[0,:3],aa[0,:3])
    torch.testing.assert_close(o[0,:3],oo[0,:3])


def test_actions_are_causal_even_when_video_verdict_pools_full_sequence():
    torch.manual_seed(3);model=focus.ActionFirstGRU(0).eval()
    values=torch.randn(1,8,576)
    with torch.no_grad():
        _,a,o=model(values,torch.tensor([8]));values[:,4:]+=100
        _,aa,oo=model(values,torch.tensor([8]))
    torch.testing.assert_close(a[:,:4],aa[:,:4]);torch.testing.assert_close(o[:,:4],oo[:,:4])


def test_action_only_verdict_cannot_depend_on_unsupported_channels():
    model=focus.ActionFirstGRU(0,True).eval();model.support.zero_()
    with torch.no_grad():
        first=model(torch.randn(1,7,576),torch.tensor([7]))[0]
        second=model(torch.randn(1,7,576)*100,torch.tensor([7]))[0]
    torch.testing.assert_close(first,second)


def test_training_pairs_are_only_opposite_verdicts_in_same_family():
    rows=[{"group_id":g,"target":t} for g,t in [("a",1),("a",0),("b",0),("b",1)]]
    assert focus.training_pairs(rows)==[(0,1),(3,2)]
    good=focus.pair_loss(torch.tensor([3.,-3.,-3.,3.]),focus.training_pairs(rows))
    bad=focus.pair_loss(torch.tensor([-3.,3.,3.,-3.]),focus.training_pairs(rows))
    assert good<bad


def test_clips_stay_within_video_and_never_get_clip_verdict_targets():
    row={"features":torch.zeros(99,576),"actions":torch.full((99,15),-1.)}
    row["actions"][98,0]=1
    rng=np.random.default_rng(42)
    starts=[focus.clip_start(row,32,rng) for _ in range(100)]
    assert min(starts)>=0 and max(starts)<=67 and 67 in starts


def test_normalization_uses_only_supplied_training_rows_and_rejects_holdout():
    rows=[{"target":t,"split":"train","features":torch.full((2,576),float(t))} for t in (0,1)]
    norm=fit_norm(rows);assert (norm["mean"]==.5).all()
    with pytest.raises(ValueError):fit_norm([{**rows[0],"split":"independent_test"},rows[1]])


def test_threshold_is_selected_without_outer_labels():
    predictions=[{"truth":False,"score":.6},{"truth":True,"score":.7}]
    threshold=focus.calibrate(predictions)
    assert .6<threshold<.7
    assert focus.rank({"metrics":{"accuracy":.9,"balanced_accuracy":.5,"macro_f1":.5},"bce":.1}) < focus.rank({"metrics":{"accuracy":.8,"balanced_accuracy":.8,"macro_f1":.8},"bce":.5})


def test_fit_rejects_reserved_before_any_tensor_or_checkpoint_work(tmp_path):
    experiment=object.__new__(focus.Experiment)
    experiment.plan={"development_ids":["video_001"]}
    experiment.fits=tmp_path
    with pytest.raises(ValueError):experiment.fit(["video_020"],"roi_joint",focus.CONFIG,42)
    with pytest.raises(ValueError):experiment.fit(["video_001"]*2,"roi_joint",focus.CONFIG,42)


@pytest.mark.parametrize("arm",["roi_pretrain","roi_action_bottleneck"])
def test_actual_action_pretraining_roundtrip_and_heldout_predict(tmp_path,arm):
    from ml.models.encoder import safe_torch_load
    torch.set_num_threads(2)
    experiment=object.__new__(focus.Experiment)
    experiment.device="cpu";experiment.fits=tmp_path
    experiment.plan={"development_ids":["v0","v1"],"protocol_sha256":"a"*64}
    experiment.by_id={}
    for n in range(3):
        a=torch.full((6,15),-1.);a[:,0]=torch.tensor([0,0,0,1,1,1])
        experiment.by_id[f"v{n}"]={"video_id":f"v{n}","target":n%2,"split":"train" if n<2 else "independent_test",
            "group_id":"pair","prefix":torch.zeros(6,1,96,7,7),"roi_features":torch.randn(6,576),"roi_actions":a,"roi_objects":torch.full((6,7),-1.),
            "roi_pts":np.arange(6,dtype=np.int64),"roi2_indices":torch.arange(6)}
    config={**focus.CONFIG,"epochs":2,"pretrain_epochs":2}
    path=experiment.fit(["v0","v1"],arm,config,42)
    state=safe_torch_load(path)
    assert len(state["pretrain_loss_history"])==2
    assert state["identity"]["ids"]==["v0","v1"]
    predictions=experiment.predict(path,["v2"])
    assert len(predictions)==1 and 0<=predictions[0]["score"]<=1


def test_cnn_updates_only_suffix_with_frozen_batchnorm_statistics():
    from ml.models.encoder import FrozenEncoder
    torch.set_num_threads(2)
    experiment=object.__new__(focus.Experiment);experiment.device="cpu"
    experiment.suffix_template=copy.deepcopy(FrozenEncoder(test_only=True).features[-2:]).eval()
    a=torch.full((4,15),-1.);a[:,0]=torch.tensor([0,0,1,1])
    experiment.by_id={"train":{"prefix":torch.randn(4,3,96,7,7),"roi_actions":a,"roi_objects":torch.full((4,7),-1.)}}
    before={k:v.clone() for k,v in experiment.suffix_template.state_dict().items()}
    suffix,_=experiment.adapt_cnn(["train"],{**focus.CONFIG,"cnn_epochs":1})
    after=suffix.state_dict()
    assert any(not torch.equal(before[k],after[k]) for k in before if k.endswith("weight"))
    for k in before:
        if "running_" in k or "num_batches" in k:assert torch.equal(before[k],after[k])
    for k in before:assert torch.equal(before[k],experiment.suffix_template.state_dict()[k])
