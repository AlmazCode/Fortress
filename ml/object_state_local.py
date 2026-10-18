"""Camera-anchor ROIs and position-invariant green-bag color evidence."""
from __future__ import annotations
import argparse,hashlib,json,time,zipfile
from pathlib import Path
import numpy as np
import torch
from ml import object_state_refine as base,state_focus as helpers,object_events as original
from ml.data.annotation_tasks import read_json
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_checkpoint,atomic_json,metrics
from ml.small_data import summarize
from ml.action_refinement import auxiliary_metrics

VERSION='camera-anchor-object-states-v1'
RULES=('visible_bag_after_departure',)+helpers.RULES[1:]

def code_hash():return helpers.stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),'base':base.code_hash()})

def color_signature(color):
    rgb=color[:,:588].reshape(-1,3,196);r,g,b=rgb.unbind(1);green=torch.minimum(g-r,g-b);ratio=green/(r+g+b+.03)
    values=[green.topk(k,1).values.mean(1) for k in (1,3,10)]
    values.extend((green>t).float().mean(1) for t in (.005,.01,.015,.025,.035,.05))
    values.extend(green.clamp_min(t).mean(1)-t for t in (0.,.01,.02))
    values.extend(ratio.topk(k,1).values.mean(1) for k in (1,3,10))
    values.extend((ratio>t).float().mean(1) for t in (.01,.02,.03,.05))
    return torch.stack(values,1)

def presence_fit(rows,hard):
    x=[];y=[];groups=[]
    for g,r in enumerate(rows):
        values=color_signature(torch.from_numpy(np.array(r['position_features'][:,helpers.inputs.CNN_DIM:],copy=True)))
        for n in range(len(values)):
            label=float(r['actions'][n,18])
            if label<0 and bool(r['object_known'][n,7]):label=float(any(b[0]==7 for b in r['boxes'][n]))
            if label>=0:x.append(values[n]);y.append(label);groups.append(g)
    dim=19
    if not x or len(set(y))<2:return {'normalization':{'mean':torch.zeros(dim),'scale':torch.ones(dim)},'weight':torch.zeros(dim),'bias':torch.zeros(()),'supported':False}
    x=torch.stack(x);y=torch.tensor(y);g=torch.tensor(groups);norm=helpers.block_normalization(x,(dim,),.003);z=helpers.normalize(x,norm);w=helpers.balanced_weights(y)
    for c in (0,1):
        mask=y==c;w[mask]=base.source_weights(g[mask]);w[mask]*=.5/w[mask].sum()
    model=helpers.ridge(z,2*y-1,w,.1)
    if hard:
        margin=z@model['weight']+model['bias'];w*=torch.where((y==0)&(margin>-.25),2.,1.);model=helpers.ridge(z,2*y-1,w,.1)
    return {'normalization':norm,**model,'supported':True}

def bag_fit(rows,device,hard):
    samples=[];target=[];groups=[];sizes=[];rng=np.random.default_rng(20261018)
    for g,r in enumerate(rows):
        values=base.pixels(r)
        for n,boxes in enumerate(r['boxes']):
            bags=[b[1:] for b in boxes if b[0]==7]
            if bags:
                box=torch.tensor(bags[:1]);sizes.append((box[0,2:]-box[0,:2]).tolist());inner=box.clone();span=box[:,2:]-box[:,:2]
                inner[:,:2]+=span*.25;inner[:,2:]-=span*.25;sample=base.roi_pool(values[n:n+1],inner,2).reshape(583,4).T
                samples.append(sample);target.extend([1.]*len(sample));groups.extend([g]*len(sample))
            elif bool(r['object_known'][n,7]) or r['actions'][n,18]==0:
                chosen=torch.tensor(rng.choice(196,8,replace=False));sample=values[n].flatten(1)[:,chosen].T
                samples.append(sample);target.extend([0.]*len(sample));groups.extend([g]*len(sample))
    if not samples or len(set(target))<2:
        return {'normalization':{'mean':torch.zeros(583),'scale':torch.ones(583)},'weight':torch.zeros(583,1),'bias':torch.zeros(1),
                'median_size':torch.tensor([.15,.18]),'positive_patches':sum(v==1 for v in target),'negative_patches':sum(v==0 for v in target),'supported':False}
    x=torch.cat(samples).to(device);y=torch.tensor(target,device=device);g=torch.tensor(groups,device=device);norm=helpers.block_normalization(x,(576,7),.03);z=helpers.normalize(x,norm);w=helpers.balanced_weights(y)
    for c in (0,1):
        mask=y==c;w[mask]=base.source_weights(g[mask]);w[mask]*=.5/w[mask].sum()
    model=base.multi_ridge(z,(2*y-1)[:,None],w,1.)
    if hard:
        margin=(z@model['weight']+model['bias']).squeeze(1);w*=torch.where((y==0)&(margin>-.25),3.,1.);model=base.multi_ridge(z,(2*y-1)[:,None],w,1.)
    return {'normalization':{k:v.cpu() for k,v in norm.items()},**{k:v.cpu() for k,v in model.items()},'median_size':torch.tensor(sizes).median(0).values,
            'positive_patches':int((y==1).sum()),'negative_patches':int((y==0).sum()),'supported':True}

