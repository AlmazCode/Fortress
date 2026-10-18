"""Exact-PTS visual action heads; frozen DINOv2, nested family evaluation.

Weak scenario violations never become frame targets. Unknown observations are
masked. Per-class parameters and thresholds are selected on inner folds only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from sklearn.linear_model import LogisticRegression
import torch
import torch.nn.functional as F

from ml import dino_probe,temporal_actions
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint

VERSION='dino-source-action-kernel-v1'
TAXONOMY=temporal_actions.COARSE
DYNAMIC=TAXONOMY[:7]
GRID=[{'mode':mode,'gamma':gamma,'c':c} for mode in ('appearance','motion') for gamma in (2.,8.) for c in (.1,1.,10.)]


def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'encoder':dino_probe.code_hash()})


def prepare(root,output,device='cuda'):
    root,output=Path(root),Path(output)
    parent=json.loads((root/'temporal-operations-stage-v1c/protocol.json').read_text())
    old_plan=json.loads((root/'dinov2-temporal-readout-v1/protocol.json').read_text())
    if old_plan['code_sha256']!=dino_probe.code_hash():raise ValueError('DINO source preprocessing changed')
    old_marker=root/'dinov2-temporal-readout-v1/inputs.json'
    old_entries={e['video_id']:e['sha256'] for e in json.loads(old_marker.read_text())['entries']}
    for name,digest in old_plan['source_files'].items():
        if file_sha256(Path(old_plan['source_root'])/name)!=digest:raise ValueError('Pretrained encoder code changed')
    source=Path(json.loads((root/'prepared/readiness.json').read_text())['source_root'])
    output.mkdir(parents=True,exist_ok=False);(output/'inputs').mkdir()
    baseline=root/'local-state-stage-v1/cv_report.json'
    plan={'version':VERSION,'code_sha256':code_hash(),'parent_protocol_sha256':parent['protocol_sha256'],
          'baseline_report':str(baseline),'baseline_sha256':file_sha256(baseline),'old_inputs_sha256':file_sha256(old_marker),
          'development_ids':parent['development_ids'],'reserved_ids':parent['reserved_ids'],
          'folds':parent['folds'],'final_inner':parent['final_inner'],'taxonomy':list(TAXONOMY),
          'dynamic':list(DYNAMIC),'grid':GRID,'source_root':old_plan['source_root'],'source_files':old_plan['source_files'],
          'weights':old_plan['weights'],'weights_sha256':old_plan['weights_sha256'],'rate':2.,
          'supervision':'exact existing assistant-reviewed PTS labels only, -1 unknown ignored; no scenario/legal target',
          'selection':'inner-only per-class max F1 with precision>=.8; then recall,precision; otherwise unavailable',
          'support':'at least2 positive and2 negative training families, >=3 samples of each class',
          'promotion':'per-class outer precision>=.8,recall>=.5,F1>=.8 and F1 above old exact-PTS control',
          'independent_test':False,'human_approved':False,'production_ready':False}
    plan['protocol_sha256']=stable_hash(plan);atomic_json(output/'protocol.json',plan)
    encoder=dino_probe.encoder(plan['source_root'],plan['weights'],device);entries=[]
    for video in parent['development_ids']:
        path=root/'temporal-operations-stage-v1c/inputs'/(video+'.pt')
        if file_sha256(path)!=parent['inputs'][video]['sha256']:raise ValueError('Action labels changed')
        labels=safe_torch_load(path);old=safe_torch_load(root/'dinov2-temporal-readout-v1/inputs'/(video+'.pt'),expected_sha256=old_entries[video])
        index=json.loads((root/'prepared/indices'/(video+'.json')).read_text())
        if labels['source_sha256']!=old['source_sha256'] or labels['source_sha256']!=index['source_sha256']:
            raise ValueError('Mixed source identities')
        points=labels['source_pts']
        if old['source_pts']!=points[::2]:raise ValueError('DINO source sampling changed')
        odd=dino_probe.encode(encoder,source,index,points[1::2],device) if len(points)>1 else old['features'][:0]
        features=torch.empty(len(points),old['features'].shape[1]);features[::2]=old['features'];features[1::2]=odd
        payload={k:labels[k] for k in ('video_id','group_id','source_sha256','source_pts','times','coarse','target')}
        payload['features']=features
        destination=output/'inputs'/(video+'.pt');atomic_checkpoint(destination,payload)
        entries.append({'video_id':video,'sha256':file_sha256(destination)})
        print(json.dumps({'action_cached':video,'frames':len(points),'known':int((labels['coarse']>=0).sum())}),flush=True)
    atomic_json(output/'inputs.json',{'protocol_sha256':plan['protocol_sha256'],'entries':entries})


def frame_features(values,mode):
    x=torch.as_tensor(values,dtype=torch.float32)
    if x.ndim!=2 or not len(x) or x.shape[1]!=3840 or not torch.isfinite(x).all():raise ValueError('Action features')
    x=F.normalize(x,dim=1)
    if mode=='appearance':return x
    if mode!='motion':raise ValueError('Unknown action feature mode')
    before=torch.cat((x[:1],x[:-1]));after=torch.cat((x[1:],x[-1:]))
    delta=(after-before)*.5
    return F.normalize(torch.cat((x,3*(x-x.mean(0)),5*delta,5*delta.abs()),1),dim=1)


def representation(train,rows,mode,gamma):
    anchors=[]
    for row in train:
        x=frame_features(row['features'],mode)
        chosen=sorted(set(round(n*(len(x)-1)/3) for n in range(4)))
        anchors.append(x[chosen])
    anchors=torch.cat(anchors)
    def transform(row):
        x=frame_features(row['features'],mode)
        return torch.exp(-gamma*(1-x@anchors.T).clamp_min(0)).numpy()
    train_x=np.concatenate([transform(r) for r in train])
    mean=train_x.mean(0);scale=np.maximum(train_x.std(0),.03)
    values={r['video_id']:((transform(r)-mean)/scale).astype(np.float64) for r in rows}
    return values,{'anchors':anchors,'mean':torch.from_numpy(mean),'scale':torch.from_numpy(scale),'mode':mode,'gamma':gamma}


def fit_class(train,values,c,regularization):
    x=[];y=[];groups=[];families={0:set(),1:set()}
    for row in train:
        targets=row['coarse'][:,c].numpy();known=targets>=0
        for v in (0,1):
            if (targets==v).any():families[v].add(row['group_id'])
        x.append(values[row['video_id']][known]);y.extend(targets[known]);groups.extend([row['video_id']]*int(known.sum()))
    y=np.asarray(y);groups=np.asarray(groups)
    if any(len(families[v])<2 or int((y==v).sum())<3 for v in (0,1)):return None
    weights=np.zeros(len(y))
    for v in (0,1):
        sources=np.unique(groups[y==v])
        for source in sources:
            mask=(y==v)&(groups==source);weights[mask]=len(y)/(2*len(sources)*mask.sum())
    model=LogisticRegression(C=regularization,solver='lbfgs',max_iter=300,tol=1e-6)
    model.fit(np.concatenate(x),y,sample_weight=weights)
    return {'weight':torch.tensor(model.coef_[0],dtype=torch.float32),'bias':float(model.intercept_[0])}


def probabilities(head,x):
    if head is None:return np.full(len(x),np.nan)
    z=np.clip(x@head['weight'].double().numpy()+head['bias'],-30,30)
    return 1/(1+np.exp(-z))


def statistics(y,p,threshold):
    y=np.asarray(y);p=np.asarray(p);known=y>=0;y=y[known];p=p[known]
    predicted=np.isfinite(p)&(p>=threshold)
    tp=int(((y==1)&predicted).sum());fp=int(((y==0)&predicted).sum());fn=int(((y==1)&~predicted).sum())
    precision=tp/max(1,tp+fp);recall=tp/max(1,tp+fn)
    return {'positive':int((y==1).sum()),'negative':int((y==0).sum()),'tp':tp,'fp':fp,'fn':fn,
            'precision':precision,'recall':recall,'f1':2*tp/max(1,2*tp+fp+fn),
            'prediction_coverage':float(np.isfinite(p).mean()) if len(p) else 0.}


def threshold(y,p):
    y=np.asarray(y);p=np.asarray(p);known=(y>=0)&np.isfinite(p)
    if not known.any() or len(np.unique(y[known]))<2:return 1.000001
    order=np.argsort(-p[known],kind='stable');scores=p[known][order];truth=y[known][order]
    tp=np.cumsum(truth==1);fp=np.cumsum(truth==0);positive=max(1,int((y==1).sum()))
    ends=np.flatnonzero(np.r_[scores[:-1]!=scores[1:],True]);choices=[]
    for i in ends:
        precision=tp[i]/max(1,tp[i]+fp[i]);recall=tp[i]/positive
        t=float((scores[i]+scores[i+1])/2) if i+1<len(scores) else float(scores[i]/2)
        if precision>=.8:choices.append((float(2*tp[i]/max(1,positive+tp[i]+fp[i])),float(recall),float(precision),t))
    m=statistics(y,p,.5)
    if m['precision']>=.8:choices.append((m['f1'],m['recall'],m['precision'],.5))
    return max(choices)[-1] if choices else 1.000001


def select(data,folds):
    pooled={stable_hash(candidate):[[],[]] for candidate in GRID}
    for fold in folds:
        train=[data[v] for v in fold['train']];validation=[data[v] for v in fold['validation']]
        for mode in ('appearance','motion'):
            for gamma in (2.,8.):
                values,_=representation(train,train+validation,mode,gamma)
                target=np.concatenate([r['coarse'].numpy() for r in validation])
                for regularization in (.1,1.,10.):
                    candidate={'mode':mode,'gamma':gamma,'c':regularization}
                    heads=[fit_class(train,values,c,regularization) for c in range(len(TAXONOMY))]
                    p=np.concatenate([np.stack([probabilities(head,values[r['video_id']]) for head in heads],1) for r in validation])
                    pooled[stable_hash(candidate)][0].append(target);pooled[stable_hash(candidate)][1].append(p)
    choices=[]
    for c in range(len(TAXONOMY)):
        candidates=[]
        for candidate in GRID:
            targets,pred=pooled[stable_hash(candidate)];y=np.concatenate(targets)[:,c];p=np.concatenate(pred)[:,c]
            t=threshold(y,p);m=statistics(y,p,t)
            candidates.append({'candidate':candidate,'threshold':t,'metrics':m})
        choices.append(max(candidates,key=lambda row:(row['metrics']['f1'],row['metrics']['recall'],row['metrics']['precision'])))
    return choices


def train_selected(data,train_ids,test_ids,choices):
    train=[data[v] for v in train_ids];test=[data[v] for v in test_ids];banks={};heads=[];out=np.full((sum(len(r['features']) for r in test),len(TAXONOMY)),np.nan)
    for c,choice in enumerate(choices):
        candidate=choice['candidate'];key=(candidate['mode'],candidate['gamma'])
        if key not in banks:banks[key]=representation(train,train+test,*key)
        values,bank=banks[key];head=fit_class(train,values,c,candidate['c'])
        out[:,c]=np.concatenate([probabilities(head,values[r['video_id']]) for r in test])
        heads.append({'bank':stable_hash({'mode':key[0],'gamma':key[1]}),'head':head,'threshold':choice['threshold']})
    state={'banks':{stable_hash({'mode':k[0],'gamma':k[1]}):v[1] for k,v in banks.items()},'heads':heads,'train_ids':sorted(train_ids)}
    return out,state


def run(output):
    output=Path(output);plan=json.loads((output/'protocol.json').read_text())
    if plan['code_sha256']!=code_hash() or plan['protocol_sha256']!=stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'}):raise ValueError('Action protocol changed')
    if (output/'report.json').exists():raise ValueError('Completed action experiment')
    marker=json.loads((output/'inputs.json').read_text());data={e['video_id']:safe_torch_load(output/'inputs'/(e['video_id']+'.pt'),expected_sha256=e['sha256']) for e in marker['entries']}
    if set(data)!=set(plan['development_ids']) or set(data)&set(plan['reserved_ids']):raise ValueError('Action source partition')
    dino_probe.validate_folds(data,plan['folds'],data);dino_probe.validate_folds(data,plan['final_inner'],data)
    targets=[];predictions=[];decisions=[];fold_reports=[]
    for n,fold in enumerate(plan['folds']):
        started=time.monotonic();choices=select(data,fold['inner']);p,_=train_selected(data,fold['train'],fold['validation'],choices)
        y=np.concatenate([data[v]['coarse'].numpy() for v in fold['validation']]);thresholds=np.asarray([r['threshold'] for r in choices])
        predicted=np.where(np.isfinite(p),(p>=thresholds).astype(float),np.nan)
        targets.append(y);predictions.append(p);decisions.append(predicted)
        record={'fold':n,'choices':choices,'sources':fold['validation'],'counts':[len(data[v]['features']) for v in fold['validation']]}
        atomic_json(output/f'fold-{n}.json',record);fold_reports.append(record)
        np.savez_compressed(output/f'fold-{n}.npz',targets=y,predictions=p,decisions=predicted)
        print(json.dumps({'action_fold':n,'seconds':time.monotonic()-started,'f1':{name:statistics(y[:,c],predicted[:,c],.5)['f1'] for c,name in enumerate(DYNAMIC)}}),flush=True)
    y=np.concatenate(targets);p=np.concatenate(decisions)
    if file_sha256(plan['baseline_report'])!=plan['baseline_sha256']:raise ValueError('Action control changed')
    baseline=json.loads(Path(plan['baseline_report']).read_text())['state_oof']['False'];classes={}
    for c,name in enumerate(TAXONOMY):
        m=statistics(y[:,c],p[:,c],.5);old=baseline[name]['metrics'];old_f1=(old['per_class'][1]['f1'] or 0.) if old and old['per_class'][1] else 0.
        m.update(baseline_f1=old_f1,promoted=bool(m['precision']>=.8 and m['recall']>=.5 and m['f1']>=.8 and m['f1']>old_f1))
        if m['positive']!=baseline[name]['positive'] or m['negative']!=baseline[name]['negative']:raise ValueError('Unequal action evaluation coverage')
        classes[name]=m
    choices=select(data,plan['final_inner']);_,state=train_selected(data,plan['development_ids'],plan['development_ids'],choices)
    state.update(version=VERSION,protocol_sha256=plan['protocol_sha256'],taxonomy=list(TAXONOMY),promoted=[classes[name]['promoted'] for name in TAXONOMY])
    atomic_checkpoint(output/'final.pt',state)
    report={'protocol_sha256':plan['protocol_sha256'],'classes':classes,
            'dynamic_macro_f1':float(np.mean([classes[name]['f1'] for name in DYNAMIC])),
            'dynamic_evaluable_macro_f1':float(np.mean([classes[name]['f1'] for name in DYNAMIC if classes[name]['positive']>0])),
            'dynamic_evaluable_classes':[name for name in DYNAMIC if classes[name]['positive']>0],
            'promoted_classes':[name for name in TAXONOMY if classes[name]['promoted']],
            'final_sha256':file_sha256(output/'final.pt'),'folds':fold_reports,'production_ready':False,'independent_test':False}
    atomic_json(output/'report.json',report);print(json.dumps({k:v for k,v in report.items() if k not in ('classes','folds')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--root',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('run');a.add_argument('--output',type=Path,required=True);a=p.parse_args();torch.set_num_threads(4)
    if a.command=='prepare':prepare(a.root,a.output)
    else:run(a.output)
