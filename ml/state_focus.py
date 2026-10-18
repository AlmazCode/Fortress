"""Position-preserving state heads, hard negatives and regularized clip readouts."""
from __future__ import annotations
import argparse,hashlib,json,math,time,zipfile
from pathlib import Path
import numpy as np
import torch
from ml import state_focus_inputs as inputs,object_events as previous
from ml.action_refinement import auxiliary_metrics
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint,metrics
from ml.small_data import summarize

VERSION='positional-state-hard-negatives-v1'
SEEDS=(42,137,2026)
FRAME_ALPHA=10.
CLIP_ALPHAS=(.1,1.,10.)
COMMON=(0,1,2,3,4,7,8,9,10,12,13,18,19)
RULES=('bag_after_departure','storage_open_after_departure','bright_content_after_departure','persistent_open_door',
       'counter_after_person_departure','bag_then_flat_item','device_then_storage')

def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'inputs':inputs.code_hash(),'parent':previous.code_hash()})

def candidates():
    result=[{'name':f'visual_{a:g}','arm':'visual','hard':False,'alpha':a} for a in CLIP_ALPHAS]
    for hard in (False,True):
        for arm in ('states','fused','blend'):
            result.extend({'name':f'{arm}_{"hard" if hard else "base"}_{a:g}','arm':arm,'hard':hard,'alpha':a} for a in CLIP_ALPHAS)
        result.append({'name':'persistent_'+('hard' if hard else 'base'),'arm':'persistent','hard':hard,'alpha':1.})
    return result

def block_normalization(values,blocks,minimum=.1):
    if values.ndim!=2 or sum(blocks)!=values.shape[1] or not torch.isfinite(values).all():raise ValueError('finite feature blocks required')
    mean=values.mean(0);std=values.std(0,unbiased=False).clamp_min(minimum)
    scales=torch.cat([torch.full((n,),math.sqrt(n),device=values.device) for n in blocks])
    return {'mean':mean,'scale':std*scales}

def normalize(values,state):return (values-state['mean'])/state['scale']

def ridge(values,targets,weights,alpha):
    """Weighted least squares, unpenalized intercept, compact primal result."""
    if values.ndim!=2 or targets.shape!=(len(values),) or weights.shape!=targets.shape or len(values)<2 or alpha<=0 or not torch.isfinite(values).all() or not torch.isfinite(targets).all() or not torch.isfinite(weights).all() or (weights<=0).any():raise ValueError('invalid ridge inputs')
    w=weights/weights.sum()*len(weights);xm=(values*w[:,None]).sum(0)/w.sum();ym=(targets*w).sum()/w.sum()
    root=w.sqrt();x=(values-xm)*root[:,None];y=(targets-ym)*root
    kernel=x@x.T;dual=torch.linalg.solve(kernel+torch.eye(len(x),device=x.device)*alpha,y)
    coefficient=x.T@dual;bias=ym-xm@coefficient
    if not torch.isfinite(coefficient).all() or not torch.isfinite(bias):raise ValueError('nonfinite ridge solution')
    return {'weight':coefficient,'bias':bias}

def balanced_weights(target):
    if not (target==0).any() or not (target==1).any():raise ValueError('both classes required')
    return torch.where(target.bool(),.5/(target==1).sum(),.5/(target==0).sum())

def state_fit(values,targets,video_indices,hard=False,device='cuda'):
    x=values.to(device);t=targets.to(device);groups=video_indices.to(device)
    norm=block_normalization(x,(inputs.CNN_DIM,inputs.COLOR_DIM));x=normalize(x,norm)
    heads=[];bias=[];enabled=[]
    for c in range(t.shape[1]):
        mask=t[:,c]>=0;y=t[mask,c]
        supported=bool((y==0).any() and (y==1).any());enabled.append(supported)
        if not supported:
            heads.append(torch.zeros(x.shape[1],device=device));bias.append(torch.zeros((),device=device));continue
        selected=x[mask];g=groups[mask];w=balanced_weights(y)
        # Equal contribution per source within each class reduces long-video dominance.
        for value in (0,1):
            cls=y==value;unique,counts=torch.unique(g[cls],return_counts=True)
            for group,count in zip(unique,counts):w[cls&(g==group)]=.5/(len(unique)*count)
        model=ridge(selected,2*y-1,w,FRAME_ALPHA)
        if hard:
            margin=selected@model['weight']+model['bias']
            w=w*torch.where((y==0)&(margin>-.25),2.,1.)
            model=ridge(selected,2*y-1,w,FRAME_ALPHA)
        heads.append(model['weight']);bias.append(model['bias'])
    return {'normalization':{k:v.cpu() for k,v in norm.items()},'weight':torch.stack(heads,1).cpu(),
            'bias':torch.stack(bias).cpu(),'support':torch.tensor(enabled,dtype=torch.bool),'hard_negatives':hard,
            'scores_are_calibrated_probabilities':False}

