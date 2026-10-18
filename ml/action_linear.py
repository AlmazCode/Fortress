"""Linear exact-frame action readout with nested family selection.

Uses the existing DINO frame cache. The failed kernel experiment is preserved;
this protocol compares both candidates against control predictions on identical
source PTS and targets, rather than comparing different annotation revisions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import warnings

import numpy as np
import torch
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from ml import action_kernel as base
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256, safe_torch_load
from ml.video_baseline import atomic_json, atomic_checkpoint

VERSION = 'source-actions-linear-v1'
GRID = [{'mode': mode, 'c': c} for mode in ('appearance', 'motion') for c in (.01, .1, 1., 10.)]


def code_hash():
    return stable_hash({'own': hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'base': base.code_hash()})


def prepare(parent, output):
    parent, output = Path(parent), Path(output)
    old = json.loads((parent/'protocol.json').read_text())
    marker = json.loads((parent/'inputs.json').read_text())
    if old['code_sha256'] != base.code_hash():
        raise ValueError('Action source code changed')
    control = parent.parent/'local-state-stage-v1/state_oof.pt'
    plan = {k: old[k] for k in ('development_ids', 'reserved_ids', 'folds', 'final_inner', 'taxonomy', 'promotion', 'source_root', 'source_files', 'weights', 'weights_sha256')}
    plan.update(version=VERSION, code_sha256=code_hash(), parent=str(parent.resolve()),
                parent_sha256=file_sha256(parent/'protocol.json'), inputs_sha256=file_sha256(parent/'inputs.json'),
                control=str(control.resolve()), control_sha256=file_sha256(control), grid=GRID,
                selection='inner-only F1 at precision>=.8; source/class balanced; family support>=2 per target',
                comparison='same exact frame targets and held-family control predictions, unsupported targets count as misses',
                kernel_folds={str(i): file_sha256(parent/f'fold-{i}.npz') for i in range(4)},
                independent_test=False, human_approved=False, production_ready=False)
    plan['protocol_sha256'] = stable_hash(plan)
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output/'protocol.json', plan)
    atomic_json(parent/'failed.json', {'reason': 'aggregate control report used a different target revision for four classes; coverage assertion stopped completion',
                                      'folds_preserved': True, 'deployed': False})


def representation(train, rows, mode):
    raw = {r['video_id']: base.frame_features(r['features'], mode) for r in rows}
    x = torch.cat([raw[r['video_id']] for r in train])
    mean = x.mean(0); scale = x.std(0, unbiased=False).clamp_min(.01)
    # Scale by sqrt dimension so regularization is comparable across modes.
    scale = scale * np.sqrt(x.shape[1])
    return {k: ((v-mean)/scale).numpy().astype(np.float64) for k,v in raw.items()}, {'mean': mean, 'scale': scale, 'mode': mode}


def fit_class(train, values, c, regularization):
    x=[]; y=[]; sources=[]; families={0:set(),1:set()}
    for r in train:
        t=r['coarse'][:,c].numpy(); known=t>=0
        for v in (0,1):
            if (t==v).any(): families[v].add(r['group_id'])
        x.append(values[r['video_id']][known]); y.extend(t[known]); sources.extend([r['video_id']]*int(known.sum()))
    y=np.asarray(y); sources=np.asarray(sources)
    if any(len(families[v])<2 or (y==v).sum()<3 for v in (0,1)): return None
    weights=np.zeros(len(y))
    for v in (0,1):
        ids=np.unique(sources[y==v])
        for video in ids:
            mask=(y==v)&(sources==video); weights[mask]=len(y)/(2*len(ids)*mask.sum())
    model=LogisticRegression(C=regularization,solver='liblinear',max_iter=3000,tol=1e-5,random_state=42)
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        model.fit(np.concatenate(x),y,sample_weight=weights)
    return {'weight':torch.tensor(model.coef_[0],dtype=torch.float32),'bias':float(model.intercept_[0])}


def select(data, folds):
    pooled={stable_hash(c):[[],[]] for c in GRID}
    for fold in folds:
        train=[data[v] for v in fold['train']]; validation=[data[v] for v in fold['validation']]
        for mode in ('appearance','motion'):
            values,_=representation(train,train+validation,mode)
            y=np.concatenate([r['coarse'].numpy() for r in validation])
            for c in (.01,.1,1.,10.):
                heads=[fit_class(train,values,k,c) for k in range(len(base.TAXONOMY))]
                p=np.concatenate([np.stack([base.probabilities(h,values[r['video_id']]) for h in heads],1) for r in validation])
                destination=pooled[stable_hash({'mode':mode,'c':c})]; destination[0].append(y); destination[1].append(p)
    choices=[]
    for k in range(len(base.TAXONOMY)):
        candidates=[]
        for candidate in GRID:
            yy,pp=pooled[stable_hash(candidate)]; y=np.concatenate(yy)[:,k]; p=np.concatenate(pp)[:,k]
            t=base.threshold(y,p); m=base.statistics(y,p,t)
            candidates.append({'candidate':candidate,'threshold':t,'metrics':m})
        choices.append(max(candidates,key=lambda r:(r['metrics']['f1'],r['metrics']['recall'],r['metrics']['precision'])))
    return choices


def train_selected(data, train_ids, test_ids, choices):
    train=[data[v] for v in train_ids]; test=[data[v] for v in test_ids]; banks={}; heads=[]; predictions=[]
    for k, choice in enumerate(choices):
        candidate=choice['candidate']; mode=candidate['mode']
        if mode not in banks: banks[mode]=representation(train,train+test,mode)
        values,_=banks[mode]; head=fit_class(train,values,k,candidate['c'])
        predictions.append(np.concatenate([base.probabilities(head,values[r['video_id']]) for r in test]))
        heads.append({'bank':mode,'head':head,'threshold':choice['threshold']})
    return np.stack(predictions,1), {'banks':{k:v[1] for k,v in banks.items()},'heads':heads,'train_ids':sorted(train_ids)}


def run(output):
    output=Path(output); plan=json.loads((output/'protocol.json').read_text()); parent=Path(plan['parent'])
    if plan['code_sha256']!=code_hash() or plan['protocol_sha256']!=stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'}): raise ValueError('Linear protocol changed')
    if (output/'report.json').exists(): raise ValueError('Completed experiment')
    if file_sha256(parent/'protocol.json')!=plan['parent_sha256'] or file_sha256(parent/'inputs.json')!=plan['inputs_sha256']: raise ValueError('Action inputs changed')
    marker=json.loads((parent/'inputs.json').read_text()); data={e['video_id']:safe_torch_load(parent/'inputs'/(e['video_id']+'.pt'),expected_sha256=e['sha256']) for e in marker['entries']}
    base.dino_probe.validate_folds(data,plan['folds'],data); base.dino_probe.validate_folds(data,plan['final_inner'],data)
    controls=safe_torch_load(plan['control'],expected_sha256=plan['control_sha256'])['frames']['False']
    control={r['video_id']:r for r in controls}; targets=[]; decisions=[]; previous=[]; kernel=[]; records=[]
    for n,fold in enumerate(plan['folds']):
        choices=select(data,fold['inner']); p,_=train_selected(data,fold['train'],fold['validation'],choices)
        y=np.concatenate([data[v]['coarse'].numpy() for v in fold['validation']]); d=np.where(np.isfinite(p),p>=np.asarray([c['threshold'] for c in choices]),np.nan)
        old=[]
        for video in fold['validation']:
            row=control[video]
            if row['actions'].shape[0]!=len(data[video]['source_pts']): raise ValueError('Control PTS length changed')
            score=row['actions'][:,:len(base.TAXONOMY)].numpy(); score[:,~row['actions_supported'][:len(base.TAXONOMY)].numpy()]=np.nan
            old.append(score)
        if file_sha256(parent/f'fold-{n}.npz')!=plan['kernel_folds'][str(n)]: raise ValueError('Kernel predictions changed')
        k=np.load(parent/f'fold-{n}.npz');
        if not np.array_equal(y,k['targets']): raise ValueError('Kernel source order changed')
        targets.append(y); decisions.append(d); previous.append(np.concatenate(old)); kernel.append(k['decisions'])
        record={'fold':n,'choices':choices,'sources':fold['validation'],'counts':[len(data[v]['features']) for v in fold['validation']]}; records.append(record)
        atomic_json(output/f'fold-{n}.json',record); np.savez_compressed(output/f'fold-{n}.npz',targets=y,decisions=d,predictions=p,control=previous[-1])
        print(json.dumps({'linear_fold':n,'f1':{name:base.statistics(y[:,c],d[:,c],.5)['f1'] for c,name in enumerate(base.DYNAMIC)}}),flush=True)
    y=np.concatenate(targets); d=np.concatenate(decisions); old=np.concatenate(previous); k=np.concatenate(kernel); classes={}
    for c,name in enumerate(base.TAXONOMY):
        m=base.statistics(y[:,c],d[:,c],.5); b=base.statistics(y[:,c],old[:,c],.5); km=base.statistics(y[:,c],k[:,c],.5)
        gate=lambda v:bool(v['precision']>=.8 and v['recall']>=.5 and v['f1']>=.8 and v['f1']>b['f1'])
        classes[name]={'linear':m,'kernel':km,'control':b,'promoted_linear':gate(m),'promoted_kernel':gate(km)}
    choices=select(data,plan['final_inner']); _,state=train_selected(data,plan['development_ids'],plan['development_ids'],choices)
    state.update(version=VERSION,protocol_sha256=plan['protocol_sha256'],taxonomy=list(base.TAXONOMY)); atomic_checkpoint(output/'final.pt',state)
    report={'version':VERSION,'protocol_sha256':plan['protocol_sha256'],'classes':classes,'folds':records,
            'dynamic_macro_f1':float(np.mean([classes[n]['linear']['f1'] for n in base.DYNAMIC])),
            'promoted_linear':[n for n in base.TAXONOMY if classes[n]['promoted_linear']],
            'promoted_kernel':[n for n in base.TAXONOMY if classes[n]['promoted_kernel']],
            'final_sha256':file_sha256(output/'final.pt'),'independent_test':False,'production_ready':False}
    atomic_json(output/'report.json',report);print(json.dumps({k:v for k,v in report.items() if k not in ('classes','folds')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('prepare');p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=subs.add_parser('run');p.add_argument('--output',type=Path,required=True);args=parser.parse_args();torch.set_num_threads(4)
    if args.command=='prepare':prepare(args.parent,args.output)
    else:run(args.output)
