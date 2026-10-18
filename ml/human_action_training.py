"""Train exact-frame heads from an immutable local human-review snapshot.

Only explicit human targets are used. Existing features/family splits are reused;
old labels, experiments and deployed models remain immutable.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import time
import warnings

import numpy as np
import torch
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from ml import action_linear as linear, action_kernel as base
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256, safe_torch_load
from ml.video_baseline import atomic_json, atomic_checkpoint
from tools.label_review import CHOICES, VERSION as REVIEW_VERSION, digest, file_hash, read_json

VERSION = 'human-frame-action-heads-v1'
GRID = [{'mode': mode, 'c': c} for mode in ('appearance', 'motion') for c in (.1, 1., 10., 100.)]


def code_hash():
    return stable_hash({'own': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        'linear': linear.code_hash(), 'review': file_hash(Path(__file__).parents[1]/'tools/label_review.py')})


def target(question, value):
    if question not in CHOICES or value not in CHOICES[question]:
        raise ValueError('Unknown human question/value')
    if question == 'bag_position':
        return 'bag_on_desk', {'on_desk': 1, 'in_hands': 0, 'elsewhere': 0, 'unknown': -1}[value]
    return question, (1 if value in ('yes', 'open', 'lit') else -1 if value == 'unknown' else 0)


def import_targets(data, manifest, snapshot):
    """Identity-check every answer; leave every unreviewed target unknown."""
    if (manifest.get('version') != REVIEW_VERSION or
            manifest.get('sha256') != digest({k: v for k, v in manifest.items() if k != 'sha256'}) or
            snapshot.get('version') != REVIEW_VERSION or snapshot.get('manifest_sha256') != manifest['sha256'] or
            snapshot.get('human_approved_records') != len(snapshot['records']) or
            snapshot.get('no_interval_extrapolation') is not True):
        raise ValueError('Human snapshot identity changed')
    videos = {v['id']: v for v in manifest['videos']}
    frames = {f['id']: f for f in manifest['frames']}
    if set(data) != set(videos) or set(data) & set(manifest['reserved_ids']):
        raise ValueError('Human development partition changed')
    positions = {}; result = {}
    for video, row in data.items():
        meta = videos[video]
        if row['source_sha256'] != meta['source_sha256'] or row['group_id'] != meta['group_id']:
            raise ValueError('Human source identity changed')
        positions[video] = {int(p): n for n, p in enumerate(row['source_pts'])}
        if len(positions[video]) != len(row['source_pts']):
            raise ValueError('Duplicate source PTS')
        result[video] = {**row, 'coarse': torch.full((len(row['source_pts']), len(base.TAXONOMY)), -1.)}
    seen = set(); counts = {}; conflicts = Counter(); extended = Counter()
    for record in snapshot['records']:
        frame = frames.get(record['id'])
        if frame is None or any(record[k] != frame[k] for k in ('video_id', 'source_pts', 'timestamp_sec')):
            raise ValueError('Human frame identity changed')
        video = frame['video_id']; meta = videos[video]; row = data[video]
        if any(record[k] != meta[k] for k in ('source_sha256', 'group_id', 'time_base', 'origin_pts')):
            raise ValueError('Human source timing changed')
        key = (record['id'], record['question'])
        if key in seen:
            raise ValueError('Duplicate human answer')
        seen.add(key)
        name, value = target(record['question'], record['value'])
        if (record['human_approved'] is not True or record['reviewer'] != 'local_human' or
                record['training_class'] != name or record['training_value'] != value or
                record['known'] != (value >= 0) or not record['reviewed_at']):
            raise ValueError('Human approval/target changed')
        counts.setdefault(name, Counter())[str(value)] += 1
        if name not in base.TAXONOMY:
            extended[name] += 1
            continue
        position = positions[video].get(record['source_pts'])
        if position is None or abs(float(row['times'][position])-record['timestamp_sec']) > 1e-4:
            raise ValueError('Human PTS is missing from feature cache')
        c = base.TAXONOMY.index(name)
        old = int(row['coarse'][position, c])
        if old >= 0 and value >= 0 and old != value:
            conflicts[name] += 1
        result[video]['coarse'][position, c] = value
    return result, {'answers': len(seen), 'counts': counts, 'old_known_conflicts': dict(conflicts),
                    'extended_targets_without_runtime_head': dict(extended)}


def load_inputs(root, manifest, snapshot):
    parent = root/'dino-source-actions-v1'
    marker = read_json(parent/'inputs.json')
    data = {e['video_id']: safe_torch_load(parent/'inputs'/(e['video_id']+'.pt'), expected_sha256=e['sha256'])
            for e in marker['entries']}
    source_root = Path(manifest['source_root']).resolve(strict=True)
    for meta in manifest['videos']:
        source = Path(meta['path']).resolve(strict=True)
        index = read_json(meta['index'])
        if (source_root not in source.parents or file_hash(source) != meta['source_sha256'] or
                file_hash(meta['index']) != meta['index_sha256'] or
                index['source_sha256'] != meta['source_sha256'] or index['group_id'] != meta['group_id'] or
                index['time_base'] != meta['time_base'] or index['origin_pts'] != meta['origin_pts']):
            raise ValueError('Actual human source/index changed')
        row = data[meta['id']]
        timing = {f['source_pts']: f['timestamp_sec'] for f in index['frames']}
        expected = [f for f in manifest['frames'] if f['video_id'] == meta['id']]
        if [f['source_pts'] for f in expected] != row['source_pts']:
            raise ValueError('Human source feature order changed')
        if any(abs(timing[f['source_pts']]-f['timestamp_sec']) > 1e-8 for f in expected):
            raise ValueError('Human source timestamps changed')
    return import_targets(data, manifest, snapshot)


def fit_head(train, values, c, regularization):
    x = []; y = []; sources = []; families = {0: set(), 1: set()}
    for row in train:
        labels = row['coarse'][:, c].numpy(); known = labels >= 0
        x.append(values[row['video_id']][known]); y.extend(labels[known])
        sources.extend([row['video_id']]*int(known.sum()))
        for value in (0, 1):
            if (labels == value).any(): families[value].add(row['group_id'])
    y = np.asarray(y); sources = np.asarray(sources)
    if any((y == value).sum() < 3 for value in (0, 1)):
        return None
    weights = np.zeros(len(y))
    for value in (0, 1):
        ids = np.unique(sources[y == value])
        for video in ids:
            mask = (y == value) & (sources == video)
            weights[mask] = len(y)/(2*len(ids)*mask.sum())
    model = LogisticRegression(C=regularization, solver='liblinear', max_iter=3000, tol=1e-5, random_state=42)
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        model.fit(np.concatenate(x), y, sample_weight=weights)
    return {'weight': torch.tensor(model.coef_[0], dtype=torch.float32), 'bias': float(model.intercept_[0]),
            'training_families': {str(v): len(families[v]) for v in (0, 1)}}


def select(data, folds, classes):
    pooled = {stable_hash(c): [[], []] for c in GRID}
    for fold in folds:
        train = [data[v] for v in fold['train']]; validation = [data[v] for v in fold['validation']]
        y = np.concatenate([r['coarse'].numpy()[:, classes] for r in validation])
        for mode in ('appearance', 'motion'):
            values, _ = linear.representation(train, train+validation, mode)
            for c in (.1, 1., 10., 100.):
                heads = [fit_head(train, values, k, c) for k in classes]
                p = np.concatenate([np.stack([base.probabilities(h, values[r['video_id']]) for h in heads], 1) for r in validation])
                destination = pooled[stable_hash({'mode': mode, 'c': c})]
                destination[0].append(y); destination[1].append(p)
    choices = []
    for k in range(len(classes)):
        candidates = []
        for candidate in GRID:
            yy, pp = pooled[stable_hash(candidate)]; y = np.concatenate(yy)[:, k]; p = np.concatenate(pp)[:, k]
            threshold = base.threshold(y, p)
            candidates.append({'candidate': candidate, 'threshold': threshold, 'metrics': base.statistics(y, p, threshold)})
        choices.append(max(candidates, key=lambda r: (r['metrics']['f1'], r['metrics']['recall'], r['metrics']['precision'])))
    return choices


def train_selected(data, train_ids, test_ids, choices, classes):
    train = [data[v] for v in train_ids]; test = [data[v] for v in test_ids]
    banks = {}; heads = [{'head': None} for _ in base.TAXONOMY]; predictions = []
    for c, choice in zip(classes, choices):
        candidate = choice['candidate']; mode = candidate['mode']
        if mode not in banks: banks[mode] = linear.representation(train, train+test, mode)
        values, _ = banks[mode]; head = fit_head(train, values, c, candidate['c'])
        heads[c] = {'bank': mode, 'head': head, 'threshold': choice['threshold']}
        predictions.append(np.concatenate([base.probabilities(head, values[r['video_id']]) for r in test]))
    return np.stack(predictions, 1), {'banks': {k: v[1] for k, v in banks.items()}, 'heads': heads,
                                    'train_ids': sorted(train_ids), 'taxonomy': list(base.TAXONOMY)}


def prepare(root, manifest_path, snapshot_path, output):
    root, manifest_path, snapshot_path, output = map(Path, (root, manifest_path, snapshot_path, output))
    manifest = read_json(manifest_path); snapshot = read_json(snapshot_path)
    data, audit = load_inputs(root, manifest, snapshot)
    parent = root/'temporal-operations-stage-v1c/protocol.json'; old = read_json(parent)
    if set(data) != set(old['development_ids']) or manifest['reserved_ids'] != old['reserved_ids']:
        raise ValueError('Human partition differs from frozen development partition')
    classes = [i for i, name in enumerate(base.TAXONOMY) if name in audit['counts']]
    if not classes: raise ValueError('No supported human action targets')
    base.dino_probe.validate_folds(data, old['folds'], data)
    base.dino_probe.validate_folds(data, old['final_inner'], data)
    plan = {k: old[k] for k in ('development_ids', 'reserved_ids', 'folds', 'final_inner')}
    plan.update(version=VERSION, code_sha256=code_hash(), root=str(root.resolve()),
                manifest_sha256=file_hash(manifest_path), snapshot_sha256=file_hash(snapshot_path), revision=snapshot['revision'],
                parent_sha256=file_hash(parent), inputs_sha256=file_hash(root/'dino-source-actions-v1/inputs.json'),
                control_sha256=file_hash(root/'local-state-stage-v1/state_oof.pt'), classes=classes, grid=GRID,
                taxonomy=list(base.TAXONOMY), audit=audit,
                selection='train-only scaling and fitting; inner family OOF max F1 at P>=.8; no extrapolation; no old assistant targets',
                promotion='outer P>=.8,R>=.5,F1>=.8,coverage>=.9,above paired control; >=2 positive and2 negative labeled families',
                independent_test=False, production_ready=False)
    plan['protocol_sha256'] = stable_hash(plan)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(manifest_path, output/'manifest.json'); shutil.copyfile(snapshot_path, output/'human-review.json')
    atomic_json(output/'protocol.json', plan)
    print(json.dumps({'prepared': str(output), 'revision': plan['revision'], 'audit': audit}), flush=True)


def run(output):
    output = Path(output); started = time.monotonic(); plan = read_json(output/'protocol.json'); root = Path(plan['root'])
    if (plan['code_sha256'] != code_hash() or plan['protocol_sha256'] != stable_hash({k: v for k, v in plan.items() if k != 'protocol_sha256'}) or
            (output/'report.json').exists() or (output/'final.pt').exists()):
        raise ValueError('Changed or completed human experiment')
    paths = {'manifest_sha256': output/'manifest.json', 'snapshot_sha256': output/'human-review.json',
             'parent_sha256': root/'temporal-operations-stage-v1c/protocol.json',
             'inputs_sha256': root/'dino-source-actions-v1/inputs.json', 'control_sha256': root/'local-state-stage-v1/state_oof.pt'}
    if any(file_hash(path) != plan[key] for key, path in paths.items()): raise ValueError('Human training inputs changed')
    data, audit = load_inputs(root, read_json(output/'manifest.json'), read_json(output/'human-review.json'))
    if audit != plan['audit']: raise ValueError('Human target audit changed')
    base.dino_probe.validate_folds(data, plan['folds'], data)
    base.dino_probe.validate_folds(data, plan['final_inner'], data)
    control = {r['video_id']: r for r in safe_torch_load(paths['control_sha256'])['frames']['False']}
    classes = plan['classes']; targets = []; decisions = []; previous = []; folds = []
    for n, fold in enumerate(plan['folds']):
        choices = select(data, fold['inner'], classes)
        p, _ = train_selected(data, fold['train'], fold['validation'], choices, classes)
        y = np.concatenate([data[v]['coarse'].numpy()[:, classes] for v in fold['validation']])
        d = np.where(np.isfinite(p), p >= np.asarray([c['threshold'] for c in choices]), np.nan)
        old = []
        for video in fold['validation']:
            row = control[video]
            if row['actions'].shape[0] != len(data[video]['source_pts']): raise ValueError('Control frame count changed')
            values = row['actions'][:, classes].numpy().copy()
            values[:, ~row['actions_supported'][classes].numpy()] = np.nan
            old.append(values)
        targets.append(y); decisions.append(d); previous.append(np.concatenate(old))
        record = {'fold': n, 'sources': fold['validation'], 'counts': [len(data[v]['source_pts']) for v in fold['validation']], 'choices': choices}
        folds.append(record); atomic_json(output/f'fold-{n}.json', record)
        np.savez_compressed(output/f'fold-{n}.npz', targets=y, predictions=p, decisions=d, control=previous[-1])
        print(json.dumps({'fold': n, 'elapsed_seconds': time.monotonic()-started,
                          'f1': {base.TAXONOMY[c]: base.statistics(y[:, i], d[:, i], .5)['f1'] for i, c in enumerate(classes)}}), flush=True)
    y = np.concatenate(targets); d = np.concatenate(decisions); old = np.concatenate(previous); metrics = {}
    for i, c in enumerate(classes):
        m = base.statistics(y[:, i], d[:, i], .5); b = base.statistics(y[:, i], old[:, i], .5)
        families = {str(value): len({r['group_id'] for r in data.values() if (r['coarse'][:, c] == value).any()}) for value in (0, 1)}
        promoted = (m['precision'] >= .8 and m['recall'] >= .5 and m['f1'] >= .8 and m['prediction_coverage'] >= .9
                    and m['f1'] > b['f1'] and min(families.values()) >= 2)
        metrics[base.TAXONOMY[c]] = {'human_head': m, 'paired_control': b, 'labeled_families': families, 'promoted': promoted}
    choices = select(data, plan['final_inner'], classes)
    _, state = train_selected(data, plan['development_ids'], plan['development_ids'], choices, classes)
    state.update(version=VERSION, protocol_sha256=plan['protocol_sha256'], snapshot_sha256=plan['snapshot_sha256'])
    atomic_checkpoint(output/'final.pt', state)
    safe_torch_load(output/'final.pt')
    report = {'version': VERSION, 'protocol_sha256': plan['protocol_sha256'], 'snapshot_sha256': plan['snapshot_sha256'],
              'revision': plan['revision'], 'audit': audit, 'classes': metrics, 'folds': folds, 'final_choices': choices,
              'trained_heads': [base.TAXONOMY[c] for c in classes if state['heads'][c]['head'] is not None],
              'promoted': [name for name, m in metrics.items() if m['promoted']], 'final_sha256': file_hash(output/'final.pt'),
              'elapsed_seconds': time.monotonic()-started, 'independent_test': False, 'production_ready': False,
              'deployed': False, 'clip_model_unchanged': True}
    atomic_json(output/'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('folds', 'final_choices')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    for name in ('root', 'manifest', 'snapshot', 'output'): p.add_argument('--'+name, type=Path, required=True)
    p = sub.add_parser('run'); p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); torch.set_num_threads(4)
    if args.command == 'prepare': prepare(args.root, args.manifest, args.snapshot, args.output)
    else: run(args.output)
