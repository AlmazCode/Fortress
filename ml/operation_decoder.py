"""Linear operation decoder and cross-fitted bounded clip correction.

The frozen CNN/GRU control is preserved. Video-centred visual differences feed a
small ridge head. No imported labels, names, times or hashes are inference inputs.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import time

import numpy as np
import torch

from ml import temporal_actions as source
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256, safe_torch_load
from ml.small_data import summarize
from ml.video_baseline import atomic_json, atomic_checkpoint

VERSION='centred-operation-decoder-v1'
RIDGE=.1
TEMPERATURE=.2
RESIDUAL_BOUND=2.
RESIDUAL_PENALTY=.5
DIM=source.DIM*2


def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'source':source.code_hash()})


def visual_features(values):
    if values.ndim!=2 or values.shape[1]!=source.DIM or not torch.isfinite(values).all():raise ValueError('Decoder visual input')
    centered=values-values.mean(0,keepdim=True)
    before=torch.cat((values[:1],values[:-1]),0)
    after=torch.cat((values[1:],values[-1:]),0)
    return torch.cat((centered,(after-before)*.5),1)


def fit(rows,device='cuda'):
    enabled,*_=source.support(rows)
    # All statistics are training-only; video centering itself uses no labels.
    all_values=[visual_features(r['features'][0]) for r in rows]
    mean=torch.stack([x.mean(0) for x in all_values]).mean(0)
    scale=torch.stack([x.square().mean(0) for x in all_values]).mean(0).clamp_min(.0025).sqrt()
    examples=[];targets=[];row_weights=[]
    for row in rows:
        y=row['fine']*enabled
        known=y.sum(-1)>0
        y=y/y.sum(-1,keepdim=True).clamp_min(1)
        for variant in range(3):
            x=(visual_features(row['features'][variant])-mean)/scale
            x=torch.nn.functional.normalize(x,dim=-1)
            examples.append(x[known]);targets.append(y[known]);row_weights.append(torch.full((int(known.sum()),),1/max(1,int(known.sum()))))
    x=torch.cat(examples).to(device);y=torch.cat(targets).to(device)
    # Class and source balancing, without creating targets outside annotation coverage.
    class_weight=y.sum(0).clamp_min(1).rsqrt()
    weights=torch.cat(row_weights).to(device)*(y*class_weight).sum(-1)
    weights=weights/weights.mean().clamp_min(1e-8)
    # Primal solve is larger than dual here; collapse brightness rows by label
    # preserving their average visual representation and train on that mean.
    unique_x=[];unique_y=[];unique_weight=[];offset=0
    for row in rows:
        known=(row['fine']*enabled).sum(-1)>0;n=int(known.sum())
        if not n:continue
        unique_x.append(x[offset:offset+3*n].reshape(3,n,-1).mean(0))
        unique_y.append(y[offset:offset+n]);unique_weight.append(weights[offset:offset+3*n].reshape(3,n).mean(0));offset+=3*n
    x=torch.cat(unique_x);y=torch.cat(unique_y);weight=torch.cat(unique_weight).sqrt()
    a=x*weight[:,None];b=y*weight[:,None]
    gram=a@a.T+RIDGE*torch.eye(len(a),device=device)
    coefficients=a.T@torch.linalg.solve(gram,b)
    return {'weight':coefficients.cpu(),'mean':mean,'scale':scale,'support':enabled,
            'train_ids':sorted(r['video_id'] for r in rows),'version':VERSION}


def predict(checkpoint,rows):
    result=[]
    for row in rows:
        x=(visual_features(row['features'][0])-checkpoint['mean'])/checkpoint['scale']
        x=torch.nn.functional.normalize(x,dim=-1)
        logits=(x@checkpoint['weight'])/TEMPERATURE
        logits[:,~checkpoint['support']]=-100.
        probabilities=logits.softmax(-1);probabilities[:,~checkpoint['support']]=0
        before=torch.cat((probabilities[:1],probabilities[:-1]),0)
        after=torch.cat((probabilities[1:],probabilities[-1:]),0)
        probabilities=.25*before+.5*probabilities+.25*after
        result.append({'video_id':row['video_id'],'truth':bool(row['target']),'score':.5,'fine':probabilities})
    return result


def summary(probabilities):
    n=len(probabilities)
    return torch.cat((probabilities.mean(0),probabilities.amax(0),probabilities[-max(1,n//3):].mean(0)))


def logit(value):
    value=torch.as_tensor(value,dtype=torch.float32).clamp(.00001,.99999)
    return torch.logit(value)


def fit_residual(predictions,reference,threshold):
    by_id={r['video_id']:r for r in reference}
    if len(by_id)!=len(reference) or set(by_id)!={p['video_id'] for p in predictions}:raise ValueError('Crossfit reference coverage')
    x=torch.stack([summary(p['fine']) for p in predictions]);mean=x.mean(0);scale=x.std(0,unbiased=False).clamp_min(.1)
    z=(x-mean)/scale
    baseline=torch.stack([logit(by_id[p['video_id']]['score'])-logit(threshold) for p in predictions])
    y=torch.tensor([float(by_id[p['video_id']]['truth']) for p in predictions])
    if {bool(t) for t in y}!={False,True}:raise ValueError('Residual needs both train classes')
    weight=torch.zeros(z.shape[1],requires_grad=True);bias=torch.zeros((),requires_grad=True)
    optimizer=torch.optim.Adam((weight,bias),lr=.03)
    for _ in range(200):
        correction=RESIDUAL_BOUND*torch.tanh((z@weight+bias)/RESIDUAL_BOUND)
        loss=torch.nn.functional.binary_cross_entropy_with_logits(baseline+correction,y)
        loss=loss+RESIDUAL_PENALTY*(weight.square().sum()+bias.square())
        optimizer.zero_grad(set_to_none=True);loss.backward();optimizer.step()
    return {'weight':weight.detach(),'bias':bias.detach(),'mean':mean,'scale':scale,'base_threshold':threshold}


def corrected_scores(state,predictions,reference):
    by_id={r['video_id']:r for r in reference};result=[]
    for p in predictions:
        ref=by_id[p['video_id']]
        z=(summary(p['fine'])-state['mean'])/state['scale']
        correction=RESIDUAL_BOUND*torch.tanh((z@state['weight']+state['bias'])/RESIDUAL_BOUND)
        value=(logit(ref['score'])-logit(state['base_threshold'])+correction).sigmoid()
        result.append({'video_id':p['video_id'],'truth':bool(ref['truth']),'score':float(value),'threshold':.5})
    return result


def prepare(inputs,reference,destination):
    inputs,reference,destination=Path(inputs),Path(reference),Path(destination)
    parent=read_json(inputs/'protocol.json')
    if parent['code_sha256']!=source.code_hash():raise ValueError('Source operation supervision changed')
    old=read_json(reference)
    if len(old['folds'])!=len(parent['folds']):raise ValueError('Reference fold mismatch')
    for new,prior in zip(parent['folds'],old['folds']):
        if set(new['train'])!=set(prior['train']) or set(new['validation'])!=set(prior['validation']):raise ValueError('Reference family partition mismatch')
    plan={'version':VERSION,'code_sha256':code_hash(),'inputs':str(inputs.resolve()),'input_protocol':parent['protocol_sha256'],
          'reference':str(reference.resolve()),'reference_sha256':file_sha256(reference),'folds':parent['folds'],
          'final_inner':parent['final_inner'],'development_ids':parent['development_ids'],'reserved_ids':parent['reserved_ids'],
          'ridge':RIDGE,'temperature':TEMPERATURE,'residual_bound':RESIDUAL_BOUND,'residual_penalty':RESIDUAL_PENALTY,
          'selection':'fixed decoder; thresholds from inner OOF only; residual trained on inner crossfit predictions; fixed final decision .5',
          'control':parent['control'],'production_ready':False,'independent_external_test':False}
    plan['protocol_sha256']=stable_hash(plan)
    destination.mkdir(parents=True,exist_ok=False);atomic_json(destination/'protocol.json',plan)


class Experiment:
    def __init__(self,directory,device='cuda'):
        self.directory=Path(directory);self.plan=read_json(self.directory/'protocol.json');self.device=device
        if self.plan['code_sha256']!=code_hash() or self.plan['protocol_sha256']!=stable_hash({k:v for k,v in self.plan.items() if k!='protocol_sha256'}):raise ValueError('Decoder protocol/code changed')
        self.original=source.Experiment(self.plan['inputs'],device);self.rows=self.original.rows
        if file_sha256(self.plan['reference'])!=self.plan['reference_sha256']:raise ValueError('Reference predictions changed')
        self.reference=read_json(self.plan['reference']);self.memo={}
        (self.directory/'fits').mkdir(exist_ok=True)

    def train(self,ids):
        if not set(ids)<=set(self.plan['development_ids']) or len(set(ids))!=len(ids):raise ValueError('Foreign decoder training data')
        identity={'ids':sorted(ids),'protocol':self.plan['protocol_sha256']};key=stable_hash(identity)
        if key in self.memo:return self.memo[key]
        path=self.directory/'fits'/(key+'.pt')
        if path.exists():
            value=safe_torch_load(path)
            if value['identity']!=identity:raise ValueError('Decoder fit identity changed')
        else:
            started=time.monotonic();value={**fit([self.rows[v] for v in ids],self.device),'identity':identity}
            atomic_checkpoint(path,value)
            print(__import__('json').dumps({'decoder_sources':len(ids),'seconds':time.monotonic()-started}),flush=True)
        self.memo[key]=value;return value

    def crossfit(self,folds):
        result=[]
        for fold in folds:
            if {self.rows[v]['group_id'] for v in fold['train']} & {self.rows[v]['group_id'] for v in fold['validation']}:raise ValueError('Decoder family leakage')
            result.extend(predict(self.train(fold['train']),[self.rows[v] for v in fold['validation']]))
        return result

    def run(self):
        if (self.directory/'complete.json').exists():raise ValueError('Completed decoder experiment is immutable')
        predictions={str(s):[] for s in source.SEEDS};action_predictions=[]
        for number,fold in enumerate(self.plan['folds']):
            calibrated=self.crossfit(fold['inner'])
            action_t=source.action_thresholds(calibrated,self.rows)
            prior=self.reference['folds'][number]['choices']['uniform_gru']
            if {p['video_id'] for p in calibrated}!=set(fold['train']):raise ValueError('Outer validation entered crossfit')
            residual=fit_residual(calibrated,prior['oof'],prior['threshold'])
            held=predict(self.train(fold['train']),[self.rows[v] for v in fold['validation']])
            for seed in source.SEEDS:
                reference=[r for r in self.reference['oof']['uniform_gru'][str(seed)] if r['video_id'] in fold['validation']]
                predictions[str(seed)].extend(corrected_scores(residual,held,reference))
            action_predictions.extend([{**p,'fine':p['fine']/torch.tensor(action_t).clamp_min(.001)} for p in held])
            atomic_checkpoint(self.directory/f'outer-{number}.pt',{'residual':residual,'held':held,'action_thresholds':action_t,'predictions':predictions})
            print(__import__('json').dumps({'decoder_outer_complete':number}),flush=True)
        per_seed={seed:summarize(p) for seed,p in predictions.items()}
        mean={k:float(np.mean([m[k] for m in per_seed.values()])) for k in ('accuracy','balanced_accuracy','macro_f1')}
        actions=source.action_report(action_predictions,self.rows,[1.]*len(source.TAXONOMY))
        improved=all(mean[k]>=self.plan['control'][k] for k in mean) and mean['accuracy']>self.plan['control']['accuracy']
        report={'version':VERSION,'protocol_sha256':self.plan['protocol_sha256'],'clip_seeds':per_seed,'clip_mean':mean,
                'actions':actions,'clip_promoted':improved,'control':self.plan['control'],'oof_predictions':predictions,
                'production_ready':False,'independent_external_test':False}
        atomic_json(self.directory/'cv_report.json',report)
        calibrated=self.crossfit(self.plan['final_inner']);action_t=source.action_thresholds(calibrated,self.rows)
        old=self.reference['final_choices']['uniform_gru']
        residual=fit_residual(calibrated,old['oof'],old['threshold'])
        final={**self.train(self.plan['development_ids']),'residual':residual,'action_thresholds':action_t,'protocol_sha256':self.plan['protocol_sha256']}
        atomic_checkpoint(self.directory/'final.pt',final)
        atomic_json(self.directory/'complete.json',{'fit_sha256':file_sha256(self.directory/'final.pt'),'report_sha256':file_sha256(self.directory/'cv_report.json'),
                                               'clip_promoted':improved,'production_ready':False})
        print(__import__('json').dumps({'clip_mean':mean,'action_f1':actions['macro_f1_all_classes'],'clip_promoted':improved}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--inputs',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('run');p.add_argument('--output',type=Path,required=True);p.add_argument('--device',default='cuda')
    args=parser.parse_args();torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
    if args.command=='prepare':prepare(args.inputs,args.reference,args.output)
    else:Experiment(args.output,args.device).run()


if __name__=='__main__':main()
