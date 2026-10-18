"""Weak event localization over fold-specific frozen CNN/GRU representations.

Scenario interpretations are weak targets, not verified legal findings. Outside
positive intervals remains unknown; a soft within-video ranking term gives the
annotated window priority without treating it as exhaustive negative annotation.
"""
from __future__ import annotations
import argparse
import hashlib
import math
from pathlib import Path
import time
import json
import numpy as np
import torch
from torch.nn.utils.rnn import pad_packed_sequence

from ml import object_events as reference
from ml import temporal_actions as operations
from ml import operation_crops as crops
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint,metrics
from ml.small_data import summarize

VERSION='weak-temporal-risk-v1'
ARMS=('base_control','risk_localizer','risk_blend')
DIM=256+operations.DIM*2
REGULARIZATION=.02
RANKING_WEIGHT=.2


def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'reference':reference.code_hash(),'crops':crops.code_hash(),'operations':operations.code_hash()})


def targets(row,annotations):
    times=row['times'];y=torch.full((len(times),),-1.)
    if not row['target']:return torch.zeros(len(times))
    for record in annotations:
        if record['video_id']!=row['video_id'] or record.get('label_kind')!='scenario_interpretation' or record.get('known') is not True:continue
        start,end=record['start_sec'],record['end_sec']
        if not 0<=start<end:raise ValueError('Invalid weak risk interval')
        margin=min(float(record.get('boundary_uncertainty_sec',1.)),(end-start)*.2)
        for n,t in enumerate(times):
            if start+margin<=t<=end-margin:y[n]=1.
    return y


def combine(hidden,visual):
    if hidden.shape!=(len(visual),256) or visual.shape[1]!=operations.DIM:raise ValueError('Risk representation shape')
    return torch.cat((hidden,visual,visual-visual.mean(0,keepdim=True)),1)


def fit(rows,representations,device='cuda'):
    values=[representations[r['video_id']]['features'] for r in rows]
    mean=torch.stack([x.mean(0) for x in values]).mean(0)
    second=torch.stack([x.square().mean(0) for x in values]).mean(0)
    scale=(second-mean.square()).clamp_min(.01).sqrt()
    x=torch.cat([(v-mean)/scale for v in values]).to(device)
    y=torch.cat([r['risk'] for r in rows]).to(device)
    known=y>=0
    if not (y==0).any() or not (y==1).any():raise ValueError('Risk supervision needs both classes')
    sample_weights=[];pairs=[];offset=0
    for row in rows:
        target=row['risk'];n=len(target);mask=target>=0
        sample_weights.append(torch.full((n,),1/max(1,int(mask.sum()))))
        if row['target'] and (target==1).any() and (target<0).any():
            pairs.append((torch.where(target==1)[0].to(device)+offset,torch.where(target<0)[0].to(device)+offset))
        offset+=n
    sample_weights=torch.cat(sample_weights).to(device)
    sample_weights=sample_weights*torch.where(y==1,(y==0).sum()/(y==1).sum(),1.)
    sample_weights=sample_weights/sample_weights[known].sum()
    w=torch.zeros(DIM,device=device,requires_grad=True);b=torch.zeros((),device=device,requires_grad=True)
    optimizer=torch.optim.LBFGS((w,b),lr=1.,max_iter=60,history_size=10,line_search_fn='strong_wolfe')
    def closure():
        optimizer.zero_grad(set_to_none=True);logits=x@w+b
        loss=(torch.nn.functional.binary_cross_entropy_with_logits(logits[known],y[known],reduction='none')*sample_weights[known]).sum()
        if pairs:
            ranking=[]
            for positive,unknown in pairs:
                a=torch.logsumexp(logits[positive],0)-math.log(len(positive))
                u=torch.logsumexp(logits[unknown],0)-math.log(len(unknown))
                ranking.append(torch.nn.functional.softplus(u-a+.5))
            loss=loss+RANKING_WEIGHT*torch.stack(ranking).mean()
        loss=loss+REGULARIZATION*(w.square().sum()+b.square())
        if not torch.isfinite(loss):raise ValueError('Nonfinite risk fit')
        loss.backward();return loss
    optimizer.step(closure)
    return {'weight':w.detach().cpu(),'bias':b.detach().cpu(),'mean':mean,'scale':scale,
            'train_ids':sorted(r['video_id'] for r in rows),'weak_targets':True}


