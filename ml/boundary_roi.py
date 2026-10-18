"""Magnified frozen-CNN state heads; clip labels never train object states."""
from __future__ import annotations
import argparse,hashlib,json,math,time,zipfile
from pathlib import Path
import numpy as np
import torch
from ml import boundary_temporal as parent,boundary_crop_inputs as data,object_state_refine as ridge
from ml.data.annotation_tasks import read_json
from ml.models.encoder import safe_torch_load,file_sha256
from ml.video_baseline import atomic_json,atomic_checkpoint,metrics
from ml.small_data import summarize
from ml.action_refinement import auxiliary_metrics
helpers=parent.helpers
VERSION='magnified-object-boundaries-v1'
ARMS=('roi_states','roi_blend','legacy_uniform')

def code_hash():return helpers.stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),'inputs':data.code_hash(),'parent':parent.code_hash()})

def frame_features(crops,bag):
    if crops.ndim!=3 or crops.shape[1:]!=(2,960) or bag.shape!=(len(crops),29) or not 1<=len(crops)<=360 or not torch.isfinite(crops).all() or not torch.isfinite(bag).all():raise ValueError('magnified frame features')
    safe=crops[:,0];n=min(3,len(safe));initial=safe[:n].cumsum(0)/torch.arange(1,n+1)[:,None]
    baseline=torch.cat((initial,initial[-1:].expand(len(safe)-n,-1)))
    held=torch.cat((crops[:,1],bag),1)
    return [torch.cat((safe,safe-baseline),1),bag[:,:19],held,held]

def fit_head(values,target,groups,blocks,alpha,device='cuda'):
    mask=target>=0;x=values[mask].to(device);y=target[mask].to(device);g=groups[mask].to(device);dimension=values.shape[1]
    if not bool((y==0).any() and (y==1).any()):
        return {'normalization':{'mean':torch.zeros(dimension),'scale':torch.ones(dimension)},'weight':torch.zeros(dimension),'bias':torch.zeros(()),'supported':False}
    norm=helpers.block_normalization(x,blocks,.01);z=helpers.normalize(x,norm);weight=torch.zeros_like(y)
    for value in (0,1):
        cls=y==value;weight[cls]=ridge.source_weights(g[cls]);weight[cls]*=.5/weight[cls].sum()
    model=ridge.multi_ridge(z,(2*y-1)[:,None],weight,alpha)
    return {'normalization':{k:v.cpu() for k,v in norm.items()},'weight':model['weight'][:,0].cpu().clone(),'bias':model['bias'][0].cpu().clone(),'supported':True}

def fit_states(rows,device='cuda'):
    arrays=[frame_features(r['crops'],r['bag']) for r in rows];targets=torch.cat([r['boundary_targets'] for r in rows]);groups=torch.cat([torch.full((len(r['crops']),),n) for n,r in enumerate(rows)])
    blocks=((576,384,576,384),(19,),(576,384,29),(576,384,29));alpha=(10.,.1,10.,10.)
    return [fit_head(torch.cat([a[c] for a in arrays]),targets[:,c],groups,blocks[c],alpha[c],device) for c in range(4)]

def predict_states(state,crops,bag,context,context_support):
    if context.shape!=(len(crops),18) or context_support.shape!=(18,):raise ValueError('exact-training spatial context shape')
    p=torch.zeros(len(crops),6);support=torch.zeros(6,dtype=torch.bool)
    for c,(head,x) in enumerate(zip(state,frame_features(crops,bag))):
        p[:,c]=(3*(helpers.normalize(x,head['normalization'])@head['weight']+head['bias'])).sigmoid()*head['supported'];support[c]=head['supported']
    p[:,4:]=context[:,[7,8]]*context_support[[7,8]];support[4:]=context_support[[7,8]]
    return p,support

