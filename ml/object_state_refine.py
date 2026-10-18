"""Train-only object ROI regression and translation-invariant bag appearance."""
from __future__ import annotations
import argparse,hashlib,json,time,zipfile,math
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from ml import state_focus as parent,object_events as original
from ml.data.annotation_tasks import read_json
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_checkpoint,atomic_json,metrics
from ml.small_data import summarize
from ml.action_refinement import auxiliary_metrics

VERSION='object-roi-states-v2'

def code_hash():return parent.stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),'parent':parent.code_hash()})

def multi_ridge(x,y,w,alpha):
    w=w/w.sum()*len(w);xm=(x*w[:,None]).sum(0)/w.sum();ym=(y*w[:,None]).sum(0)/w.sum();root=w.sqrt()
    a=(x-xm)*root[:,None];b=(y-ym)*root[:,None]
    if len(a)>a.shape[1]:
        coefficient=torch.linalg.solve(a.T@a+torch.eye(a.shape[1],device=x.device)*alpha,a.T@b)
    else:
        coefficient=a.T@torch.linalg.solve(a@a.T+torch.eye(len(a),device=x.device)*alpha,b)
    return {'weight':coefficient,'bias':ym-xm@coefficient}

def roi_pool(maps,boxes,size=3):
    if maps.ndim!=4 or boxes.shape!=(len(maps),4):raise ValueError('ROI shape')
    n=len(maps);unit=(torch.arange(size,device=maps.device)+.5)/size
    yy,xx=torch.meshgrid(unit,unit,indexing='ij');x0,y0,x1,y1=boxes.unbind(1)
    grid=torch.stack((x0[:,None,None]+xx*(x1-x0)[:,None,None],y0[:,None,None]+yy*(y1-y0)[:,None,None]),-1)
    return F.grid_sample(maps,grid*2-1,align_corners=False,padding_mode='border').flatten(1)

def pixels(row):
    cnn=torch.from_numpy(np.array(row['maps'][0],dtype=np.float32));color=torch.from_numpy(np.array(row['position_features'][:,parent.inputs.CNN_DIM:],copy=True)).reshape(-1,7,14,14)
    return torch.cat((cnn,color),1)

def source_weights(groups):
    g=torch.as_tensor(groups);w=torch.ones(len(g),device=g.device)
    unique,counts=torch.unique(g,return_counts=True)
    for group,count in zip(unique,counts):w[g==group]=1./count
    return w

def bbox_fit(rows,object_class,device):
    x=[];y=[];groups=[]
    for g,r in enumerate(rows):
        for n,boxes in enumerate(r['boxes']):
            matches=[b[1:] for b in boxes if b[0]==object_class]
            if matches:
                x.append(torch.from_numpy(np.array(r['position_features'][n,parent.inputs.CNN_DIM:],copy=True)))
                y.append(torch.tensor(matches[0]));groups.append(g)
    if not x:
        return {'normalization':{'mean':torch.zeros(1372),'scale':torch.ones(1372)},'weight':torch.zeros(1372,4),
                'bias':torch.tensor([.1,.1,.9,.9]),'supported':False}
    x=torch.stack(x).to(device);y=torch.stack(y).to(device);norm=parent.block_normalization(x,(1372,),.03);z=parent.normalize(x,norm)
    model=multi_ridge(z,y,source_weights(groups).to(device),10.)
    return {'normalization':{k:v.cpu() for k,v in norm.items()},**{k:v.cpu() for k,v in model.items()},'supported':True}

def bbox_predict(state,color):
    box=parent.normalize(color,state['normalization'])@state['weight']+state['bias']
    lower=torch.minimum(box[:,:2],box[:,2:]).clamp(0,.98);upper=torch.maximum(box[:,:2],box[:,2:]).clamp(.02,1.)
    upper=torch.maximum(upper,lower+.02).clamp_max(1)
    return torch.cat((lower,upper),1)

