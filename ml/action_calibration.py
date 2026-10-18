"""Nested temporal calibration of existing source action heads.

All frame heads must already exist with the exact train identity. No completed
training experiment is modified and no held-family target selects its threshold.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch

from ml import action_kernel as base, object_state_local as local
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256, safe_torch_load
from ml.video_baseline import atomic_json

VERSION='source-action-temporal-calibration-v1'
MODES=('identity','median3','mean3','max3')


def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'base':base.code_hash(),'local':local.code_hash()})


def filtered(scores,times,mode):
    scores=np.asarray(scores,dtype=float);times=np.asarray(times,dtype=float)
    if scores.ndim!=1 or times.shape!=scores.shape or not np.isfinite(times).all() or (np.diff(times)<=0).any():raise ValueError('Invalid temporal action timeline')
    if mode not in MODES:raise ValueError('Unknown temporal filter')
    if mode=='identity':return scores.copy()
    result=scores.copy()
    for n in range(len(scores)):
        a=max(0,n-1);b=min(len(scores),n+2)
        if not np.isfinite(scores[a:b]).all() or (np.diff(times[a:b])>.75).any():continue
        values=scores[a:b];result[n]={'median3':np.median,'mean3':np.mean,'max3':np.max}[mode](values)
    return result


def prepare(parent,output):
    parent,output=Path(parent),Path(output);old=json.loads((parent/'protocol.json').read_text());source=parent.parent/'local-state-stage-v1'
    plan={k:old[k] for k in ('folds','final_inner','development_ids','reserved_ids','taxonomy')}
    plan.update(version=VERSION,code_sha256=code_hash(),parent=str(parent.resolve()),input_marker_sha256=file_sha256(parent/'inputs.json'),
                source=str(source.resolve()),source_protocol_sha256=file_sha256(source/'protocol.json'),modes=MODES,
                selection='inner-only max F1 with precision>=.8, same exact-frame known targets; unsupported classes count as misses',
                promotion='per-class outer P>=.8,R>=.5,F1>=.8 and above unchanged control; no clip verdict changes',
                independent_test=False,human_approved=False,production_ready=False)
    fits={};protocol=json.loads((source/'protocol.json').read_text())['protocol_sha256']
    for outer in [*plan['folds'],{'inner':plan['final_inner']}]:
        for fold in outer.get('inner',[]):
            identity={'protocol':protocol,'kind':'roi_states','ids':sorted(fold['train']),'hard':False};name=stable_hash(identity)+'.pt';path=source/'fits'/name
            if not path.exists() or safe_torch_load(path)['identity']!=identity:raise ValueError('Exact calibration fit missing')
            fits[name]=file_sha256(path)
    plan['fits']=fits;plan['protocol_sha256']=stable_hash(plan);output.mkdir(parents=True,exist_ok=False);atomic_json(output/'protocol.json',plan)


def choose(data,rows):
    choices=[]
    for c in range(len(base.TAXONOMY)):
        candidates=[]
        for mode in MODES:
            yy=[];pp=[]
            for row in rows:
                video=row['video_id']; yy.extend(data[video]['coarse'][:,c].numpy())
                score=row['actions'][:,c].numpy() if bool(row['actions_supported'][c]) else np.full(len(data[video]['times']),np.nan)
                pp.extend(filtered(score,data[video]['times'],mode))
            y=np.asarray(yy);p=np.asarray(pp);t=base.threshold(y,p);m=base.statistics(y,p,t)
            candidates.append({'mode':mode,'threshold':t,'metrics':m})
        choices.append(max(candidates,key=lambda v:(v['metrics']['f1'],v['metrics']['recall'],v['metrics']['precision'])))
    return choices


def decisions(data,rows,choices):
    result=[]
    for row in rows:
        video=row['video_id'];parts=[]
        for c,choice in enumerate(choices):
            score=row['actions'][:,c].numpy() if bool(row['actions_supported'][c]) else np.full(len(data[video]['times']),np.nan)
            p=filtered(score,data[video]['times'],choice['mode']);parts.append(np.where(np.isfinite(p),p>=choice['threshold'],np.nan))
        result.append(np.stack(parts,1))
    return np.concatenate(result)


def run(output):
    output=Path(output);plan=json.loads((output/'protocol.json').read_text());parent=Path(plan['parent']);source=Path(plan['source'])
    if plan['code_sha256']!=code_hash() or plan['protocol_sha256']!=stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'}):raise ValueError('Calibration code changed')
    if (output/'report.json').exists():raise ValueError('Completed calibration')
    if file_sha256(parent/'inputs.json')!=plan['input_marker_sha256'] or file_sha256(source/'protocol.json')!=plan['source_protocol_sha256']:raise ValueError('Calibration inputs changed')
    marker=json.loads((parent/'inputs.json').read_text());data={e['video_id']:safe_torch_load(parent/'inputs'/(e['video_id']+'.pt'),expected_sha256=e['sha256']) for e in marker['entries']}
    experiment=local.Experiment(source,'cpu');torch.set_num_threads(4)
    for video in data:
        if list(experiment.rows[video]['source_pts'])!=data[video]['source_pts']:raise ValueError('Calibration PTS mismatch')
    protocol=experiment.plan['protocol_sha256'];memo={}
    def observations(folds):
        rows=[]
        for fold in folds:
            identity={'protocol':protocol,'kind':'roi_states','ids':sorted(fold['train']),'hard':False};name=stable_hash(identity)+'.pt';path=source/'fits'/name
            if file_sha256(path)!=plan['fits'][name]:raise ValueError('Calibration fit changed')
            key=(name,tuple(fold['validation']))
            if key not in memo:memo[key]=experiment.observations(path,fold['validation'])
            rows.extend(memo[key])
            # Keep only small predictions; spatial maps remain memory mapped.
            experiment.memo.clear();experiment.context.memo.clear()
        return rows
    controls={r['video_id']:r for r in safe_torch_load(source/'state_oof.pt')['frames']['False']}
    targets=[];predictions=[];old=[];records=[]
    for n,fold in enumerate(plan['folds']):
        choices=choose(data,observations(fold['inner']));rows=[controls[v] for v in fold['validation']]
        y=np.concatenate([data[v]['coarse'].numpy() for v in fold['validation']]);d=decisions(data,rows,choices)
        p=np.concatenate([np.where(r['actions_supported'][:len(base.TAXONOMY)].numpy()[None],r['actions'][:,:len(base.TAXONOMY)].numpy(),np.nan) for r in rows])
        targets.append(y);predictions.append(d);old.append(p);records.append({'fold':n,'choices':choices,'sources':fold['validation']})
        atomic_json(output/f'fold-{n}.json',records[-1]);np.savez_compressed(output/f'fold-{n}.npz',targets=y,decisions=d,control=p)
        print(json.dumps({'calibration_fold':n,'f1':{name:base.statistics(y[:,c],d[:,c],.5)['f1'] for c,name in enumerate(base.DYNAMIC)}}),flush=True)
    y=np.concatenate(targets);p=np.concatenate(predictions);old=np.concatenate(old);classes={}
    for c,name in enumerate(base.TAXONOMY):
        m=base.statistics(y[:,c],p[:,c],.5);b=base.statistics(y[:,c],old[:,c],.5)
        classes[name]={'candidate':m,'control':b,'promoted':bool(m['precision']>=.8 and m['recall']>=.5 and m['f1']>=.8 and m['f1']>b['f1'])}
    choices=choose(data,observations(plan['final_inner']))
    report={'version':VERSION,'protocol_sha256':plan['protocol_sha256'],'classes':classes,'choices':choices,
            'promoted':[n for n in base.TAXONOMY if classes[n]['promoted']], 'folds':records,'production_ready':False,'independent_test':False}
    atomic_json(output/'report.json',report);print(json.dumps({'calibration_promoted':report['promoted']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--parent',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('run');a.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.command=='prepare':prepare(a.parent,a.output)
    else:run(a.output)
