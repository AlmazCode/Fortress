from copy import deepcopy

import numpy as np
import pytest
import torch

from ml import human_action_training as human
from tools.label_review import VERSION, digest


def fixture():
    data = {'video_a': {'video_id': 'video_a', 'group_id': 'family_a', 'source_sha256': 'a'*64,
                        'source_pts': [0, 10, 20], 'times': [0., .5, 1.],
                        'coarse': torch.ones(3, 15), 'features': torch.zeros(3, 3840)}}
    manifest = {'version': VERSION, 'reserved_ids': ['reserved'],
                'videos': [{'id': 'video_a', 'group_id': 'family_a', 'source_sha256': 'a'*64,
                            'time_base': '1/20', 'origin_pts': 0}],
                'frames': [{'id': 'video_a-0', 'video_id': 'video_a', 'source_pts': 0, 'timestamp_sec': 0.},
                           {'id': 'video_a-10', 'video_id': 'video_a', 'source_pts': 10, 'timestamp_sec': .5}]}
    manifest['sha256'] = digest(manifest)
    record = {**manifest['frames'][0], 'group_id': 'family_a', 'source_sha256': 'a'*64,
              'time_base': '1/20', 'origin_pts': 0, 'question': 'storage_open', 'value': 'closed',
              'training_class': 'storage_open', 'training_value': 0, 'known': True,
              'human_approved': True, 'reviewer': 'local_human', 'reviewed_at': '2026-10-18'}
    unknown = {**record, **manifest['frames'][1], 'value': 'unknown', 'training_value': -1, 'known': False}
    snapshot = {'version': VERSION, 'manifest_sha256': manifest['sha256'], 'records': [record, unknown],
                'human_approved_records': 2, 'no_interval_extrapolation': True}
    return data, manifest, snapshot


def test_only_explicit_human_answers_used_without_mutating_old_targets():
    data, manifest, snapshot = fixture()
    rows, audit = human.import_targets(data, manifest, snapshot)
    assert rows['video_a']['coarse'][:, 9].tolist() == [0., -1., -1.]
    assert (rows['video_a']['coarse'][:, :9] == -1).all()
    assert (data['video_a']['coarse'] == 1).all()
    assert audit['old_known_conflicts'] == {'storage_open': 1}


@pytest.mark.parametrize('key,value', [('source_sha256', 'b'*64), ('source_pts', 5),
                                      ('time_base', '1/10'), ('training_value', 1), ('human_approved', False)])
def test_source_timing_and_human_target_tampering_rejected(key, value):
    data, manifest, snapshot = fixture()
    snapshot['records'][0][key] = value
    with pytest.raises(ValueError): human.import_targets(data, manifest, snapshot)


def test_duplicate_answers_and_reserved_sources_rejected():
    data, manifest, snapshot = fixture()
    snapshot['records'].append(deepcopy(snapshot['records'][0])); snapshot['human_approved_records'] = 3
    with pytest.raises(ValueError, match='Duplicate'): human.import_targets(data, manifest, snapshot)
    data, manifest, snapshot = fixture()
    manifest['reserved_ids'] = ['video_a']; manifest['sha256'] = digest({k: v for k, v in manifest.items() if k != 'sha256'})
    snapshot['manifest_sha256'] = manifest['sha256']
    with pytest.raises(ValueError, match='partition'): human.import_targets(data, manifest, snapshot)


def test_unknown_features_do_not_enter_classifier_fit():
    labels = torch.full((8, 15), -1.); labels[:3, 9] = 0; labels[3:6, 9] = 1
    rows = [{'video_id': 'a', 'group_id': 'f', 'coarse': labels}]
    x = np.array([[-1., 0.]]*3+[[1., 0.]]*3+[[0., 0.]]*2)
    first = human.fit_head(rows, {'a': x.copy()}, 9, 1.)
    x[6:] = 1000000.
    second = human.fit_head(rows, {'a': x}, 9, 1.)
    assert torch.equal(first['weight'], second['weight']) and first['bias'] == second['bias']
    labels[3:6, 9] = -1
    assert human.fit_head(rows, {'a': x}, 9, 1.) is None


def test_held_out_features_cannot_change_fit_or_normalizer():
    generator = torch.Generator().manual_seed(42)
    labels = torch.full((6, 15), -1.); labels[:, 9] = torch.tensor([0., 0., 0., 1., 1., 1.])
    data = {v: {'video_id': v, 'group_id': v, 'coarse': labels.clone(),
                'features': torch.randn(6, 3840, generator=generator)} for v in ('train', 'test')}
    choices = [{'candidate': {'mode': 'appearance', 'c': 1.}, 'threshold': .5}]
    _, first = human.train_selected(data, ['train'], ['test'], choices, [9])
    data['test']['features'] *= -100; data['test']['coarse'] *= -1
    _, second = human.train_selected(data, ['train'], ['test'], choices, [9])
    assert torch.equal(first['banks']['appearance']['mean'], second['banks']['appearance']['mean'])
    assert torch.equal(first['banks']['appearance']['scale'], second['banks']['appearance']['scale'])
    assert torch.equal(first['heads'][9]['head']['weight'], second['heads'][9]['head']['weight'])
