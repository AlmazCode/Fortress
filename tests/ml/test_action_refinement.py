"""Unknown masks, source-time supervision and held-out family isolation."""
from pathlib import Path

import numpy as np
import pytest
import torch

from ml.action_refinement import (ActionGRU, Experiment, LOSS_WEIGHTS, OBJECT_IDS, TAXONOMY, VERSION,
                                  auxiliary_weights, masked_loss, observation_targets)
from ml.models.encoder import safe_torch_load
from ml.small_data import fit_norm, split_folds


@pytest.fixture(autouse=True)
def one_thread():
    before = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(before)


def test_exact_source_pts_only_no_interval_fill_or_unknown_negatives():
    index = {"frames":[{"source_pts":p,"timestamp_sec":p/100} for p in (100, 151, 201, 305)]}
    target = [1,0]+[-1]*(len(TAXONOMY)-2)
    obs = [{"source_pts":151,"timestamp_sec":1.51,"values":target}]
    values = observation_targets(obs,np.array([100,151,201,305]),index)
    assert values[1].tolist() == target
    assert (values[[0,2,3]] == -1).all()
    assert (observation_targets(obs,np.array([100,201,305]),index) == -1).all()
    for changed in ({**obs[0],"timestamp_sec":1.5}, {**obs[0],"source_pts":150}, {**obs[0],"values":[2]*len(TAXONOMY)}):
        with pytest.raises(ValueError,match="observation"):
            observation_targets([changed],np.array([100,151]),index)
    with pytest.raises(ValueError,match="duplicate"):
        observation_targets(obs+obs,np.array([100,151]),index)


def test_masked_loss_has_zero_unknown_gradient_and_no_unsupported_class_training():
    targets = torch.tensor([[[1.,-1.,1.],[0.,-1.,1.],[-1.,-1.,1.]]])
    logits = torch.zeros_like(targets,requires_grad=True)
    weights = auxiliary_weights(targets)
    assert weights["enabled"].tolist() == [True,False,False]
    loss = masked_loss(logits,targets,weights)
    loss.backward()
    assert logits.grad[0,0,0] < 0 < logits.grad[0,1,0]
    assert (logits.grad[:,:,1:] == 0).all() and logits.grad[0,2,0] == 0
    empty = torch.full_like(targets,-1.)
    assert masked_loss(logits,empty,auxiliary_weights(empty)) == 0


def test_padding_does_not_change_video_or_action_logits_and_gru_is_causal():
    torch.manual_seed(42)
    model = ActionGRU(.35).eval()
    source = torch.randn(1,5,576)
    padded = torch.cat([source,torch.full((1,3,576),10000.)],1)
    original = model(source,torch.tensor([5]))
    extra = model(padded,torch.tensor([5]))
    assert torch.allclose(original[0],extra[0])
    assert torch.allclose(original[1],extra[1][:,:5])
    changed = source.clone(); changed[:,3:] *= 100
    assert torch.allclose(original[1][:,:3],model(changed,torch.tensor([5]))[1][:,:3])


def synthetic_rows():
    torch.manual_seed(5)
    rows = []
    for n in range(8):
        length = 5+n%3
        actions = torch.full((length,len(TAXONOMY)),-1.)
        actions[:,0] = torch.arange(length)%2
        objects = torch.full((length,7),-1.); objects[:,0] = torch.arange(length)%2
        rows.append({"video_id":f"v{n}","source_sha256":str(n),"group_id":f"g{n//2}",
                     "split":"train","target":n%2,"features":torch.randn(length,576)+(n%2)*.4,
                     "actions":actions,"objects":objects})
    return rows


def experiment(tmp_path,rows):
    obj = Experiment.__new__(Experiment)
    obj.device = "cpu"
    obj.plan = {"protocol_sha256":"unit-test","development_ids":[r["video_id"] for r in rows[:6]],"loss_weights":LOSS_WEIGHTS}
    obj.by_id = {r["video_id"]:r for r in rows}
    obj.fits = tmp_path/"fits"; obj.fits.mkdir()
    return obj


