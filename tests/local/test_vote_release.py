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