def bbox_fit(rows,object_class):
    x=[];y=[]
    for r in rows:
        boxes=[b[1:] for frame in r['boxes'] for b in frame if b[0]==object_class]
        if boxes:
            x.append(torch.from_numpy(np.array(r['position_features'][:3,helpers.inputs.CNN_DIM:],copy=True)).mean(0));y.append(torch.tensor(boxes).median(0).values)
    if not x:return {'normalization':{'mean':torch.zeros(1372),'scale':torch.ones(1372)},'weight':torch.zeros(1372,4),'bias':torch.tensor([.1,.1,.9,.9]),'supported':False}
    x=torch.stack(x);norm=helpers.block_normalization(x,(1372,),.03)
    yy,xx=torch.meshgrid(torch.arange(14),torch.arange(14),indexing='ij');background=(yy<3)|(xx<2)|(xx>11)
    mask=torch.where(background,1.,.05).repeat(7,1,1).flatten()
    return {'normalization':norm,'weight':torch.zeros(1372,4),'bias':torch.stack(y).median(0).values,'supported':True,
            'anchors':helpers.normalize(x,norm),'boxes':torch.stack(y),'distance_weight':mask}

def bbox_predict(state,color):
    if not state['supported']:return base.bbox_predict(state,color)
    value=helpers.normalize(color[:min(3,len(color))].mean(0),state['normalization']);distance=((state['anchors']-value).square()*state['distance_weight']).sum(1)
    return state['boxes'][distance.argmin()][None].expand(len(color),-1).clone()

def expanded(box,name):
    if name!='safe':return box
    span=box[:,2:]-box[:,:2]
    return torch.cat((box[:,:2]-span*torch.tensor([.6,.1]),box[:,2:]+span*torch.tensor([.1,.1])),1).clamp(0,1)

def refine_predict(state,values,color,base_scores,base_support):
    result=torch.cat((base_scores,torch.zeros(len(values),2)),1);support=torch.cat((base_support,torch.zeros(2,dtype=torch.bool)))
    _,bag_box=base.bag_predict(state['bag'],values);presence=state['bag_presence'];signature=color_signature(color)
    result[:,18]=(3*(helpers.normalize(signature,presence['normalization'])@presence['weight']+presence['bias'])).sigmoid()*presence['supported'];support[18]=presence['supported']
    boxes={name:bbox_predict(state[name],color) for name in ('safe','laptop')};boxes['bag']=bag_box
    for name,classes in (('safe',(9,)),('laptop',(12,19)),('bag',(4,10))):
        crop=base.roi_pool(values,expanded(boxes[name],name));model=state[name+'_appearance'];score=(3*(helpers.normalize(crop,model['normalization'])@model['weight']+model['bias'])).sigmoid()
        for n,c in enumerate(classes):
            enabled=bool(model['support'][n]) and state[name]['supported'];result[:,c]=score[:,n]*enabled;support[c]=enabled
    door=state['door_state'];position=helpers.inputs.combine(values[:,:576],color)
    result[:,13]=(3*(helpers.normalize(position,door['normalization'])@door['weight']+door['bias'])).sigmoid()*door['supported'];support[13]=door['supported']
    return result,support,boxes

def state_summary(scores,support):
    summary,risk,available=helpers.state_summary(scores,support);enabled=all(bool(support[c]) for c in (18,7,8));p=scores*support
    value=helpers.rolling_minimum(p[:,18]*(1-p[:,7])*(1-p[:,8]))[-min(8,len(p)):].mean()*p[:,7].amax()
    risk[0]=value if enabled else 0.;available[0]=enabled;summary[-len(risk):]=risk
    return summary,risk,available