def state_predict(state,values):
    if values.ndim!=2 or values.shape[1]!=len(state['normalization']['mean']) or not torch.isfinite(values).all():raise ValueError('invalid state features')
    with torch.inference_mode():margin=normalize(values,state['normalization'])@state['weight']+state['bias']
    return (3*margin).sigmoid()*state['support']

def rolling_minimum(values,window=3):
    w=min(window,len(values))
    return values.unfold(0,w,1).amin(-1)

def state_summary(scores,support):
    if scores.ndim!=2 or scores.shape[1]!=20 or len(scores)<1 or support.shape!=(20,):raise ValueError('state timeline shape')
    p=scores*support;tail=p[-min(8,len(p)):];q=p[:max(1,len(p)//4)]
    common=p[:,COMMON];persist=rolling_minimum(common)
    summary=torch.cat((common.mean(0),common.amax(0),common.std(0,unbiased=False),tail[:,COMMON].mean(0),
                       tail[:,COMMON].mean(0)-q[:,COMMON].mean(0),persist.amax(0)))
    risks=[];available=[];operator=p[:,7];presence=operator.amax();absent=1-operator
    departure=presence*(1-operator[-min(3,len(p)):]).amin()
    def add(value,requires):
        enabled=all(bool(support[c]) for c in requires);available.append(enabled);risks.append(value if enabled else value*0)
    add(rolling_minimum(p[:,18]*p[:,10]*absent)[-min(8,len(p)):].mean()*presence,(18,10,7))
    add(rolling_minimum(p[:,9]*absent)[-min(8,len(p)):].mean()*presence,(9,7))
    add(rolling_minimum(p[:,19])[-min(8,len(p)):].mean()*departure,(19,7))
    add(rolling_minimum(p[:,13]*operator)[-max(1,len(p)//2):].mean(),(13,7))
    add(rolling_minimum(p[:,1]*(1-p[:,8])*operator)[-min(8,len(p)):].mean(),(1,8,7))
    past=p[:,4].cumsum(0)/torch.arange(1,len(p)+1)
    add((past*p[:,0]).amax(),(4,0))
    past=p[:,1].cumsum(0)/torch.arange(1,len(p)+1)
    add((past*p[:,3]).amax(),(1,3))
    return torch.cat((summary,torch.stack(risks))),torch.stack(risks),torch.tensor(available,dtype=torch.bool)

def visual_summary(values):
    if values.ndim!=2 or len(values)<1:raise ValueError('visual timeline shape')
    n=max(1,len(values)//4)
    return torch.cat((values.mean(0),values.std(0,unbiased=False),values[-n:].mean(0)-values[:n].mean(0)))

def visual_blocks():return [inputs.CNN_DIM,inputs.COLOR_DIM]*3

def readout_features(arm,visual,states):
    if arm=='visual':return visual,visual_blocks()
    if arm in ('states','persistent'):return states,[states.shape[-1]]
    if arm in ('fused','blend'):return torch.cat((visual,states),-1),visual_blocks()+[states.shape[-1]]
    raise ValueError('unsupported clip arm')

def fit_readout(values,targets,groups,alpha,blocks):
    norm=block_normalization(values,blocks);x=normalize(values,norm);y=2*targets-1;w=balanced_weights(targets)
    pairs=[]
    for n in range(len(y)):
        for m in range(n):
            if groups[n]==groups[m] and targets[n]!=targets[m]:
                d=(x[n]-x[m])*.5;v=(y[n]-y[m])*.5
                pairs.extend(((d,v),(-d,-v)))
    if pairs:
        px=torch.stack([p[0] for p in pairs]);py=torch.stack([p[1] for p in pairs])
        w=torch.cat((w,torch.full((len(pairs),),.5/len(pairs))))
        x=torch.cat((x,px));y=torch.cat((y,py))
    return {**ridge(x,y,w,alpha),'normalization':norm,'training_pairs':len(pairs)//2}

def readout_predict(state,values):return (3*(normalize(values,state['normalization'])@state['weight']+state['bias'])).sigmoid()

def prepare(parent,directory,review,output):
    plan=read_json(Path(parent)/'protocol.json');doc,rows,marker,labels=inputs.load(plan,directory,review)
    groups={r['video_id']:r['group_id'] for r in rows}
    previous.validate_folds(plan['folds'],plan['development_ids'],groups)
    for f in plan['folds']:previous.validate_folds(f['inner'],f['train'],groups)
    previous.validate_folds(plan['final_inner'],plan['development_ids'],groups)
    p={'version':VERSION,'parent':str(Path(parent).resolve()),'parent_protocol_sha256':plan['protocol_sha256'],
       'inputs':str(Path(directory).resolve()),'inputs_sha256':file_sha256(Path(directory)/'inputs.json'),
       'review':str(Path(review).resolve()),'review_sha256':file_sha256(review),'code_sha256':code_hash(),
       'folds':plan['folds'],'final_inner':plan['final_inner'],'development_ids':plan['development_ids'],'reserved_ids':plan['reserved_ids'],
       'candidates':candidates(),'state_alpha':FRAME_ALPHA,'primary_seed':42,'seeds':list(SEEDS),
       'state_fit':'deterministic balanced weighted ridge; source-equal classes; optional2x explicitly negative hard examples margin>-.25; no verdict input',
       'clip_fit':'balanced ridge with train-family opposite-verdict contrast pairs; train-only normalization',
       'cup_prior':'diagnostic only; excluded from new state/rule/readout features; reference GRU retains original frozen metadata',
       'appearance_not_os_state':True,'selection':'same inner folds; max min(acc,BA,macroF1),thenacc,BA,F1,lowerBCE',
       'target':'mean acc/BA/macroF1>=.80 with36/36coverage; repeatedly used development benchmark,not independent external test',
       'production_ready':False,'normative_status':'unknown','original_verdicts_changed':False}
    p['protocol_sha256']=stable_hash(p);out=Path(output);out.mkdir(parents=True,exist_ok=False);atomic_json(out/'protocol.json',p)
    with zipfile.ZipFile(out/'source_snapshot.zip','x',zipfile.ZIP_DEFLATED) as z:
        for name in ('state_focus.py','state_focus_inputs.py'):z.write(Path(__file__).parent/name,'ml/'+name)
    print(json.dumps({'protocol_sha256':p['protocol_sha256']}),flush=True)

class Experiment:
    def __init__(self,directory,device='cuda'):
        torch.set_num_threads(4);self.directory=Path(directory);self.plan=read_json(self.directory/'protocol.json');self.device=device
        if self.plan['code_sha256']!=code_hash() or self.plan['protocol_sha256']!=stable_hash({k:v for k,v in self.plan.items() if k!='protocol_sha256'}):raise ValueError('state protocol changed')
        self.parent_plan=read_json(Path(self.plan['parent'])/'protocol.json')
        if self.parent_plan['protocol_sha256']!=self.plan['parent_protocol_sha256'] or file_sha256(Path(self.plan['inputs'])/'inputs.json')!=self.plan['inputs_sha256'] or file_sha256(self.plan['review'])!=self.plan['review_sha256']:raise ValueError('state inputs changed')
        _,rows,_,_=inputs.load(self.parent_plan,self.plan['inputs'],self.plan['review']);self.rows={r['video_id']:r for r in rows}
        self.fits=self.directory/'fits';self.fits.mkdir(exist_ok=True);self.memo={};self.old={}
        ref=read_json(Path(self.plan['parent'])/'cv_report.json');mark=read_json(Path(self.plan['parent'])/'complete.json')
        if file_sha256(Path(self.plan['parent'])/'cv_report.json')!=mark['report_sha256']:raise ValueError('reference CV changed')
        for n,fold in enumerate(self.plan['folds']):
            for seed in SEEDS:
                self.old.setdefault((tuple(sorted(fold['train'])),seed),{}).update({p['video_id']:p['score'] for p in ref['oof']['uniform_gru'][str(seed)] if p['fold']==n})
            for inner in fold['inner']:
                self.old.setdefault((tuple(sorted(inner['train'])),42),{}).update({p['video_id']:p['score'] for p in ref['folds'][n]['choices']['uniform_gru']['oof'] if p['video_id'] in inner['validation']})
        for inner in self.plan['final_inner']:
            self.old.setdefault((tuple(sorted(inner['train'])),42),{}).update({p['video_id']:p['score'] for p in ref['final_choices']['uniform_gru']['oof'] if p['video_id'] in inner['validation']})

    def guard(self,ids):
        if not ids or len(set(ids))!=len(ids) or not set(ids)<=set(self.plan['development_ids']):raise ValueError('unique development sources required')

    def frame_fit(self,ids,hard):
        self.guard(ids);identity={'protocol':self.plan['protocol_sha256'],'kind':'states','ids':sorted(ids),'hard':hard}
        path=self.fits/(stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('frame fit identity')
            return path
        started=time.perf_counter();values=[];targets=[];groups=[]
        for group,video in enumerate(ids):
            r=self.rows[video];mask=(r['actions']>=0).any(1);values.append(torch.from_numpy(np.array(r['position_features'][mask],copy=True)))
            targets.append(r['actions'][mask]);groups.append(torch.full((int(mask.sum()),),group))
        state=state_fit(torch.cat(values),torch.cat(targets),torch.cat(groups),hard,self.device)
        atomic_checkpoint(path,{'format':VERSION,'identity':identity,'state':state,'seconds':time.perf_counter()-started,'production_ready':False})
        print(json.dumps({'states':len(ids),'hard':hard,'seconds':time.perf_counter()-started}),flush=True);return path

    def observations(self,path,ids):
        state=safe_torch_load(path)
        if state['identity']['protocol']!=self.plan['protocol_sha256']:raise ValueError('frame model lineage')
        result=[]
        for video in ids:
            key=(path.stem,video)
            if key not in self.memo:
                x=torch.from_numpy(np.array(self.rows[video]['position_features'],copy=True));p=state_predict(state['state'],x)
                summary,risk,support=state_summary(p,state['state']['support'])
                self.memo[key]={'video_id':video,'actions':p,'actions_supported':state['state']['support'],
                                'visual':visual_summary(x),'states':summary,'rules':risk,'rule_support':support}
            result.append(self.memo[key])
        return result

    def fit(self,ids,candidate):
        self.guard(ids);identity={'protocol':self.plan['protocol_sha256'],'kind':'clip','ids':sorted(ids),'candidate':candidate}
        path=self.fits/(stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('clip fit identity')
            return path
        frame=self.frame_fit(ids,candidate['hard']);obs=self.observations(frame,ids)
        visual=torch.stack([o['visual'] for o in obs]);states=torch.stack([o['states'] for o in obs]);arm=candidate['arm']
        features,blocks=readout_features(arm,visual,states)
        readout=None if arm=='persistent' else fit_readout(features,torch.tensor([self.rows[v]['target'] for v in ids],dtype=torch.float32),[self.rows[v]['group_id'] for v in ids],candidate['alpha'],blocks)
        atomic_checkpoint(path,{'format':VERSION,'identity':identity,'frame_fit':str(frame.resolve()),'frame_sha256':file_sha256(frame),
                                'readout':readout,'production_ready':False});return path

    def reference(self,ids,seed,video_ids):
        key=(tuple(sorted(ids)),seed)
        if key not in self.old:
            if set(ids)!=set(self.plan['development_ids']):raise ValueError('missing exact train-only reference predictions')
            original=previous.Experiment(self.plan['parent']);original.fits=self.directory/'reference_fits';original.fits.mkdir(exist_ok=True)
            fitted=original.fit(ids,'uniform',seed);atomic_json(self.directory/'final_reference.json',{'fit':str(fitted.resolve()),'sha256':file_sha256(fitted)})
            self.old[key]={p['video_id']:p['gru'] for p in original.predict(fitted,video_ids)}
        if not set(video_ids)<=set(self.old[key]):raise ValueError('reference validation coverage')
        return [self.old[key][v] for v in video_ids]

    def predict(self,path,ids,seed=42):
        state=safe_torch_load(path);identity=state['identity'];c=identity['candidate']
        if identity['protocol']!=self.plan['protocol_sha256'] or file_sha256(state['frame_fit'])!=state['frame_sha256']:raise ValueError('clip lineage')
        obs=self.observations(Path(state['frame_fit']),ids)
        x,_=readout_features(c['arm'],torch.stack([o['visual'] for o in obs]),torch.stack([o['states'] for o in obs]))
        if c['arm']=='persistent':scores=[float(o['rules'][:4].amax()) for o in obs]
        else:scores=readout_predict(state['readout'],x).tolist()
        if c['arm']=='blend':scores=[.5*(a+b) for a,b in zip(scores,self.reference(identity['ids'],seed,ids))]
        return [{'video_id':v,'truth':bool(self.rows[v]['target']),'score':float(p)} for v,p in zip(ids,scores)]

    def choices(self,folds):
        choices={}
        for c in self.plan['candidates']:
            rows=[]
            for fold in folds:rows.extend(self.predict(self.fit(fold['train'],c),fold['validation']))
            threshold=previous.previous.calibrate(rows);bce=float(np.mean([-math.log(max(1e-7,min(1-1e-7,p['score'] if p['truth'] else 1-p['score']))) for p in rows]))
            choices[c['name']]={'arm':c['name'],'candidate':c,'threshold':threshold,'metrics':metrics(rows,threshold),'bce':bce,'oof':rows}
        return choices,max(choices.values(),key=previous.previous.rank)

def run(directory):
    torch.use_deterministic_algorithms(True);e=Experiment(directory);out=Path(directory)
    if (out/'complete.json').exists():raise ValueError('complete experiment immutable')
    nested={str(s):[] for s in SEEDS};comparisons={c['name']:{str(s):[] for s in SEEDS} for c in e.plan['candidates']};folds=[];frames={False:[],True:[]}
    for n,fold in enumerate(e.plan['folds']):
        choices,selected=e.choices(fold['inner'])
        for hard in (False,True):frames[hard].extend(e.observations(e.frame_fit(fold['train'],hard),fold['validation']))
        for seed in SEEDS:
            for c in e.plan['candidates']:
                rows=[{**p,'threshold':choices[c['name']]['threshold'],'fold':n,'arm':c['name']} for p in e.predict(e.fit(fold['train'],c),fold['validation'],seed)]
                comparisons[c['name']][str(seed)].extend(rows)
                if c['name']==selected['arm']:nested[str(seed)].extend(rows)
        record={'fold':n,'choices':choices,'selected':selected['arm']};folds.append(record);atomic_json(out/f'outer-fold-{n}.json',record)
        print(json.dumps({'outer_done':n,'selected':selected['arm']}),flush=True)
    choices,selected=e.choices(e.plan['final_inner']);fit=e.fit(e.plan['development_ids'],selected['candidate'])
    if selected['candidate']['arm']=='blend':e.reference(e.plan['development_ids'],42,e.plan['development_ids'])
    choice={'selected':selected,'fit':str(fit.resolve()),'fit_sha256':file_sha256(fit),'protocol_sha256':e.plan['protocol_sha256'],'uses_reserved':False,'production_ready':False}
    atomic_json(out/'frozen_decision.json',choice)
    report={'version':VERSION,'nested_metrics':{s:summarize(p) for s,p in nested.items()},'comparisons':{a:{s:summarize(p) for s,p in ss.items()} for a,ss in comparisons.items()},
            'nested_oof':nested,'oof':comparisons,'folds':folds,'final_choices':choices,'frozen_decision':choice,
            'state_oof':{str(hard):auxiliary_metrics(obs,e.rows,'actions',inputs.TAXONOMY) for hard,obs in frames.items()},
            'deterministic_state_and_ridge_heads':True,'seed_sensitivity':'Only frozen reference GRU varies by seed; deterministic arms reuse identical fits.',
            'production_ready':False,'independent_external_test':False,'normative_status':'unknown'}
    atomic_checkpoint(out/'state_oof.pt',{'format':VERSION,'frames':{str(k):v for k,v in frames.items()}})
    atomic_json(out/'cv_report.json',report);atomic_json(out/'complete.json',{'report_sha256':file_sha256(out/'cv_report.json'),'decision_sha256':file_sha256(out/'frozen_decision.json')})
    print(json.dumps({'nested':report['nested_metrics'],'selected':selected['arm']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare')
    for name in ('parent','inputs','review','output'):a.add_argument('--'+name,type=Path,required=True)
    a=s.add_parser('run');a.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
    if a.command=='prepare':prepare(a.parent,a.inputs,a.review,a.output)
    else:run(a.experiment)