def predict(state,rows,representations):
    result=[]
    for row in rows:
        representation=representations[row['video_id']]
        z=(representation['features']-state['mean'])/state['scale']
        p=(z@state['weight']+state['bias']).sigmoid()
        before=torch.cat((p[:1],p[:-1]));after=torch.cat((p[1:],p[-1:]));p=.25*before+.5*p+.25*after
        result.append({'video_id':row['video_id'],'truth':bool(row['target']),'base':representation['score'],
                       'risk':float(p.topk(min(3,len(p))).values.mean()),'frame_risk':p})
    return result


def arm_rows(predictions,arm):
    key='base' if arm=='base_control' else 'risk'
    return [{'video_id':r['video_id'],'truth':r['truth'],
             'score':float(.5*(r['base']+r['risk']) if arm=='risk_blend' else r[key])} for r in predictions]


def calibrate_event(predictions,rows):
    y=torch.cat([rows[p['video_id']]['risk'] for p in predictions]);scores=torch.cat([p['frame_risk'] for p in predictions]);known=y>=0
    y=y[known]==1;scores=scores[known]
    best=(-1.,1.)
    for t in np.linspace(.1,.9,33):
        pred=scores>=t;tp=int((pred&y).sum());fp=int((pred&~y).sum());fn=int((~pred&y).sum())
        f1=2*tp/max(1,2*tp+fp+fn)
        if (f1,t)>best:best=(f1,float(t))
    return best[1]


def prepare(inputs,destination):
    inputs,destination=Path(inputs),Path(destination);parent=read_json(inputs/'protocol.json')
    root=Path(parent['root']);source_root=Path(read_json(root/'prepared/readiness.json')['source_root'])
    annotations=source_root/'annotations/violations_weak.json'
    plan={'version':VERSION,'code_sha256':code_hash(),'inputs':str(inputs.resolve()),'input_protocol':parent['protocol_sha256'],
          'root':str(root),'weak_labels':str(annotations),'weak_labels_sha256':file_sha256(annotations),
          'reference_protocol_sha256':file_sha256(root/'object-stage-v2/protocol.json'),
          'folds':parent['folds'],'final_inner':parent['final_inner'],'development_ids':parent['development_ids'],
          'reserved_ids':parent['reserved_ids'],'seeds':operations.SEEDS,'arms':ARMS,'regularization':REGULARIZATION,'ranking_weight':RANKING_WEIGHT,
          'selection':'inner OOF max min(accuracy,BA,macroF1), then accuracy,BA,F1; fixed seed42 selection; three outer seeds',
          'negative_policy':'unchanged user_scenario no_violation implies weak negative frames; outside positive intervals stays unknown',
          'interpretation':'scenario weak labels only; not denomination recognition or verified legal findings',
          'control':parent['control'],'production_ready':False,'independent_external_test':False}
    plan['protocol_sha256']=stable_hash(plan);destination.mkdir(parents=True,exist_ok=False);atomic_json(destination/'protocol.json',plan)