def prepare(source,inputs,output):
    old=read_json(Path(source)/'protocol.json');marker,rows=data.load(inputs)
    if old['version']!=parent.VERSION or marker['parent_protocol_sha256']!=old['parent_protocol_sha256'] or marker['review_sha256']!=old['review_sha256'] or set(rows)!=set(old['development_ids']):raise ValueError('magnified source lineage')
    plan={**old,'version':VERSION,'boundary_parent':str(Path(source).resolve()),'inputs':str(Path(inputs).resolve()),'inputs_sha256':file_sha256(Path(inputs)/'inputs.json'),
          'code_sha256':code_hash(),'arms':list(ARMS),'config':{'state_alphas':[10.,.1,10.,10.],'clip_ridge_alpha':10.,'clip_labels_train_states':False,'source_balanced':True,'regions':[list(r) for r in data.REGIONS]},
          'selection':'same nested inner folds/rank; deterministic state/ridge fits; only frozen GRU varies by seed',
          'previous_negative_result_preserved':True,'production_ready':False}
    plan.pop('protocol_sha256');plan['protocol_sha256']=helpers.stable_hash(plan);out=Path(output);out.mkdir(parents=True,exist_ok=False);atomic_json(out/'protocol.json',plan)
    with zipfile.ZipFile(out/'source_snapshot.zip','x',zipfile.ZIP_DEFLATED) as z:
        for name in ('boundary_roi.py','boundary_crop_inputs.py'):z.write(Path(__file__).parent/name,'ml/'+name)
    print({'protocol_sha256':plan['protocol_sha256'],'arms':ARMS},flush=True)

