import pytest
from ml.seed_vote_infer import vote_score,proof


def test_three_member_vote_and_uncalibrated_score():
    assert vote_score([.2,.5,.8],[.3,.3,.3])==2/3
    assert vote_score([.2,.2,.2],[.3,.3,.3])==0
    for values in [[.1,.2],[.1,float('nan'),.2],[.1,2.,.2]]:
        with pytest.raises(ValueError):vote_score(values,[.3,.3,.3])


def test_unbound_package_fails_before_loading_weights(tmp_path):
    with pytest.raises(ValueError,match='Unsupported seed vote'):
        proof(tmp_path,{'seed_vote_extension':{'version':'invented'}})
