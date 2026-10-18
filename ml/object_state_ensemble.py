"""Preregistered state-only/GRU ensembles using frozen family-fold predictions."""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from ml import object_state_refine as core,state_focus as helpers,object_events as original
from ml.data.annotation_tasks import read_json
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,metrics
from ml.small_data import summarize

VERSION='roi-state-readout-ensemble-v1'

def code_hash():return helpers.stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),'core':core.code_hash()})

def candidates():
    result=[{'name':'legacy_uniform','arm':'legacy_uniform','hard':False,'alpha':1.}]
    for hard in (False,True):
        for arm in ('states','state_blend'):
            result.extend({'name':f'{arm}_{"hard" if hard else "base"}_{a:g}','arm':arm,'hard':hard,'alpha':a} for a in helpers.CLIP_ALPHAS)
        for arm in ('persistent','policy_blend'):result.append({'name':arm+'_'+('hard' if hard else 'base'),'arm':arm,'hard':hard,'alpha':1.})
    return result

def base_candidate(candidate):
    arm={'state_blend':'states','policy_blend':'persistent','legacy_uniform':'persistent'}.get(candidate['arm'],candidate['arm'])
    return next(c for c in helpers.candidates() if c['arm']==arm and c['hard']==candidate['hard'] and c['alpha']==candidate['alpha'])

def merge(candidate,states,legacy):
    a={p['video_id']:p for p in states};b={p['video_id']:p for p in legacy}
    if len(a)!=len(states) or len(b)!=len(legacy) or set(a)!=set(b):raise ValueError('ensemble source coverage mismatch')
    rows=[]
    for video,p in a.items():
        if p['truth']!=b[video]['truth']:raise ValueError('ensemble truth mismatch')
        if candidate['arm']=='legacy_uniform':score=b[video]['score']
        elif candidate['arm'] in ('state_blend','policy_blend'):score=.5*(p['score']+b[video]['score'])
        else:score=p['score']
        rows.append({'video_id':video,'truth':p['truth'],'score':score})
    return rows

def prepare(parent,preregister,clarification,output):
    p=read_json(Path(parent)/'protocol.json');pre=read_json(preregister);extra=read_json(clarification)
    if pre['parent_protocol_sha256']!=p['protocol_sha256'] or pre['parent_complete_existed'] is not False or pre['reserved_not_evaluated_this_stage'] is not True or extra['parent_complete_existed'] is not False or extra['preregister_sha256']!=file_sha256(preregister):raise ValueError('ensemble preregistration mismatch')
    plan={**p,'version':VERSION,'roi_parent':str(Path(parent).resolve()),'roi_protocol_sha256':p['protocol_sha256'],
          'preregister_sha256':file_sha256(preregister),'clarification_sha256':file_sha256(clarification),'code_sha256':code_hash(),'candidates':candidates(),
          'ensemble':'equal mean of state-only score or persistent score and exact-train uniform GRU; old uniform control; no new outer fits',
          'production_ready':False}
    plan.pop('protocol_sha256');plan['protocol_sha256']=helpers.stable_hash(plan);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    atomic_json(out/'protocol.json',plan);(out/'source_snapshot.py').write_text(Path(__file__).read_text(encoding='utf-8-sig'),encoding='utf-8')
    print(json.dumps({'protocol_sha256':plan['protocol_sha256']}),flush=True)

def load_parent(plan):
    out=Path(plan['roi_parent']);marker=read_json(out/'complete.json')
    if read_json(out/'protocol.json')['protocol_sha256']!=plan['roi_protocol_sha256'] or file_sha256(out/'cv_report.json')!=marker['report_sha256'] or file_sha256(out/'frozen_decision.json')!=marker['decision_sha256']:raise ValueError('frozen ROI parent changed')
    return read_json(out/'cv_report.json')

def choices(plan,new_choices,legacy):
    result={}
    for c in plan['candidates']:
        rows=merge(c,new_choices[base_candidate(c)['name']]['oof'],legacy['oof']);threshold=helpers.previous.previous.calibrate(rows)
        bce=float(np.mean([-math.log(max(1e-7,min(1-1e-7,p['score'] if p['truth'] else 1-p['score']))) for p in rows]))
        result[c['name']]={'arm':c['name'],'candidate':c,'threshold':threshold,'metrics':metrics(rows,threshold),'bce':bce,'oof':rows}
    return result,max(result.values(),key=helpers.previous.previous.rank)

