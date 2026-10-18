import numpy as np
import pytest
import torch

from ml.source_action_infer import decision_score, head_scores, methods
from ml.action_calibration import filtered
from ml.action_linear import representation
from ml.action_kernel import TAXONOMY


@pytest.mark.parametrize('threshold', [.1,.5,.9,1.000001])
def test_display_cut_matches_inner_decision_without_turning_disabled_head_positive(threshold):
    p=np.linspace(0,1,101)
    score=decision_score(p,threshold)
    assert np.array_equal(score>=.5,p>=threshold)
    assert np.all(np.diff(score)>=0)
    with pytest.raises(ValueError):decision_score([float('nan')],threshold)


def test_temporal_filter_never_bridges_source_gaps_or_unknown_predictions():
    assert np.array_equal(filtered([.9,.1,.9],[0,.5,3],'max3'),[.9,.1,.9])
    result=filtered([.9,float('nan'),.1],[0,.5,1],'max3')
    assert np.isnan(result[1]) and result[2]==.1
    with pytest.raises(ValueError):filtered([.9,.1],[1,0],'mean3')


def test_promotion_requires_precision_recall_and_improvement_not_easy_presence_average():
    bad={'precision':.99,'recall':.1,'f1':.18}
    good={'precision':.9,'recall':.9,'f1':.9}
    report={'classes':{name:{'control':{'f1':.8},'linear':bad,'kernel':good} for name in TAXONOMY}}
    assert methods(report)==['kernel']*len(TAXONOMY)
    report['classes'][TAXONOMY[0]]['control']['f1']=.95
    assert methods(report)[0]=='control'


def test_linear_normalization_uses_training_only_and_portable_head_agrees():
    x=torch.randn(5,3840,generator=torch.Generator().manual_seed(9))
    train=[{'video_id':'train','features':x}]
    values,a=representation(train,train,'appearance')
    _,b=representation(train,train+[{'video_id':'held','features':100+x*20}],'appearance')
    assert torch.equal(a['mean'],b['mean']) and torch.equal(a['scale'],b['scale'])
    h={'weight':torch.randn(3840,generator=torch.Generator().manual_seed(11)),'bias':.12}
    state={'banks':{'appearance':a},'heads':[{'bank':'appearance','head':h,'threshold':.4}]}
    expected=torch.tensor(values['train']).float()@h['weight']+h['bias']
    actual=head_scores(state,x,'linear')[0]
    np.testing.assert_allclose(actual,expected.sigmoid().numpy(),atol=2e-6)