def prepare(parent_directory,output):
    old=read_json(Path(parent_directory)/'protocol.json')
    if old['code_sha256']!=base.code_hash():raise ValueError('ROI parent code changed')
    p={**old,'version':VERSION,'local_parent':str(Path(parent_directory).resolve()),'code_sha256':code_hash(),
       'bbox_fit':'nearest train-source camera anchor from first3 color observations; background weighted; median provided boxes; no video ID lookup',
       'bag_presence':'19 translation-invariant color/chroma summaries; source-balanced ridge alpha.1; explicit reviewed frame labels only',
       'negative_sampling':'uniform deterministic8 pixels per known-negative frame over all196 locations',
       'safe_state_roi':'expand safe box .6width left,.1right,.1height vertically to include moving door',
       'door_context':'exact-train positional head for door; frozen original spatial context for other supported actions',
       'bag_probe':'visible bag with operator/person absent after observed operator presence; physical proxy only, normative unknown'}
    p.pop('protocol_sha256');p['protocol_sha256']=helpers.stable_hash(p);out=Path(output);out.mkdir(parents=True,exist_ok=False);atomic_json(out/'protocol.json',p)
    with zipfile.ZipFile(out/'source_snapshot.zip','x',zipfile.ZIP_DEFLATED) as z:
        for name in ('object_state_local.py','object_state_refine.py','state_focus.py','state_focus_inputs.py'):z.write(Path(__file__).parent/name,'ml/'+name)
    print(json.dumps({'protocol_sha256':p['protocol_sha256']}),flush=True)

