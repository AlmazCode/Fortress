import pytest
from ml.seed_vote import majority


def controls():
    return {s:[{'video_id':'v','truth':True,'fold':0,'score':p,'threshold':t}]
            for s,p,t in [('42',.6,.7),('137',.3,.2),('2026',.4,.3)]}


def test_vote_preserves_member_thresholds_and_majority():
    assert majority(controls())[0]['positive_votes']==2
    assert majority(controls())[0]['score']==2/3


def test_mixed_fold_and_duplicate_source_are_rejected():
    rows=controls();rows['42'][0]['fold']=1
    with pytest.raises(ValueError):majority(rows)
    rows=controls();rows['42']*=2
    with pytest.raises(ValueError):majority(rows)