def bag_fit(rows,device,hard):
    samples=[];target=[];groups=[];sizes=[]
    for g,r in enumerate(rows):
        values=pixels(r)
        for n,boxes in enumerate(r['boxes']):
            bags=[b[1:] for b in boxes if b[0]==7]
            if bags:
                box=torch.tensor(bags[:1]);sizes.append((box[0,2:]-box[0,:2]).tolist())
                inner=box.clone();span=box[:,2:]-box[:,:2];inner[:,:2]+=span*.25;inner[:,2:]-=span*.25
                sample=roi_pool(values[n:n+1],inner,2).reshape(583,4).T
                samples.append(sample);target.extend([1.]*len(sample));groups.extend([g]*len(sample))
            elif bool(r['object_known'][n,7]) or r['actions'][n,18]==0:
                # Only explicit visible-workspace negatives supply background patches.
                chosen=torch.tensor([17,31,45,73,101,129,157,185]);sample=values[n].flatten(1)[:,chosen].T
                samples.append(sample);target.extend([0.]*len(sample));groups.extend([g]*len(sample))
    if not samples or len(set(target))<2:
        return {'normalization':{'mean':torch.zeros(583),'scale':torch.ones(583)},'weight':torch.zeros(583,1),'bias':torch.zeros(1),
                'median_size':torch.tensor([.15,.18]),'positive_patches':sum(v==1 for v in target),'negative_patches':sum(v==0 for v in target),'supported':False}
    x=torch.cat(samples).to(device);y=torch.tensor(target,device=device);g=torch.tensor(groups,device=device)
    norm=parent.block_normalization(x,(576,7),.03);z=parent.normalize(x,norm);w=parent.balanced_weights(y)
    for c in (0,1):
        mask=y==c;w[mask]=source_weights(g[mask]);w[mask]*=.5/w[mask].sum()
    model=multi_ridge(z,(2*y-1)[:,None],w,1.)
    if hard:
        margin=(z@model['weight']+model['bias']).squeeze(1);w=w*torch.where((y==0)&(margin>-.25),3.,1.)
        model=multi_ridge(z,(2*y-1)[:,None],w,1.)
    return {'normalization':{k:v.cpu() for k,v in norm.items()},**{k:v.cpu() for k,v in model.items()},
            'median_size':torch.tensor(sizes).median(0).values,'positive_patches':int((y==1).sum()),'negative_patches':int((y==0).sum()),'supported':True}

