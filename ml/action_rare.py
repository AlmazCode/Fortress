"""Explicit few-family experiment for bag and safe actions on existing frames.

One positive training family is allowed; this corrects unavailable inner heads,
but does not relax held-family promotion or pretend to validate rare classes.
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
from ml import action_linear as linear, action_kernel as base
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint

VERSION='few-family-source-actions-v1'
CLASSES=(4,9,10)
GRID=[{'mode':mode,'c':c} for mode in ('appearance','motion') for c in (.1,1.,10.,100.)]


def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),'linear':linear.code_hash()})


def fit(train,values,c,regularization):
    x=[];y=[];sources=[];families={0:set(),1:set()}
    for row in train:
        t=row['coarse'][:,c].numpy();known=t>=0
        for v in (0,1):
            if (t==v).any():families[v].add(row['group_id'])
        x.append(values[row['video_id']][known]);y.extend(t[known]);sources.extend([row['video_id']]*int(known.sum()))
    y=np.asarray(y);sources=np.asarray(sources)
    if len(families[1])<1 or len(families[0])<2 or any((y==v).sum()<5 for v in (0,1)):return None
    weights=np.zeros(len(y))
    for v in (0,1):
        ids=np.unique(sources[y==v])
        for video in ids:
            mask=(y==v)&(sources==video);weights[mask]=len(y)/(2*len(ids)*mask.sum())
    model=LogisticRegression(C=regularization,solver='liblinear',max_iter=3000,tol=1e-5,random_state=42)
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning);model.fit(np.concatenate(x),y,sample_weight=weights)
    return {'weight':torch.tensor(model.coef_[0],dtype=torch.float32),'bias':float(model.intercept_[0]),
            'positive_training_families':len(families[1]),'negative_training_families':len(families[0])}


def select(data,folds):
    pooled={stable_hash(c):[[],[]] for c in GRID}
    for fold in folds:
        train=[data[v] for v in fold['train']];test=[data[v] for v in fold['validation']]
        y=np.concatenate([r['coarse'].numpy()[:,CLASSES] for r in test])
        for mode in ('appearance','motion'):
            values,_=linear.representation(train,train+test,mode)
            for c in (.1,1.,10.,100.):
                heads=[fit(train,values,k,c) for k in CLASSES]
                p=np.concatenate([np.stack([base.probabilities(h,values[r['video_id']]) for h in heads],1) for r in test])
                destination=pooled[stable_hash({'mode':mode,'c':c})];destination[0].append(y);destination[1].append(p)
    choices=[]
    for c in range(len(CLASSES)):
        candidates=[]
        for candidate in GRID:
            yy,pp=pooled[stable_hash(candidate)];y=np.concatenate(yy)[:,c];p=np.concatenate(pp)[:,c];t=base.threshold(y,p)
            candidates.append({'candidate':candidate,'threshold':t,'metrics':base.statistics(y,p,t)})
        choices.append(max(candidates,key=lambda r:(r['metrics']['f1'],r['metrics']['recall'],r['metrics']['precision'])))
    return choices


def train_selected(data,train_ids,test_ids,choices):
    train=[data[v] for v in train_ids];test=[data[v] for v in test_ids];banks={};heads=[{'head':None} for _ in base.TAXONOMY];pred=[]
    for c,choice in zip(CLASSES,choices):
        candidate=choice['candidate'];mode=candidate['mode']
        if mode not in banks:banks[mode]=linear.representation(train,train+test,mode)
        values,_=banks[mode];head=fit(train,values,c,candidate['c'])
        heads[c]={'bank':mode,'head':head,'threshold':choice['threshold']};pred.append(np.concatenate([base.probabilities(head,values[r['video_id']]) for r in test]))
    return np.stack(pred,1),{'banks':{k:v[1] for k,v in banks.items()},'heads':heads,'train_ids':sorted(train_ids),'taxonomy':list(base.TAXONOMY)}


def prepare(parent,control,output):
    parent,control,output=map(Path,(parent,control,output));old=json.loads((parent/'protocol.json').read_text())
    plan={k:old[k] for k in ('development_ids','reserved_ids','folds','final_inner','taxonomy')}
    plan.update(version=VERSION,code_sha256=code_hash(),parent=str(parent.resolve()),input_marker_sha256=file_sha256(parent/'inputs.json'),
                control=str(control.resolve()),control_report_sha256=file_sha256(control/'report.json'),classes=CLASSES,grid=GRID,
                support='>=1 positive and >=2 negative TRAIN families, >=5 known samples per target; held-family unchanged',
                promotion='same exact-frame outer P>=.8,R>=.5,F1>=.8 and above unchanged control; prototype only',
                selection='inner-only threshold at P>=.8, max F1 then recall then precision',independent_test=False,human_approved=False,production_ready=False)
    plan['protocol_sha256']=stable_hash(plan);output.mkdir(parents=True,exist_ok=False);atomic_json(output/'protocol.json',plan)


def run(output):
    output=Path(output);plan=json.loads((output/'protocol.json').read_text());parent=Path(plan['parent']);control=Path(plan['control'])
    if plan['code_sha256']!=code_hash() or plan['protocol_sha256']!=stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'}):raise ValueError('Rare protocol changed')
    if (output/'report.json').exists():raise ValueError('Completed rare experiment')
    if file_sha256(parent/'inputs.json')!=plan['input_marker_sha256'] or file_sha256(control/'report.json')!=plan['control_report_sha256']:raise ValueError('Rare inputs changed')
    marker=json.loads((parent/'inputs.json').read_text());data={e['video_id']:safe_torch_load(parent/'inputs'/(e['video_id']+'.pt'),expected_sha256=e['sha256']) for e in marker['entries']}
    base.dino_probe.validate_folds(data,plan['folds'],data);base.dino_probe.validate_folds(data,plan['final_inner'],data)
    targets=[];decisions=[];previous=[]
    for n,fold in enumerate(plan['folds']):
        choices=select(data,fold['inner']);p,_=train_selected(data,fold['train'],fold['validation'],choices)
        y=np.concatenate([data[v]['coarse'].numpy()[:,CLASSES] for v in fold['validation']]);d=np.where(np.isfinite(p),p>=np.asarray([r['threshold'] for r in choices]),np.nan)
        old=np.load(control/f'fold-{n}.npz')
        if not np.array_equal(y,old['targets'][:,CLASSES]):raise ValueError('Rare exact-frame coverage changed')
        targets.append(y);decisions.append(d);previous.append(old['control'][:,CLASSES])
        atomic_json(output/f'fold-{n}.json',{'choices':choices,'sources':fold['validation']});np.savez_compressed(output/f'fold-{n}.npz',targets=y,decisions=d,control=previous[-1])
        print(json.dumps({'rare_fold':n,'metrics':{base.TAXONOMY[c]:base.statistics(y[:,j],d[:,j],.5) for j,c in enumerate(CLASSES)}}),flush=True)
    y=np.concatenate(targets);d=np.concatenate(decisions);old=np.concatenate(previous);classes={}
    for j,c in enumerate(CLASSES):
        m=base.statistics(y[:,j],d[:,j],.5);b=base.statistics(y[:,j],old[:,j],.5)
        classes[base.TAXONOMY[c]]={'candidate':m,'control':b,'promoted':bool(m['precision']>=.8 and m['recall']>=.5 and m['f1']>=.8 and m['f1']>b['f1'])}
    choices=select(data,plan['final_inner']);_,state=train_selected(data,plan['development_ids'],plan['development_ids'],choices);state.update(version=VERSION,protocol_sha256=plan['protocol_sha256']);atomic_checkpoint(output/'final.pt',state)
    report={'version':VERSION,'protocol_sha256':plan['protocol_sha256'],'classes':classes,'promoted':[n for n,m in classes.items() if m['promoted']],
            'final_sha256':file_sha256(output/'final.pt'),'production_ready':False,'independent_test':False,'positive_family_support_is_weak':True}
    atomic_json(output/'report.json',report);print(json.dumps({'rare_promoted':report['promoted']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--parent',type=Path,required=True);a.add_argument('--control',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('run');a.add_argument('--output',type=Path,required=True);a=p.parse_args();torch.set_num_threads(4)
    if a.command=='prepare':prepare(a.parent,a.control,a.output)
    else:run(a.output)