class Experiment(base.Experiment):
    def __init__(self,directory,device='cuda'):
        p=read_json(Path(directory)/'protocol.json')
        if p['version']!=VERSION or p['code_sha256']!=code_hash() or p['protocol_sha256']!=helpers.stable_hash({k:v for k,v in p.items() if k!='protocol_sha256'}):raise ValueError('local object protocol changed')
        helpers.Experiment.__init__(self,p['parent_state'],device);self.directory=Path(directory);self.plan=p;self.memo={};self.fits=self.directory/'fits';self.fits.mkdir(exist_ok=True)
        self.context=object.__new__(original.Experiment);self.context.plan=self.parent_plan;self.context.device=device;self.context.rows=self.rows;self.context.memo={}

    def frame_fit(self,ids,hard):
        self.guard(ids);identity={'protocol':self.plan['protocol_sha256'],'kind':'roi_states','ids':sorted(ids),'hard':hard};path=self.fits/(helpers.stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('local fit identity')
            return path
        started=time.perf_counter();rows=[self.rows[v] for v in ids]
        state={'bag':bag_fit(rows,self.device,hard),'bag_presence':presence_fit(rows,hard),'safe':bbox_fit(rows,4),'laptop':bbox_fit(rows,1)}
        crops={k:[] for k in ('bag','safe','laptop')};targets={k:[] for k in crops};groups=[]
        for g,r in enumerate(rows):
            values=base.pixels(r);color=torch.from_numpy(np.array(r['position_features'][:,helpers.inputs.CNN_DIM:],copy=True));_,bag=base.bag_predict(state['bag'],values)
            boxes={'bag':bag,**{name:bbox_predict(state[name],color) for name in ('safe','laptop')}}
            for name,classes in (('safe',(9,)),('laptop',(12,19)),('bag',(4,10))):
                crops[name].append(base.roi_pool(values,expanded(boxes[name],name)));targets[name].append(r['actions'][:,classes])
            groups.append(torch.full((len(values),),g))
        for name in crops:state[name+'_appearance']=base.appearance_fit(torch.cat(crops[name]),torch.cat(targets[name]),torch.cat(groups),hard,self.device)
        positional_plan=read_json(Path(self.plan['parent_state'])/'protocol.json')
        pid={'protocol':positional_plan['protocol_sha256'],'kind':'states','ids':sorted(ids),'hard':hard};existing=Path(self.plan['parent_state'])/'fits'/(helpers.stable_hash(pid)+'.pt')
        if not existing.exists():
            positional=helpers.Experiment(self.plan['parent_state'],self.device);positional.fits=self.directory/'positional_final';positional.fits.mkdir(exist_ok=True)
            existing=positional.frame_fit(ids,hard)
        door_checkpoint=safe_torch_load(existing)
        if door_checkpoint['identity']!=pid:raise ValueError('door training source identity')
        door=door_checkpoint['state']
        state['door_state']={'normalization':door['normalization'],'weight':door['weight'][:,13],'bias':door['bias'][13],'supported':bool(door['support'][13])}
        context=self.context_path(ids);atomic_checkpoint(path,{'format':VERSION,'identity':identity,'state':state,'context':str(context.resolve()),'context_sha256':file_sha256(context),'seconds':time.perf_counter()-started,'production_ready':False})
        print(json.dumps({'local_states':len(ids),'hard':hard,'seconds':time.perf_counter()-started}),flush=True);return path

    def observations(self,path,ids):
        state=safe_torch_load(path)
        if state['identity']['protocol']!=self.plan['protocol_sha256'] or file_sha256(state['context'])!=state['context_sha256']:raise ValueError('local/context lineage')
        result=[]
        for video in ids:
            key=(path.stem,video)
            if key not in self.memo:
                r=self.rows[video];old=self.context.observations(Path(state['context']),[video])[0];color=torch.from_numpy(np.array(r['position_features'][:,helpers.inputs.CNN_DIM:],copy=True));values=base.pixels(r)
                p,support,boxes=refine_predict(state['state'],values,color,old['states'],old['support']);summary,risk,available=state_summary(p,support)
                self.memo[key]={'video_id':video,'actions':p,'actions_supported':support,'visual':helpers.visual_summary(torch.from_numpy(np.array(r['position_features'],copy=True))),
                                'states':summary,'rules':risk,'rule_support':available,'object_rois':boxes}
            result.append(self.memo[key])
        return result


parent=helpers

def run(directory):
    torch.use_deterministic_algorithms(True);e=Experiment(directory);out=Path(directory)
    if (out/'complete.json').exists():raise ValueError('complete ROI experiment immutable')
    nested={str(s):[] for s in parent.SEEDS};comparisons={c['name']:{str(s):[] for s in parent.SEEDS} for c in e.plan['candidates']};folds=[];frames={False:[],True:[]}
    for n,fold in enumerate(e.plan['folds']):
        choices,selected=e.choices(fold['inner'])
        for hard in (False,True):frames[hard].extend(e.observations(e.frame_fit(fold['train'],hard),fold['validation']))
        for seed in parent.SEEDS:
            for c in e.plan['candidates']:
                rows=[{**p,'threshold':choices[c['name']]['threshold'],'fold':n,'arm':c['name']} for p in e.predict(e.fit(fold['train'],c),fold['validation'],seed)]
                comparisons[c['name']][str(seed)].extend(rows)
                if c['name']==selected['arm']:nested[str(seed)].extend(rows)
        record={'fold':n,'choices':choices,'selected':selected['arm']};folds.append(record);atomic_json(out/f'outer-fold-{n}.json',record);print(json.dumps({'outer_done':n,'selected':selected['arm']}),flush=True)
    choices,selected=e.choices(e.plan['final_inner']);fit=e.fit(e.plan['development_ids'],selected['candidate'])
    if selected['candidate']['arm']=='blend':e.reference(e.plan['development_ids'],42,e.plan['development_ids'])
    choice={'selected':selected,'fit':str(fit.resolve()),'fit_sha256':file_sha256(fit),'protocol_sha256':e.plan['protocol_sha256'],'uses_reserved':False,'production_ready':False};atomic_json(out/'frozen_decision.json',choice)
    report={'version':VERSION,'nested_metrics':{s:summarize(p) for s,p in nested.items()},'comparisons':{a:{s:summarize(p) for s,p in ss.items()} for a,ss in comparisons.items()},
            'nested_oof':nested,'oof':comparisons,'folds':folds,'final_choices':choices,'frozen_decision':choice,
            'state_oof':{str(h):auxiliary_metrics(obs,e.rows,'actions',parent.inputs.TAXONOMY) for h,obs in frames.items()},
            'deterministic_state_and_ridge_heads':True,'seed_sensitivity':'Only frozen reference GRU varies by seed; deterministic arms reuse identical fits.',
            'production_ready':False,'independent_external_test':False,'normative_status':'unknown'}
    atomic_checkpoint(out/'state_oof.pt',{'format':VERSION,'frames':{str(k):v for k,v in frames.items()}})
    atomic_json(out/'cv_report.json',report);atomic_json(out/'complete.json',{'report_sha256':file_sha256(out/'cv_report.json'),'decision_sha256':file_sha256(out/'frozen_decision.json')});print(json.dumps({'nested':report['nested_metrics'],'selected':selected['arm']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare');a.add_argument('--parent',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=s.add_parser('run');a.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
    if a.command=='prepare':prepare(a.parent,a.output)
    else:run(a.experiment)
