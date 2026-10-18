"""Observed state changes: constant classifier uncertainty is not departure."""
from __future__ import annotations
import argparse,hashlib,json,math,zipfile
from pathlib import Path
import numpy as np
import torch
from ml import object_state_local as core,state_focus as helpers
from ml.data.annotation_tasks import read_json
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,metrics
from ml.small_data import summarize

VERSION='observed-object-transitions-v1'
RULES=('bag_after_observed_departure','storage_visual_change_after_departure','bright_content_after_observed_departure','door_visual_change_after_entry')

def code_hash():return helpers.stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),'core':core.code_hash()})

def candidates():return [{'name':name,'arm':name,'hard':False,'alpha':1.} for name in ('transition','transition_blend','legacy_uniform')]

def probes(scores,support):
    if scores.ndim!=2 or scores.shape[1]!=20 or support.shape!=(20,) or len(scores)<1:raise ValueError('transition timeline')
    evidence=(2*(scores-.5)).clamp(0,1)*support;initial=evidence[:min(3,len(scores))].mean(0)
    tail=evidence[-min(3,len(scores)):];departure=((evidence[:,7].amax()-tail[:,7].amax()-.2)/.8).clamp(0,1)
    person_absent=(2*(.5-scores[:,8])).clamp(0,1)
    bag=helpers.rolling_minimum(evidence[:,18]*person_absent)[-min(8,len(scores)):].mean()*departure
    change=((evidence[:,9]-initial[9]-.15)/.85).clamp(0,1)
    storage=helpers.rolling_minimum(change)[-min(8,len(scores)):].mean()*departure
    screen=helpers.rolling_minimum(evidence[:,19])[-min(8,len(scores)):].mean()*departure
    door_change=((evidence[:,13]-initial[13]-.15)/.85).clamp(0,1)
    door=helpers.rolling_minimum(door_change*evidence[:,7])[-max(1,len(scores)//2):].mean()*evidence[:,5].amax()
    required=((18,7,8),(9,7),(19,7),(13,7,5));available=torch.tensor([len(scores)>=3 and all(bool(support[c]) for c in r) for r in required])
    return torch.stack((bag,storage,screen,door))*available,available

def prepare(source,preregister,output):
    source=Path(source);p=read_json(source/'protocol.json');pre=read_json(preregister);marker=read_json(source/'complete.json')
    if pre['source_protocol_sha256']!=p['protocol_sha256'] or pre['prior_internal_holdout_results_used'] is not False or file_sha256(source/'frozen_decision.json')!=marker['decision_sha256']:raise ValueError('transition preregistration/lineage')
    plan={**p,'version':VERSION,'source_consensus':str(source.resolve()),'code_sha256':code_hash(),'candidates':candidates(),
          'preregister_sha256':file_sha256(preregister),'transition_rules':list(RULES),'departure_drop':.2,'state_change':.15,
          'selection':'same inner folds/rank,three predeclared alternatives; no reserved threshold fitting','production_ready':False}
    plan.pop('protocol_sha256');plan['protocol_sha256']=helpers.stable_hash(plan);out=Path(output);out.mkdir(parents=True,exist_ok=False);atomic_json(out/'protocol.json',plan)
    (out/'source_snapshot.py').write_text(Path(__file__).read_text(encoding='utf-8-sig'),encoding='utf-8');print(json.dumps({'protocol_sha256':plan['protocol_sha256']}),flush=True)

def predictions(e,train_ids,video_ids,seed):
    frame=e.frame_fit(train_ids,False);observed=e.observations(frame,video_ids);old=e.reference(train_ids,seed,video_ids);result={c['name']:[] for c in candidates()}
    for o,g in zip(observed,old):
        risk,_=probes(o['actions'],o['actions_supported']);p=float(risk.amax());video=o['video_id'];truth=bool(e.rows[video]['target'])
        for name,value in (('transition',p),('transition_blend',.5*(p+g)),('legacy_uniform',g)):
            result[name].append({'video_id':video,'truth':truth,'score':value})
    return result

def choices(e,folds):
    rows={c['name']:[] for c in candidates()}
    for fold in folds:
        p=predictions(e,fold['train'],fold['validation'],42)
        for name in rows:rows[name].extend(p[name])
    result={}
    for c in candidates():
        pred=rows[c['name']];threshold=helpers.previous.previous.calibrate(pred)
        bce=float(np.mean([-math.log(max(1e-7,min(1-1e-7,p['score'] if p['truth'] else 1-p['score']))) for p in pred]))
        result[c['name']]={'arm':c['name'],'candidate':c,'threshold':threshold,'metrics':metrics(pred,threshold),'bce':bce,'oof':pred}
    return result,max(result.values(),key=helpers.previous.previous.rank)

def run(directory):
    out=Path(directory);p=read_json(out/'protocol.json')
    if p['code_sha256']!=code_hash() or p['protocol_sha256']!=helpers.stable_hash({k:v for k,v in p.items() if k!='protocol_sha256'}):raise ValueError('transition code/protocol changed')
    if (out/'complete.json').exists():raise ValueError('transition stage complete')
    e=core.Experiment(p['roi_parent']);nested={str(s):[] for s in helpers.SEEDS};comp={c['name']:{str(s):[] for s in helpers.SEEDS} for c in candidates()};folds=[]
    for n,fold in enumerate(p['folds']):
        available,selected=choices(e,fold['inner'])
        for seed in helpers.SEEDS:
            pp=predictions(e,fold['train'],fold['validation'],seed)
            for name,rows in pp.items():
                rows=[{**v,'threshold':available[name]['threshold'],'fold':n,'arm':name} for v in rows];comp[name][str(seed)].extend(rows)
                if name==selected['arm']:nested[str(seed)].extend(rows)
        record={'fold':n,'choices':available,'selected':selected['arm']};folds.append(record);atomic_json(out/f'outer-fold-{n}.json',record);print(json.dumps({'outer_done':n,'selected':selected['arm']}),flush=True)
    available,selected=choices(e,p['final_inner']);base_c=next(c for c in helpers.candidates() if c['name']=='persistent_base')
    # This exact final state/readout already exists in the frozen local parent.
    identity={'protocol':e.plan['protocol_sha256'],'kind':'clip','ids':sorted(p['development_ids']),'candidate':base_c};fit=e.fits/(helpers.stable_hash(identity)+'.pt')
    if not fit.exists() or safe_torch_load(fit)['identity']!=identity:raise ValueError('frozen final persistent readout missing')
    reference=None
    if selected['arm'] in ('legacy_uniform','transition_blend'):
        e.directory=out;e.reference(p['development_ids'],42,p['development_ids']);reference=read_json(out/'final_reference.json')
    choice={'selected':selected,'base_candidate':base_c,'fit':str(fit.resolve()),'fit_sha256':file_sha256(fit),'reference_fit':reference,
            'protocol_sha256':p['protocol_sha256'],'uses_reserved':False,'production_ready':False}
    atomic_json(out/'frozen_decision.json',choice)
    report={'version':VERSION,'nested_metrics':{s:summarize(v) for s,v in nested.items()},'comparisons':{a:{s:summarize(v) for s,v in ss.items()} for a,ss in comp.items()},
            'nested_oof':nested,'oof':comp,'folds':folds,'final_choices':available,'frozen_decision':choice,'deterministic_state_heads':True,
            'production_ready':False,'independent_external_test':False,'normative_status':'unknown'}
    atomic_json(out/'cv_report.json',report);atomic_json(out/'complete.json',{'report_sha256':file_sha256(out/'cv_report.json'),'decision_sha256':file_sha256(out/'frozen_decision.json')});print(json.dumps({'nested':report['nested_metrics'],'selected':selected['arm']}),flush=True)

class Experiment:
    def __init__(self,directory):
        self.directory=Path(directory);self.plan=read_json(self.directory/'protocol.json');self.choice=read_json(self.directory/'frozen_decision.json')
        marker=read_json(self.directory/'complete.json')
        if self.plan['code_sha256']!=code_hash() or file_sha256(self.directory/'frozen_decision.json')!=marker['decision_sha256'] or file_sha256(self.choice['fit'])!=self.choice['fit_sha256']:raise ValueError('transition decision changed')
        self.base=core.Experiment(self.plan['roi_parent']);self.legacy=None
    def predict(self,ids):
        fit=safe_torch_load(self.choice['fit']);obs=self.base.observations(Path(fit['frame_fit']),ids);old=None;reference=self.choice['reference_fit']
        if reference:
            from ml import object_events
            self.legacy=object_events.Experiment(self.plan['parent']);old=[v['gru'] for v in self.legacy.predict(Path(reference['fit']),ids)]
        rows=[]
        for n,o in enumerate(obs):
            risk,_=probes(o['actions'],o['actions_supported']);score=float(risk.amax());name=self.choice['selected']['arm']
            if name=='legacy_uniform':score=old[n]
            elif name=='transition_blend':score=.5*(score+old[n])
            rows.append({'video_id':o['video_id'],'truth':bool(self.base.rows[o['video_id']]['target']),'score':score})
        return rows

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare')
    for name in ('source','preregister','output'):a.add_argument('--'+name,type=Path,required=True)
    a=s.add_parser('run');a.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
    if a.command=='prepare':prepare(a.source,a.preregister,a.output)
    else:run(a.experiment)
