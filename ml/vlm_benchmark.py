"""Frozen zero-shot local visual-operation probe on uniformly sampled sources."""
import argparse
import json
from pathlib import Path
import time

from ml import vlm_operations as model
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256, safe_torch_load
from ml.video_baseline import atomic_json


def run(root, output):
    root, output = Path(root), Path(output)
    parent = json.loads((root/'temporal-operations-stage-v1c/protocol.json').read_text())
    sources = Path(json.loads((root/'prepared/readiness.json').read_text())['source_root'])
    output.mkdir(parents=True, exist_ok=False)
    plan = {'version': model.VERSION, 'code_sha256': model.code_hash(),
            'model_sha256': model.MODEL_SHA256, 'projector_sha256': model.PROJECTOR_SHA256,
            'classes': list(model.CLASSES), 'sample_policy': '16 uniformly spaced existing 2fps PTS per development source; full frame',
            'development_ids': parent['development_ids'], 'reserved_ids': parent['reserved_ids'],
            'parent_protocol_sha256': parent['protocol_sha256'], 'new_training': False,
            'threshold_tuning': False, 'independent_test': False, 'normative_status': 'unknown'}
    plan['protocol_sha256'] = stable_hash(plan)
    atomic_json(output/'protocol.json', plan)
    results = []
    for video in plan['development_ids']:
        cache = root/'temporal-operations-stage-v1c/inputs'/(video+'.pt')
        if file_sha256(cache) != parent['inputs'][video]['sha256']:
            raise ValueError('Weak source/target cache changed')
        entry = safe_torch_load(cache)
        index = json.loads((root/'prepared/indices'/(video+'.json')).read_text())
        if index['source_sha256'] != entry['source_sha256']:
            raise ValueError('Foreign visual source')
        count = min(16, len(entry['source_pts']))
        chosen = [round(n*(len(entry['source_pts'])-1)/(count-1)) for n in range(count)]
        points = [entry['source_pts'][n] for n in chosen]
        started = time.monotonic()
        images = model.source_images(sources, index, points)
        predictions = []
        for n in range(0, len(images), 8):
            predictions.extend(model.classify(images[n:n+8])['actions'])
        rows = []
        for n, action in zip(chosen, predictions):
            target = entry['fine'][n]
            names = ['other' if c == 0 else parent['taxonomy'][c] for c in range(len(target)) if target[c] > 0]
            rows.append({'source_pts': entry['source_pts'][n], 'timestamp_sec': entry['times'][n],
                         'prediction': action, 'weak_targets': names})
        result = {'video_id': video, 'source_sha256': entry['source_sha256'], 'rows': rows,
                  'elapsed_seconds': time.monotonic()-started}
        atomic_json(output/(video+'.json'), result)
        results.append(result)
        known = [r for r in rows if r['weak_targets']]
        print(json.dumps({'video': video, 'known': len(known), 'matched': sum(r['prediction'] in r['weak_targets'] for r in known),
                          'elapsed_seconds': result['elapsed_seconds']}), flush=True)
    known = [r for v in results for r in v['rows'] if r['weak_targets']]
    by_class = {}
    for name in model.CLASSES:
        tp = sum(r['prediction'] == name and name in r['weak_targets'] for r in known)
        fp = sum(r['prediction'] == name and name not in r['weak_targets'] for r in known)
        fn = sum(r['prediction'] != name and name in r['weak_targets'] for r in known)
        by_class[name] = {'tp': tp, 'fp': fp, 'fn': fn, 'f1': 2*tp/max(1, 2*tp+fp+fn)}
    report = {'protocol_sha256': plan['protocol_sha256'], 'videos': len(results),
              'sampled_frames': sum(len(v['rows']) for v in results), 'known_weak_frames': len(known),
              'weak_set_accuracy': sum(r['prediction'] in r['weak_targets'] for r in known)/max(1, len(known)),
              'weak_macro_f1_all_classes': sum(x['f1'] for x in by_class.values())/len(by_class),
              'by_class': by_class, 'mean_elapsed_seconds': sum(v['elapsed_seconds'] for v in results)/len(results),
              'max_elapsed_seconds': max(v['elapsed_seconds'] for v in results),
              'binary_accuracy_measured': False, 'independent_test': False,
              'outside_annotated_operations_unknown': True, 'candidate_promoted': False}
    atomic_json(output/'report.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.root, args.output)
