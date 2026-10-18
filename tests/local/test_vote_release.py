import hashlib
from types import SimpleNamespace
from backend.local import app as native


def test_readiness_checks_every_ensemble_file_not_only_base_weights(tmp_path,monkeypatch):
    weights=tmp_path/'base.pt';weights.write_bytes(b'base')
    votes=tmp_path/'votes.pt';votes.write_bytes(b'voters')
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    metadata={'weights_sha256':digest(weights),'clip_metrics':{'accuracy':.75},
              'seed_vote_extension':{'model_sha256':'b'*64}}
    model=SimpleNamespace(metadata=metadata,integrity_files=[(weights,digest(weights)),(votes,digest(votes))])
    monkeypatch.setattr(native,'predictor',lambda *args:model)
    release=native.PrototypeRelease({'bundle_root':str(tmp_path),'device':'cpu'})
    assert release.readiness()['status']=='prototype'
    assert release.version=='prototype-seed-vote-'+('b'*12)
    votes.write_bytes(b'damaged')
    assert release.readiness()['status']!='prototype'


def test_source_action_release_has_its_own_identity_and_checks_new_encoder(tmp_path,monkeypatch):
    weights=tmp_path/'base.pt';weights.write_bytes(b'base')
    encoder=tmp_path/'encoder.pth';encoder.write_bytes(b'action encoder')
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    metadata={'weights_sha256':digest(weights),'clip_metrics':{'accuracy':.75},'ensemble_size':3,
              'source_action_extension':{'model_sha256':'c'*64},'action_metrics':{'operator_at_station':{'f1':.98}}}
    model=SimpleNamespace(metadata=metadata,integrity_files=[(weights,digest(weights)),(encoder,digest(encoder))])
    monkeypatch.setattr(native,'predictor',lambda *args:model)
    release=native.PrototypeRelease({'bundle_root':str(tmp_path),'device':'cpu'})
    assert release.version=='prototype-source-actions-'+('c'*12)
    assert '75.00%' in release.limitations[0]
    assert release.readiness()['validated'] is False
    encoder.write_bytes(b'damaged')
    assert release.readiness()['status']!='prototype'