def run(directory):
    out=Path(directory);p=read_json(out/'protocol.json')
    if p['code_sha256']!=code_hash() or p['protocol_sha256']!=helpers.stable_hash({k:v for k,v in p.items() if k!='protocol_sha256'}):raise ValueError('ensemble code/protocol changed')
    if (out/'complete.json').exists():raise ValueError('complete ensemble immutable')
    report=load_parent(p);legacy=read_json(Path(p['parent'])/'cv_report.json');parent_marker=file_sha256(Path(p['roi_parent'])/'complete.json')
    nested={str(s):[] for s in helpers.SEEDS};all_rows={c['name']:{str(s):[] for s in helpers.SEEDS} for c in p['candidates']};folds=[]
    for n,fold in enumerate(p['folds']):
        available,selected=choices(p,report['folds'][n]['choices'],legacy['folds'][n]['choices']['uniform_gru'])
        for seed in helpers.SEEDS:
            old=[v for v in legacy['oof']['uniform_gru'][str(seed)] if v['fold']==n]
            for c in p['candidates']:
                new=[v for v in report['oof'][base_candidate(c)['name']][str(seed)] if v['fold']==n]
                rows=[{**v,'threshold':available[c['name']]['threshold'],'fold':n,'arm':c['name']} for v in merge(c,new,old)]
                all_rows[c['name']][str(seed)].extend(rows)
                if c['name']==selected['arm']:nested[str(seed)].extend(rows)
        record={'fold':n,'choices':available,'selected':selected['arm']};folds.append(record);atomic_json(out/f'outer-fold-{n}.json',record)
    available,selected=choices(p,report['final_choices'],legacy['final_choices']['uniform_gru'])
    # Only a final all-development refit may be missing. Write it separately and
    # preserve every completed parent fit/report/decision.
    e=core.Experiment(p['roi_parent']);old_fits=e.fits;e.fits=out/'final_fits';e.fits.mkdir(exist_ok=True);e.directory=out
    frame_fit=e.frame_fit
    def existing_frame(ids,hard):
        identity={'protocol':e.plan['protocol_sha256'],'kind':'roi_states','ids':sorted(ids),'hard':hard};path=old_fits/(helpers.stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('final frame identity mismatch')
            return path
        return frame_fit(ids,hard)
    e.frame_fit=existing_frame
    base_c=base_candidate(selected['candidate']);fit=e.fit(p['development_ids'],base_c)
    if selected['candidate']['arm'] in ('legacy_uniform','state_blend','policy_blend'):
        existing=Path(p['roi_parent'])/'final_reference.json'
        if existing.exists():reference=read_json(existing)
        else:
            e.reference(p['development_ids'],42,p['development_ids']);reference=read_json(out/'final_reference.json')
        if file_sha256(reference['fit'])!=reference['sha256']:raise ValueError('final reference changed')
    else:reference=None
    choice={'selected':selected,'base_candidate':base_c,'fit':str(fit.resolve()),'fit_sha256':file_sha256(fit),'reference_fit':reference,
            'protocol_sha256':p['protocol_sha256'],'uses_reserved':False,'production_ready':False}
    if file_sha256(Path(p['roi_parent'])/'complete.json')!=parent_marker:raise ValueError('completed parent was modified')
    atomic_json(out/'frozen_decision.json',choice)
    result={'version':VERSION,'nested_metrics':{s:summarize(v) for s,v in nested.items()},'comparisons':{a:{s:summarize(v) for s,v in ss.items()} for a,ss in all_rows.items()},
            'nested_oof':nested,'oof':all_rows,'folds':folds,'final_choices':available,'frozen_decision':choice,
            'deterministic_roi_heads':True,'seed_sensitivity':'Only exact-train uniform GRU varies by seed; deterministic states reuse identical fits.',
            'production_ready':False,'independent_external_test':False,'normative_status':'unknown'}
    atomic_json(out/'cv_report.json',result);atomic_json(out/'complete.json',{'report_sha256':file_sha256(out/'cv_report.json'),'decision_sha256':file_sha256(out/'frozen_decision.json')})
    print(json.dumps({'nested':result['nested_metrics'],'selected':selected['arm']}),flush=True)

class Experiment:
    def __init__(self,directory):
        self.directory=Path(directory);self.plan=read_json(self.directory/'protocol.json')
        if self.plan['code_sha256']!=code_hash():raise ValueError('ensemble code changed')
        load_parent(self.plan);self.base=core.Experiment(self.plan['roi_parent']);self.choice=read_json(self.directory/'frozen_decision.json')
        marker=read_json(self.directory/'complete.json')
        if file_sha256(self.directory/'frozen_decision.json')!=marker['decision_sha256'] or file_sha256(self.choice['fit'])!=self.choice['fit_sha256']:raise ValueError('ensemble fit changed')
        self.legacy=None
    def predict(self,ids):
        new=self.base.predict(Path(self.choice['fit']),ids);reference=self.choice['reference_fit']
        if reference:
            if self.legacy is None:self.legacy=original.Experiment(self.plan['parent'])
            if file_sha256(reference['fit'])!=reference['sha256']:raise ValueError('reference changed')
            old=[{**v,'score':v['gru']} for v in self.legacy.predict(Path(reference['fit']),ids)]
        else:old=new
        return merge(self.choice['selected']['candidate'],new,old)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare')
    for name in ('parent','preregister','clarification','output'):a.add_argument('--'+name,type=Path,required=True)
    a=s.add_parser('run');a.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
    if a.command=='prepare':prepare(a.parent,a.preregister,a.clarification,a.output)
    else:run(a.experiment)
