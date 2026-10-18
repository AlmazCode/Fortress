import json
import pytest
from backend.local import select_model as selection


def test_rejected_package_does_not_mutate_configuration(tmp_path,monkeypatch):
    config=tmp_path/'config.json';original=b'{"port":8000,"bundle_root":"old","device":"cuda"}'
    config.write_bytes(original);bundle=tmp_path/'bundle';bundle.mkdir()
    monkeypatch.setattr(selection,'port_open',lambda port:False)
    def reject(config):raise ValueError('package rejected')
    monkeypatch.setattr(selection,'PrototypeRelease',reject)
    with pytest.raises(ValueError):selection.select(config,bundle)
    assert config.read_bytes()==original
    assert not list(tmp_path.glob('*.before-model-*.json'))


def test_selection_preserves_other_settings_and_recoverable_backup(tmp_path,monkeypatch):
    config=tmp_path/'config.json';original=b'{"port":8000,"bundle_root":"old","device":"cuda","api_key_file":"private"}'
    config.write_bytes(original);bundle=tmp_path/'bundle';bundle.mkdir()
    monkeypatch.setattr(selection,'port_open',lambda port:False)
    class Release:
        def __init__(self,config):pass
        def readiness(self):return {'status':'prototype','trained':True,'validated':False}
    monkeypatch.setattr(selection,'PrototypeRelease',Release)
    _,backup=selection.select(config,bundle)
    current=json.loads(config.read_text())
    assert current['bundle_root']==str(bundle.resolve()) and current['device']=='cuda'
    assert current['api_key_file']=='private' and backup.read_bytes()==original