class Experiment:
    def __init__(self,directory,device='cuda'):
        self.directory=Path(directory);self.plan=read_json(self.directory/'protocol.json');self.device=device
        if self.plan['code_sha256']!=code_hash() or self.plan['protocol_sha256']!=stable_hash({k:v for k,v in self.plan.items() if k!='protocol_sha256'}):raise ValueError('Risk protocol/code changed')
        self.source=operations.Experiment(self.plan['inputs'],device);self.rows=self.source.rows
        if file_sha256(self.plan['weak_labels'])!=self.plan['weak_labels_sha256']:raise ValueError('Risk labels changed')
        annotations=read_json(self.plan['weak_labels'])['annotations']
        for r in self.rows.values():r['risk']=targets(r,annotations)
        root=Path(self.plan['root'])
        if file_sha256(root/'object-stage-v2/protocol.json')!=self.plan['reference_protocol_sha256']:raise ValueError('Risk reference changed')
        self.reference=reference.Experiment(root/'object-stage-v2',device);self.root=root;self.memo={}
        (self.directory/'fits').mkdir(exist_ok=True);(self.directory/'representations').mkdir(exist_ok=True)

    def reference_path(self,ids,seed):
        identity={'protocol':self.reference.plan['protocol_sha256'],'kind':'temporal','mode':'uniform','ids':sorted(ids),'seed':seed}
        path=self.root/'object-stage-v2/fits'/(stable_hash(identity)+'.pt')
        if not path.exists() and set(ids)==set(self.plan['development_ids']) and seed==42:
            prior=read_json(self.root/'transition-state-stage-v1/final_reference.json');path=Path(prior['fit'])
            if file_sha256(path)!=prior['sha256']:raise ValueError('Final control changed')
        state=safe_torch_load(path)
        if state['identity']!=identity:raise ValueError('Risk encoder/GRU saw a foreign training source')
        if file_sha256(state['spatial'])!=state['spatial_sha256']:raise ValueError('Risk spatial lineage')
        return path,state

    def representations(self,ids,seed):
        path,state=self.reference_path(ids,seed);key=stable_hash({'reference':file_sha256(path),'input_protocol':self.plan['input_protocol']})
        if key in self.memo:return self.memo[key]
        cache=self.directory/'representations'/(key+'.pt')
        if cache.exists():
            value=safe_torch_load(cache,max_bytes=128*1024**2)
            if value['reference_sha256']!=file_sha256(path):raise ValueError('Risk representation lineage')
            self.memo.clear();self.memo[key]=value['rows'];return value['rows']
        self.memo.clear();self.reference.memo.clear()
        requested=self.plan['development_ids'];observations=self.reference.observations(Path(state['spatial']),requested)
        model=reference.Temporal().to(self.device).eval();model.load_state_dict(state['model'],strict=True)
        captured=[]
        hook=model.gru.register_forward_hook(lambda module,args,out:captured.append(pad_packed_sequence(out[0],batch_first=True)[0].detach().cpu()))
        result={}
        with torch.inference_mode():
            for video,obs in zip(requested,observations):
                x=(obs['uniform']-state['normalization']['mean'])/state['normalization']['std']
                logits,_=model(x[None].to(self.device),torch.tensor([len(x)]))
                hidden=captured.pop()[0]
                result[video]={'features':combine(hidden,self.rows[video]['features'][0]),'score':float(logits.sigmoid()[0]),
                               'source_sha256':self.rows[video]['source_sha256']}
        hook.remove()
        # This cache has >16MB of features; it is data, not a deployable checkpoint.
        temporary=cache.with_suffix('.tmp');torch.save({'rows':result,'reference_sha256':file_sha256(path)},temporary);temporary.replace(cache)
        self.memo[key]=result;return result

    def train(self,ids,seed):
        if not set(ids)<=set(self.plan['development_ids']):raise ValueError('Reserved risk training source')
        identity={'ids':sorted(ids),'seed':seed,'protocol':self.plan['protocol_sha256']};path=self.directory/'fits'/(stable_hash(identity)+'.pt')
        rep=self.representations(ids,seed)
        if path.exists():
            state=safe_torch_load(path)
            if state['identity']!=identity:raise ValueError('Risk fit identity')
            return state,rep
        started=time.monotonic();state={**fit([self.rows[v] for v in ids],rep,self.device),'identity':identity}
        atomic_checkpoint(path,state);print(json.dumps({'risk_fit_sources':len(ids),'seed':seed,'seconds':time.monotonic()-started}),flush=True)
        return state,rep

    def crossfit(self,folds):
        predictions=[]
        for fold in folds:
            if {self.rows[v]['group_id'] for v in fold['train']} & {self.rows[v]['group_id'] for v in fold['validation']}:raise ValueError('Risk family leakage')
            state,rep=self.train(fold['train'],42)
            predictions.extend(predict(state,[self.rows[v] for v in fold['validation']],rep))
        return predictions

    def run(self):
        if (self.directory/'complete.json').exists():raise ValueError('Completed risk experiment immutable')
        result={a:{str(s):[] for s in operations.SEEDS} for a in ARMS};nested={str(s):[] for s in operations.SEEDS};localization=[]
        for number,fold in enumerate(self.plan['folds']):
            record_path=self.directory/f'outer-{number}.pt'
            if record_path.exists():record=safe_torch_load(record_path)
            else:
                inner=self.crossfit(fold['inner']);choices={}
                for arm in ARMS:
                    rows=arm_rows(inner,arm);threshold=operations.clip_threshold(rows);m=metrics(rows,threshold)
                    choices[arm]={'threshold':threshold,'metrics':m}
                def rank(arm):
                    m=choices[arm]['metrics'];return (min(m['accuracy'],m['balanced_accuracy'],m['macro_f1']),m['accuracy'],m['balanced_accuracy'],m['macro_f1'],-ARMS.index(arm))
                chosen=max(ARMS,key=rank);event_t=calibrate_event(inner,self.rows);predictions={}
                for seed in operations.SEEDS:
                    state,rep=self.train(fold['train'],seed);predictions[str(seed)]=predict(state,[self.rows[v] for v in fold['validation']],rep)
                record={'choices':choices,'selected':chosen,'event_threshold':event_t,'predictions':predictions}
                atomic_checkpoint(record_path,record)
            for seed,p in record['predictions'].items():
                for arm in ARMS:
                    rows=[{**r,'threshold':record['choices'][arm]['threshold']} for r in arm_rows(p,arm)]
                    result[arm][seed].extend(rows)
                    if arm==record['selected']:nested[seed].extend(rows)
            for p in record['predictions']['42']:localization.append({**p,'event_threshold':record['event_threshold']})
            print(json.dumps({'risk_outer_complete':number,'selected':record['selected']}),flush=True)
        comparisons={a:{s:summarize(p) for s,p in values.items()} for a,values in result.items()}
        nested_metrics={s:summarize(p) for s,p in nested.items()}
        mean={k:float(np.mean([m[k] for m in nested_metrics.values()])) for k in ('accuracy','balanced_accuracy','macro_f1')}
        tp=fp=fn=positive=hits=0
        for p in localization:
            y=self.rows[p['video_id']]['risk'];known=y>=0;pred=p['frame_risk']>=p['event_threshold']
            tp+=int((pred&(y==1)).sum());fp+=int((pred&(y==0)).sum());fn+=int((~pred&(y==1)).sum())
            if p['truth'] and (y==1).any():
                positive+=1;peak=int(p['frame_risk'].argmax());hits+=int(y[peak]==1)
        promotion=all(mean[k]>=self.plan['control'][k] for k in mean) and mean['accuracy']>self.plan['control']['accuracy']
        report={'version':VERSION,'protocol_sha256':self.plan['protocol_sha256'],'nested_metrics':nested_metrics,'nested_mean':mean,
                'comparisons':comparisons,'oof':result,'nested_oof':nested,'localization':{'weak_frame_precision':tp/max(1,tp+fp),
                'weak_frame_recall':tp/max(1,tp+fn),'weak_frame_f1':2*tp/max(1,2*tp+fp+fn),'positive_videos_with_intervals':positive,'peak_in_weak_interval':hits,
                'outside_positive_intervals':'unknown, not counted as confirmed false positives'},'promoted':promotion,
                'production_ready':False,'independent_external_test':False}
        atomic_json(self.directory/'cv_report.json',report)
        inner=self.crossfit(self.plan['final_inner']);choices={}
        for arm in ARMS:
            r=arm_rows(inner,arm);t=operations.clip_threshold(r);choices[arm]={'threshold':t,'metrics':metrics(r,t)}
        def rank(arm):
            m=choices[arm]['metrics'];return (min(m['accuracy'],m['balanced_accuracy'],m['macro_f1']),m['accuracy'],m['balanced_accuracy'],m['macro_f1'],-ARMS.index(arm))
        chosen=max(ARMS,key=rank);final,_=self.train(self.plan['development_ids'],42)
        atomic_checkpoint(self.directory/'final.pt',{**final,'selected_arm':chosen,'threshold':choices[chosen]['threshold'],
                                                   'event_threshold':calibrate_event(inner,self.rows),'protocol_sha256':self.plan['protocol_sha256']})
        atomic_json(self.directory/'complete.json',{'report_sha256':file_sha256(self.directory/'cv_report.json'),
            'fit_sha256':file_sha256(self.directory/'final.pt'),'promoted':promotion,'production_ready':False})
        print(json.dumps({'risk_mean':mean,'localization':report['localization'],'promoted':promotion,'arm':chosen}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--inputs',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('run');a.add_argument('--output',type=Path,required=True)
    args=p.parse_args();torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
    if args.command=='prepare':prepare(args.inputs,args.output)
    else:Experiment(args.output).run()


if __name__=='__main__':main()