@pytest.mark.parametrize("arm",list(LOSS_WEIGHTS))
def test_actual_fit_normalizes_and_supervises_training_sources_only(tmp_path,arm):
    rows = synthetic_rows()
    obj = experiment(tmp_path,rows)
    ids = [r["video_id"] for r in rows[:6]]
    config = {"epochs":3,"lr":.001,"dropout":.2,"weight_decay":.01}
    fitted = obj.fit(ids,arm,config,42)
    saved = safe_torch_load(fitted)
    assert torch.equal(saved["normalization"]["mean"],fit_norm(rows[:6])["mean"])
    assert len(saved["loss_history"]) == 3
    predictions = obj.predict(fitted,["v6","v7"])
    assert all(0 <= p["score"] <= 1 for p in predictions)
    separate = obj.predict(fitted,["v7"])
    assert separate[0]["video_id"] == predictions[1]["video_id"]
    assert separate[0]["truth"] == predictions[1]["truth"]
    # FP32 kernels may round differently for batch sizes one and two. Keep the
    # before/after isolation assertion below exact by using the same batch layout.
    assert separate[0]["score"] == pytest.approx(predictions[1]["score"],abs=1e-6,rel=0)
    before = Path(fitted).read_bytes()
    rows[6]["actions"][:] = 1; rows[6]["objects"][:] = 1
    rows[6]["features"] *= 1000
    assert obj.fit(ids,arm,config,42) == fitted and Path(fitted).read_bytes() == before
    assert obj.predict(fitted,["v7"]) == separate
    with pytest.raises(ValueError,match="development"):
        obj.fit(ids+["v6"],arm,config,42)
    assert saved["production_ready"] is False and saved["human_approved_actions"] is False


def test_auxiliary_labels_do_change_shared_representation(tmp_path):
    rows = synthetic_rows(); obj = experiment(tmp_path,rows)
    ids = [r["video_id"] for r in rows[:6]]
    config = {"epochs":2,"lr":.001,"dropout":.2,"weight_decay":.01}
    base = safe_torch_load(obj.fit(ids,"video_only",config,42))["model"]
    assisted = safe_torch_load(obj.fit(ids,"actions_objects",config,42))["model"]
    assert not torch.equal(base["gru.weight_ih_l0"],assisted["gru.weight_ih_l0"])


def test_inner_selection_never_predicts_its_training_families(tmp_path):
    rows = synthetic_rows(); obj = experiment(tmp_path,rows)
    obj.plan["grid"] = {"actions":[{"c":0},{"c":1}]}
    folds = split_folds(rows[:6],3,42)
    def fit(ids,arm,config,seed):
        return (set(obj.by_id[v]["group_id"] for v in ids),config["c"])
    def predict(fitted,ids):
        assert fitted[0].isdisjoint(obj.by_id[v]["group_id"] for v in ids)
        return [{"video_id":v,"truth":bool(obj.by_id[v]["target"]),
                 "score":(.61 if obj.by_id[v]["target"] else .60) if fitted[1] else .5} for v in ids]
    obj.fit,obj.predict = fit,predict
    _,selected = obj.select(folds)
    assert selected["config"] == {"c":1}
    assert .60 < selected["threshold"] < .61


def test_saved_string_paths_reload_and_reserved_object_targets_stay_unknown(tmp_path,monkeypatch):
    import json
    import ml.action_refinement as module
    def write(path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding="utf-8")
    package,prepared,cache = tmp_path/"package",tmp_path/"prepared",tmp_path/"cache"
    cache.mkdir()
    write(prepared/"readiness.json",{"source_root":str(package)})
    index = {"frames":[{"source_pts":0,"timestamp_sec":0.}]}
    write(prepared/"indices/v.json",index)
    write(package/"annotations/objects.coco.json",{
        "categories":[{"id":c} for c in (*OBJECT_IDS,3)],
        "annotations":[],"images":[{"id":1,"video_id":"v","source_pts":0,"timestamp_sec":0.,"source_sha256":"s"}]})
    write(package/"fortress_manual_review.completed.json",{
        "objects":{"1":{"reviewed":True,"confirmation_basis":"user_declared_objects_complete"}}})
    overlay = tmp_path/"review/actions.json"
    write(overlay,{"version":VERSION,"taxonomy":list(TAXONOMY),"human_approved":False,
                   "provenance":"assistant_sequence_review","original_verdicts_changed":False,"videos":[]})
    np.savez(cache/"v.npz",source_pts=np.array([0],dtype=np.int64))
    row = {"video_id":"v","split":"independent_test","source_sha256":"s","path":"v.npz"}
    monkeypatch.setattr(module,"load_feature_cache",lambda _:({"prepared_dir":str(prepared)},[dict(row)]))
    first = module.load_inputs(str(cache),str(overlay))
    assert (first[1][0]["objects"] == -1).all()
    assert (first[1][0]["actions"] == -1).all()
    row["split"] = "train"
    second = module.load_inputs(cache,overlay)
    assert (second[1][0]["objects"] == 0).all()  # only the declared-complete provided frame
    assert first[2] == second[2]