class Experiment(parent.Experiment):
    def __init__(self,directory,device='cuda'):
        directory=Path(directory);plan=read_json(directory/'protocol.json')
        if plan['version']!=VERSION or plan['code_sha256']!=code_hash() or plan['arms']!=list(ARMS) or plan['protocol_sha256']!=helpers.stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'}):raise ValueError('magnified protocol changed')
        super().__init__(plan['boundary_parent'],device);self.directory=directory;self.plan=plan
        if file_sha256(Path(plan['inputs'])/'inputs.json')!=plan['inputs_sha256']:raise ValueError('magnified inputs changed')
        _,self.rows=data.load(plan['inputs']);self.fits=directory/'fits';self.fits.mkdir(exist_ok=True);self.memo={};self.context=parent.reference.Experiment(plan['parent'],device)

    def context_path(self,ids):
        identity={'protocol':self.parent['protocol_sha256'],'kind':'spatial','ids':sorted(ids),'seed':42}
        path=Path(self.plan['parent'])/'fits'/(helpers.stable_hash(identity)+'.pt')
        if not path.exists() and set(ids)==set(self.plan['development_ids']):path=Path(safe_torch_load(self.plan['reference_fit']['fit'])['spatial'])
        if safe_torch_load(path)['identity']!=identity:raise ValueError('missing exact-training state context')
        return path

    def fit(self,ids,seed=42):
        self.guard(ids);identity={'protocol':self.plan['protocol_sha256'],'kind':'magnified_states_readout','ids':sorted(ids)};path=self.fits/(helpers.stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('magnified fit identity')
            return path
        start=time.perf_counter();state=fit_states([self.rows[v] for v in sorted(ids)],self.device);context=self.context_path(ids)
        observations=self.frame_predictions(state,context,sorted(ids));summaries=torch.stack([parent.boundary_summary(p['actions']) for p in observations])
        readout=helpers.fit_readout(summaries,torch.tensor([self.rows[v]['target'] for v in sorted(ids)],dtype=torch.float32),[self.rows[v]['group_id'] for v in sorted(ids)],10.,[52])
        atomic_checkpoint(path,{'format':VERSION,'identity':identity,'state':state,'context':str(context.resolve()),'context_sha256':file_sha256(context),
                                'readout':readout,'seconds':time.perf_counter()-start,'production_ready':False})
        print({'fit':path.stem,'sources':len(ids),'seconds':time.perf_counter()-start},flush=True);return path

    def frame_predictions(self,state,context,ids):
        old=self.context.observations(Path(context),ids);result=[]
        for video,o in zip(ids,old):
            r=self.rows[video];p,support=predict_states(state,r['crops'],r['bag'],o['states'],o['support'])
            result.append({'video_id':video,'actions':p,'actions_supported':support})
        return result

    def observations(self,path,ids):
        checkpoint=safe_torch_load(path)
        if checkpoint['identity']['protocol']!=self.plan['protocol_sha256'] or file_sha256(checkpoint['context'])!=checkpoint['context_sha256']:raise ValueError('magnified checkpoint lineage')
        missing=[v for v in ids if (path.stem,v) not in self.memo]
        if missing:
            for o in self.frame_predictions(checkpoint['state'],checkpoint['context'],missing):
                o['ridge']=float(helpers.readout_predict(checkpoint['readout'],parent.boundary_summary(o['actions'])));self.memo[(path.stem,o['video_id'])]=o
        return [self.memo[(path.stem,v)] for v in ids]

    def predictions(self,train,ids,seed):
        observed=self.observations(self.fit(train),ids);old=self.reference(train,seed,ids);result={a:[] for a in ARMS}
        for o,g in zip(observed,old):
            for arm,value in zip(ARMS,(o['ridge'],.5*(o['ridge']+g),g)):
                result[arm].append({'video_id':o['video_id'],'truth':bool(self.rows[o['video_id']]['target']),'score':value})
        return result

    def choices(self,folds):
        pooled={a:[] for a in ARMS}
        for fold in folds:
            for arm,rows in self.predictions(fold['train'],fold['validation'],42).items():pooled[arm].extend(rows)
        choices={}
        for arm,rows in pooled.items():
            threshold=helpers.previous.previous.calibrate(rows);bce=float(np.mean([-math.log(max(1e-7,min(1-1e-7,r['score'] if r['truth'] else 1-r['score']))) for r in rows]))
            choices[arm]={'arm':arm,'threshold':threshold,'metrics':metrics(rows,threshold),'bce':bce,'oof':rows}
        return choices,max(choices.values(),key=helpers.previous.previous.rank)

def run(directory):
    torch.use_deterministic_algorithms(True);e=Experiment(directory);out=Path(directory)
    if (out/'complete.json').exists():raise ValueError('complete magnified experiment immutable')
    nested={str(s):[] for s in parent.SEEDS};comparisons={a:{str(s):[] for s in parent.SEEDS} for a in ARMS};frames=[];folds=[]
    for n,fold in enumerate(e.plan['folds']):
        choices,selected=e.choices(fold['inner'])
        frames.extend(e.observations(e.fit(fold['train']),fold['validation']))
        for seed in parent.SEEDS:
            for arm,rows in e.predictions(fold['train'],fold['validation'],seed).items():
                rows=[{**r,'threshold':choices[arm]['threshold'],'fold':n,'arm':arm} for r in rows];comparisons[arm][str(seed)].extend(rows)
                if arm==selected['arm']:nested[str(seed)].extend(rows)
        record={'fold':n,'choices':choices,'selected':selected['arm']};folds.append(record);atomic_json(out/f'outer-fold-{n}.json',record);print({'outer_done':n,'selected':selected['arm']},flush=True)
    choices,selected=e.choices(e.plan['final_inner']);fit=e.fit(e.plan['development_ids'])
    choice={'protocol_sha256':e.plan['protocol_sha256'],'selected':selected,'fit':str(fit.resolve()),'fit_sha256':file_sha256(fit),
            'reference_fit':e.plan['reference_fit'],'uses_reserved':False,'production_ready':False};atomic_json(out/'frozen_decision.json',choice)
    report={'version':VERSION,'nested_metrics':{s:summarize(p) for s,p in nested.items()},'comparisons':{a:{s:summarize(p) for s,p in ss.items()} for a,ss in comparisons.items()},
            'nested_oof':nested,'oof':comparisons,'folds':folds,'final_choices':choices,'frozen_decision':choice,
            'frame_metrics':auxiliary_metrics(frames,{v:{'actions':r['boundary_targets']} for v,r in e.rows.items()},'actions',parent.data.TAXONOMY),
            'event_metrics':parent.event_metrics(frames,e.rows,e.prepared),'state_fits_deterministic':True,'production_ready':False,'independent_external_test':False,'normative_status':'unknown'}
    atomic_checkpoint(out/'frame_oof.pt',{'format':VERSION,'observations':frames});atomic_json(out/'cv_report.json',report)
    atomic_json(out/'complete.json',{'report_sha256':file_sha256(out/'cv_report.json'),'decision_sha256':file_sha256(out/'frozen_decision.json')});print({'nested':report['nested_metrics'],'selected':selected['arm']},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare')
    for name in ('source','inputs','output'):a.add_argument('--'+name,type=Path,required=True)
    a=s.add_parser('run');a.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
    if a.command=='prepare':prepare(a.source,a.inputs,a.output)
    else:run(a.experiment)
