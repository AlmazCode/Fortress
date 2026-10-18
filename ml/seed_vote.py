"""Fixed majority vote of existing grouped out-of-fold seed controls.

Every member keeps its original training-only calibrated threshold. No new
threshold, weight or method is selected using outer labels. This probe does not
make a deployment package and does not alter any completed experiment.
"""
import argparse
import json
from pathlib import Path

from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256
from ml.video_baseline import atomic_json,metrics

SEEDS=('42','137','2026')


def majority(rows_by_seed):
    if set(rows_by_seed)!=set(SEEDS):raise ValueError('Three fixed control seeds required')
    mappings={seed:{r['video_id']:r for r in rows} for seed,rows in rows_by_seed.items()}
    ids=set(mappings[SEEDS[0]])
    if any(len(mappings[s])!=len(rows_by_seed[s]) or set(mappings[s])!=ids for s in SEEDS):
        raise ValueError('Incomplete or duplicate OOF source coverage')
    result=[]
    for video in sorted(ids):
        members=[mappings[s][video] for s in SEEDS]
        if len({(r['truth'],r['fold']) for r in members})!=1:raise ValueError('Mixed OOF identities')
        votes=[]
        for row in members:
            if (type(row['score']) not in (float,int) or not 0<=row['score']<=1
                    or type(row['threshold']) not in (float,int) or not 0<=row['threshold']<=1):
                raise ValueError('Invalid bound control decision')
            votes.append(row['score']>=row['threshold'])
        result.append({'video_id':video,'truth':members[0]['truth'],'fold':members[0]['fold'],
                       'score':sum(votes)/3,'threshold':.5,'positive_votes':sum(votes)})
    return result


def run(root,output):
    root,output=Path(root),Path(output)
    source=root/'object-stage-v2/cv_report.json'
    controls=json.loads(source.read_text())
    frozen=json.loads((root/'temporal-operations-stage-v1c/protocol.json').read_text())
    output.mkdir(parents=True,exist_ok=False)
    plan={'version':'fixed-three-seed-majority-v1','code_sha256':file_sha256(Path(__file__)),
          'control_report_sha256':file_sha256(source),'seed_order':list(SEEDS),'arm':'uniform_gru',
          'threshold_policy':'each original member inner-calibrated threshold, majority>=2/3',
          'development_ids':frozen['development_ids'],'reserved_ids':frozen['reserved_ids'],
          'new_training':False,'outer_tuning':False,'independent_test':False,
          'promotion':'accuracy,balanced_accuracy,macro_f1 all strictly above frozen three-seed mean'}
    plan['protocol_sha256']=stable_hash(plan);atomic_json(output/'protocol.json',plan)
    rows=majority(controls['oof']['uniform_gru'])
    if {r['video_id'] for r in rows}!=set(plan['development_ids']):raise ValueError('Vote development coverage')
    for n,fold in enumerate(controls['folds']):
        if set(fold['train'])&set(fold['validation']):raise ValueError('Control partition overlap')
        if {r['video_id'] for r in rows if r['fold']==n}!=set(fold['validation']):raise ValueError('Foreign outer vote')
    quality=metrics(rows,.5)
    promoted=all(quality[k]>frozen['control'][k] for k in ('accuracy','balanced_accuracy','macro_f1'))
    report={'protocol_sha256':plan['protocol_sha256'],'quality':quality,'control':frozen['control'],
            'predictions':rows,'promotion_gate_passed':promoted,'deployed':False,'production_ready':False,'independent_test':False}
    atomic_json(output/'report.json',report)
    print(json.dumps({'quality':quality,'promotion_gate_passed':promoted}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root,a.output)
