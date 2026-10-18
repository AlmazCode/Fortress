"""No-background leakage and convex, train-only operation decoder checks."""
import copy
import torch
import pytest
from ml import operation_decoder as m
from ml import temporal_actions as source


def rows():
    torch.manual_seed(17);result=[]
    for n in range(4):
        fine=torch.zeros(6,len(source.TAXONOMY));fine[1:5,1+n%2]=1
        result.append({'video_id':f'v{n}','group_id':f'f{n}','target':n%2,
                       'features':torch.randn(3,6,source.DIM),'fine':fine,'coarse':torch.zeros(6,len(source.COARSE))})
    return result


def test_decoder_features_remove_static_video_background_without_using_labels():
    torch.manual_seed(1);x=torch.randn(5,source.DIM)
    assert torch.allclose(m.visual_features(x),m.visual_features(x+7),atol=2e-6,rtol=0)
    assert m.visual_features(torch.zeros(1,source.DIM)).shape==(1,m.DIM)


def test_training_ignores_unknown_frames_and_held_out_labels():
    torch.set_num_threads(1);data=rows();a=m.fit(data,'cpu')
    other=copy.deepcopy(data);other[0]['fine'][0]=0
    held=copy.deepcopy(data[0]);held['fine'].fill_(0);held['target']=1-held['target']
    b=m.fit(other,'cpu')
    assert torch.equal(a['weight'],b['weight']) and torch.equal(a['mean'],b['mean'])
    assert torch.equal(m.predict(a,[data[0]])[0]['fine'],m.predict(b,[data[0]])[0]['fine'])
    assert torch.isfinite(m.predict(a,[held])[0]['fine']).all()


def test_residual_requires_exact_crossfit_coverage_and_cannot_make_unbounded_changes():
    data=rows();state=m.fit(data,'cpu');p=m.predict(state,data)
    ref=[{'video_id':r['video_id'],'truth':bool(r['target']),'score':.3+.1*r['target']} for r in data]
    with pytest.raises(ValueError,match='coverage'):m.fit_residual(p,ref[:-1],.4)
    correction=m.fit_residual(p,ref,.4)
    out=m.corrected_scores(correction,p,ref)
    for row,original in zip(out,ref):
        delta=m.logit(row['score'])-(m.logit(original['score'])-m.logit(.4))
        assert abs(float(delta))<=m.RESIDUAL_BOUND+1e-5
