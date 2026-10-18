import pytest
from ml import object_state_ensemble as ensemble


def test_fixed_ensembles_preserve_exact_source_and_truth_alignment():
    new=[{'video_id':'a','truth':False,'score':.2},{'video_id':'b','truth':True,'score':.8}]
    old=[{'video_id':'b','truth':True,'score':.6},{'video_id':'a','truth':False,'score':.4}]
    c={'arm':'state_blend'};p=ensemble.merge(c,new,old)
    assert p[0]['score']==pytest.approx(.3) and p[1]['score']==pytest.approx(.7)
    assert ensemble.merge({'arm':'legacy_uniform'},new,old)[0]['score']==.4
    with pytest.raises(ValueError,match='coverage'):ensemble.merge(c,new,old[:1])
    with pytest.raises(ValueError,match='truth'):ensemble.merge(c,new,[{**v,'truth':not v['truth']} for v in old])
    assert len(ensemble.candidates())==17 and len({x['name'] for x in ensemble.candidates()})==17
    for candidate in ensemble.candidates():assert ensemble.base_candidate(candidate) in ensemble.helpers.candidates()


def test_local_consensus_binds_the_correct_local_object_core():
    from ml import object_state_consensus as consensus,object_state_local as local
    assert consensus.core is local and consensus.VERSION!=ensemble.VERSION
    assert consensus.candidates()==ensemble.candidates()
    assert consensus.code_hash()!=ensemble.code_hash()