def bag_predict(state,values):
    x=values.permute(0,2,3,1).reshape(-1,583)
    margin=(parent.normalize(x,state['normalization'])@state['weight']+state['bias']).reshape(len(values),196)
    score=(3*margin.topk(3,1).values.mean(1)).sigmoid()*state['supported'];center=margin.argmax(1)
    xy=torch.stack(((center%14+.5)/14,(center//14+.5)/14),1);size=state['median_size']*1.5
    boxes=torch.cat((xy-size/2,xy+size/2),1).clamp(0,1)
    return score,boxes

def appearance_fit(values,targets,groups,hard,device):
    x=values.to(device);t=targets.to(device);g=groups.to(device);norm=parent.block_normalization(x,(576*9,7*9),.03);z=parent.normalize(x,norm)
    weight=[];bias=[];support=[]
    for c in range(t.shape[1]):
        mask=t[:,c]>=0;y=t[mask,c];enabled=bool((y==0).any() and (y==1).any());support.append(enabled)
        if not enabled:weight.append(torch.zeros(x.shape[1],device=device));bias.append(torch.zeros((),device=device));continue
        selected=z[mask];gg=g[mask];w=parent.balanced_weights(y)
        for v in (0,1):
            cls=y==v;w[cls]=source_weights(gg[cls]);w[cls]*=.5/w[cls].sum()
        model=parent.ridge(selected,2*y-1,w,1.)
        if hard:
            margin=selected@model['weight']+model['bias'];w*=torch.where((y==0)&(margin>-.25),2.,1.);model=parent.ridge(selected,2*y-1,w,1.)
        weight.append(model['weight']);bias.append(model['bias'])
    return {'normalization':{k:v.cpu() for k,v in norm.items()},'weight':torch.stack(weight,1).cpu(),'bias':torch.stack(bias).cpu(),'support':torch.tensor(support)}

def refine_predict(state,values,color,base_scores,base_support):
    result=torch.cat((base_scores,torch.zeros(len(values),2)),1);support=torch.cat((base_support,torch.zeros(2,dtype=torch.bool)))
    bag,bag_box=bag_predict(state['bag'],values);result[:,18]=bag;support[18]=state['bag']['supported']
    boxes={name:bbox_predict(state[name],color) for name in ('safe','laptop')};boxes['bag']=bag_box
    for name,classes in (('safe',(9,)),('laptop',(12,19)),('bag',(4,10))):
        crop=roi_pool(values,boxes[name]);model=state[name+'_appearance'];score=(3*(parent.normalize(crop,model['normalization'])@model['weight']+model['bias'])).sigmoid()
        for n,c in enumerate(classes):
            enabled=bool(model['support'][n]) and state[name]['supported'];result[:,c]=score[:,n]*enabled;support[c]=enabled
    return result,support,boxes

def prepare(parent_directory,output):
    old=read_json(Path(parent_directory)/'protocol.json')
    if old['code_sha256']!=parent.code_hash():raise ValueError('parent state protocol changed')
    p={**old,'version':VERSION,'parent_state':str(Path(parent_directory).resolve()),'code_sha256':code_hash(),
       'roi_fit':'train-only bbox ridge safe/laptop; bilinear3x3 CNN+color ROI appearance; train-only translation-invariant bag pixel ridge with explicit background negatives',
       'preserve_context':'frozen exact-train parent spatial heads for other actions/person/operator; no pixel/verdict lookup',
       'appearance_alpha':1.,'bbox_alpha':10.,'bag_alpha':1.,'bag_hard_negative_weight':3.,'production_ready':False}
    p.pop('protocol_sha256');p['protocol_sha256']=parent.stable_hash(p);out=Path(output);out.mkdir(parents=True,exist_ok=False);atomic_json(out/'protocol.json',p)
    with zipfile.ZipFile(out/'source_snapshot.zip','x',zipfile.ZIP_DEFLATED) as z:
        for name in ('object_state_refine.py','state_focus.py','state_focus_inputs.py'):z.write(Path(__file__).parent/name,'ml/'+name)
    print(json.dumps({'protocol_sha256':p['protocol_sha256']}),flush=True)

class Experiment(parent.Experiment):
    def __init__(self,directory,device='cuda'):
        p=read_json(Path(directory)/'protocol.json')
        if p['version']!=VERSION or p['code_sha256']!=code_hash() or p['protocol_sha256']!=parent.stable_hash({k:v for k,v in p.items() if k!='protocol_sha256'}):raise ValueError('ROI protocol changed')
        super().__init__(p['parent_state'],device);self.directory=Path(directory);self.plan=p;self.memo={}
        self.fits=self.directory/'fits';self.fits.mkdir(exist_ok=True)
        self.context=object.__new__(original.Experiment);self.context.plan=self.parent_plan;self.context.device=device;self.context.rows=self.rows;self.context.memo={}

    def context_path(self,ids):
        identity={'protocol':self.parent_plan['protocol_sha256'],'kind':'spatial','ids':sorted(ids),'seed':42}
        path=Path(self.plan['parent'])/'fits'/(parent.stable_hash(identity)+'.pt')
        if safe_torch_load(path)['identity']!=identity:raise ValueError('exact training context missing')
        return path

    def frame_fit(self,ids,hard):
        self.guard(ids);identity={'protocol':self.plan['protocol_sha256'],'kind':'roi_states','ids':sorted(ids),'hard':hard};path=self.fits/(parent.stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('ROI fit identity')
            return path
        started=time.perf_counter();rows=[self.rows[v] for v in ids]
        state={'bag':bag_fit(rows,self.device,hard),'safe':bbox_fit(rows,4,self.device),'laptop':bbox_fit(rows,1,self.device)}
        crops={k:[] for k in ('bag','safe','laptop')};targets={k:[] for k in crops};groups=[]
        for g,r in enumerate(rows):
            values=pixels(r);color=torch.from_numpy(np.array(r['position_features'][:,parent.inputs.CNN_DIM:],copy=True));_,bag=bag_predict(state['bag'],values)
            boxes={'bag':bag,**{name:bbox_predict(state[name],color) for name in ('safe','laptop')}}
            for name,classes in (('safe',(9,)),('laptop',(12,19)),('bag',(4,10))):
                crops[name].append(roi_pool(values,boxes[name]));targets[name].append(r['actions'][:,classes])
            groups.append(torch.full((len(values),),g))
        for name in crops:state[name+'_appearance']=appearance_fit(torch.cat(crops[name]),torch.cat(targets[name]),torch.cat(groups),hard,self.device)
        context=self.context_path(ids)
        atomic_checkpoint(path,{'format':VERSION,'identity':identity,'state':state,'context':str(context.resolve()),'context_sha256':file_sha256(context),'seconds':time.perf_counter()-started,'production_ready':False})
        print(json.dumps({'roi_states':len(ids),'hard':hard,'seconds':time.perf_counter()-started}),flush=True);return path

    def observations(self,path,ids):
        state=safe_torch_load(path)
        if state['identity']['protocol']!=self.plan['protocol_sha256'] or file_sha256(state['context'])!=state['context_sha256']:raise ValueError('ROI/context lineage')
        result=[]
        for video in ids:
            key=(path.stem,video)
            if key not in self.memo:
                r=self.rows[video];original_obs=self.context.observations(Path(state['context']),[video])[0]
                color=torch.from_numpy(np.array(r['position_features'][:,parent.inputs.CNN_DIM:],copy=True));values=pixels(r)
                p,support,boxes=refine_predict(state['state'],values,color,original_obs['states'],original_obs['support'])
                summary,risk,available=parent.state_summary(p,support)
                self.memo[key]={'video_id':video,'actions':p,'actions_supported':support,'visual':parent.visual_summary(torch.from_numpy(np.array(r['position_features'],copy=True))),
                                'states':summary,'rules':risk,'rule_support':available,'object_rois':boxes}
            result.append(self.memo[key])
        return result

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
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare');a.add_argument('--parent-state',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=s.add_parser('run');a.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
    if a.command=='prepare':prepare(a.parent_state,a.output)
    else:run(a.experiment)
