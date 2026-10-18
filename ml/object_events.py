"""Object localization, causal actions and explicit experimental rule probes."""
from __future__ import annotations
import argparse,hashlib,json,math,time,zipfile
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence,pad_packed_sequence,pad_sequence
from ml import object_event_inputs as data
from ml import action_focus as previous
from ml.action_refinement import auxiliary_weights,auxiliary_metrics
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256,safe_torch_load
from ml.small_data import summarize
from ml.video_baseline import atomic_json,atomic_checkpoint,metrics

VERSION='spatial-object-events-v1'
SEEDS=(42,137,2026)
ARMS=('uniform_gru','objects_gru','rules_linear','policy_fixed','hybrid_linear','hybrid_fixed')
CONFIG={'frame_epochs':16,'frame_lr':.001,'pretrain_epochs':40,'epochs':80,'lr':.0003,'dropout':.5,'weight_decay':.05}
STATE_OBJECT=(2,3,1,4,7,-1,5,-1,-1,4,7,1,1,-1,-1,8,8,9)
RULE_NAMES=('bag_unattended','storage_open_unattended','screen_lit_unattended','cup_to_mouth','visible_cup',
            'garment_on_desk','persistent_open_door','cash_after_person_departure','journal_unattended','box_unattended',
            'storage_after_device_interaction','bag_after_flat_item')

def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'inputs':data.code_hash(),'previous':previous.code_hash()})

def loss_masked(logits,target,weight):
    known=(target>=0)&weight['enabled'];raw=nn.functional.binary_cross_entropy_with_logits(logits,target.clamp_min(0),reduction='none',pos_weight=weight['positive_weight'])
    count=known.sum(tuple(range(target.ndim-1)));scale=(count>0).float()
    return (((raw*known).sum(tuple(range(target.ndim-1)))/count.clamp_min(1))*scale).sum()/scale.sum().clamp_min(1)

def cup_background_calibration(scores):
    values=np.asarray(scores,dtype=np.float64)
    if values.ndim!=1 or not len(values) or not np.isfinite(values).all() or (values<0).any() or (values>1).any():raise ValueError('known negative prior scores required')
    high=max(1e-6,float(np.quantile(values,.99)));low=max(1e-9,float(np.quantile(values,.9)))
    return torch.tensor([math.log(high),max(.25,math.log(high)-math.log(low))],dtype=torch.float32)

def calibrate_cup_prior(values,calibration):
    return ((values.clamp_min(1e-9).log()-calibration[0])/calibration[1]).sigmoid()

def object_targets(boxes,known,size=14):
    heat=torch.zeros(len(boxes),len(data.OBJECTS),size,size);reg=torch.zeros(len(boxes),len(data.OBJECTS),4,size,size);mask=torch.zeros_like(heat,dtype=torch.bool)
    yy,xx=torch.meshgrid(torch.arange(size),torch.arange(size),indexing='ij')
    for n,items in enumerate(boxes):
        for cls,x0,y0,x1,y1 in items:
            cx,cy=(x0+x1)/2,(y0+y1)/2;ix,iy=min(size-1,int(cx*size)),min(size-1,int(cy*size))
            sigma=max(.6,min(2.,max(x1-x0,y1-y0)*size/6))
            heat[n,cls]=torch.maximum(heat[n,cls],torch.exp(-((xx-ix)**2+(yy-iy)**2)/(2*sigma*sigma)))
            reg[n,cls,:,iy,ix]=torch.tensor([cx*size-ix,cy*size-iy,x1-x0,y1-y0]);mask[n,cls,iy,ix]=True
    return heat,reg,mask,known

class SpatialHeads(nn.Module):
    def __init__(self):
        super().__init__();k=len(data.OBJECTS);self.shared=nn.Sequential(nn.Conv2d(576,96,1),nn.ReLU())
        self.heat=nn.Conv2d(96,k,1);self.box=nn.Conv2d(96,4*k,1)
        self.state_weight=nn.Parameter(torch.empty(len(data.TAXONOMY),576));nn.init.normal_(self.state_weight,std=.02)
        self.state_bias=nn.Parameter(torch.zeros(len(data.TAXONOMY)))
        self.register_buffer('object_support',torch.ones(k,dtype=torch.bool))
        self.register_buffer('state_support',torch.ones(len(data.TAXONOMY),dtype=torch.bool))

    def forward(self,values):
        if values.ndim!=4 or values.shape[1:]!=(576,14,14) or not torch.isfinite(values).all():raise ValueError('invalid spatial maps')
        hidden=self.shared(values);heat=self.heat(hidden);boxes=self.box(hidden).reshape(len(values),len(data.OBJECTS),4,14,14).sigmoid()
        attention=(heat*4).flatten(2).softmax(-1).reshape_as(heat)
        tokens=torch.einsum('nkhw,nchw->nkc',attention,values);global_token=values.mean((-2,-1))
        state_tokens=torch.stack([tokens[:,c] if c>=0 else global_token for c in STATE_OBJECT],1)
        state=(state_tokens*self.state_weight[None]).sum(-1)+self.state_bias
        probability=heat.sigmoid().flatten(2).amax(-1)*self.object_support
        context=(tokens*probability[...,None]).sum(1)/probability.sum(1,keepdim=True).clamp_min(1e-5)
        focused=.5*global_token+.5*context
        center=heat.flatten(2).argmax(-1)
        selected=boxes.flatten(3).gather(3,center[:,:,None,None].expand(-1,-1,4,1)).squeeze(-1)
        selected=torch.stack(((center%14+selected[:,:,0])/14,(center//14+selected[:,:,1])/14,selected[:,:,2],selected[:,:,3]),2)
        selected=selected*self.object_support[None,:,None]
        meta=torch.cat((state.sigmoid()*self.state_support,probability,selected.flatten(1)),1)
        return heat,boxes,state,global_token,focused,meta

def frame_loss(output,target,actions,state_weights):
    heat,boxes,state=output[:3];truth,reg,centers,known=target
    expanded=known[...,None,None]
    raw=nn.functional.binary_cross_entropy_with_logits(heat,truth,reduction='none')
    focal=(heat.sigmoid()-truth).abs().pow(2)
    heat_loss=(raw*focal*(1+19*truth)*expanded).sum()/(expanded.sum()*14*14).clamp_min(1)
    bbox_loss=nn.functional.smooth_l1_loss(boxes,reg,reduction='none').mean(2)
    bbox_loss=(bbox_loss*centers).sum()/centers.sum().clamp_min(1)
    return heat_loss+2*bbox_loss+loss_masked(state,actions,state_weights)

def rule_features(states,objects,prior,support,object_support=None):
    """Observable soft combinations; missing prerequisites stay unavailable."""
    if states.ndim!=2 or len(states)<1 or states.shape[1]!=18:raise ValueError('invalid rule timeline')
    n=len(states);tail=slice(max(0,n-8),n);p=states*support
    absent=1-p[:,7];safe=1-p[:,8]
    if object_support is None:object_support=torch.ones(10,dtype=torch.bool,device=states.device)
    available=[];values=[]
    def add(value,requires):
        enabled=all(bool(support[c]) for c in requires);available.append(enabled);values.append(value if enabled else value*0.)
    add((p[:,10]*absent)[tail].mean(),(10,7));add((p[:,9]*absent)[tail].mean(),(9,7))
    add((p[:,12]*absent)[tail].mean(),(12,7));add(p[:,16].topk(min(3,n)).values.mean(),(16,))
    # The frozen ImageNet cup prior is an unvalidated observation feature, not a
    # legal trigger or training label. Its support is distinguished in diagnostics.
    cup=torch.maximum(p[:,15],prior.flatten(1).amax(-1))
    values.append(cup.topk(min(3,n)).values.mean());available.append(True)
    add(p[:,17][tail].mean(),(17,));add((p[:,13]*p[:,7])[-max(1,n//2):].mean(),(13,7))
    for value,requires,obj in (((objects[:,2]*safe*p[:,7])[tail].mean(),(8,7),2),((objects[:,5]*absent)[tail].mean(),(7,),5),((objects[:,6]*absent)[tail].mean(),(7,),6)):
        enabled=all(bool(support[c]) for c in requires) and bool(object_support[obj]);available.append(enabled);values.append(value if enabled else value*0.)
    past=p[:,1].cumsum(0)/torch.arange(1,n+1,device=p.device)
    add((p[:,3]*past).amax(),(3,1))
    past=p[:,0].cumsum(0)/torch.arange(1,n+1,device=p.device)
    add((p[:,4]*past).amax(),(4,0))
    return torch.cat((torch.stack(values),torch.tensor(available,device=p.device,dtype=p.dtype)))

def rule_diagnostics(states,objects,prior,support,object_support=None):
    features=rule_features(states,objects,prior,support,object_support);k=len(RULE_NAMES)
    return [{'probe':name,'score':float(features[i]) if bool(features[k+i]) else None,
             'observation_status':'experimental' if bool(features[k+i]) else 'unknown',
             'normative_status':'unknown','recognizer_validated':False,
             'limitation':'Soft visible-condition proxy; interval completeness, exceptions and applicable policy are unverified.'}
            for i,name in enumerate(RULE_NAMES)]

def technical_rule_inputs(video_id,scene_id,start,end):
    """Bridge to the real tri-state engine; a score cannot certify prerequisites."""
    from rules.types import RuleInputs,Interval
    return {case:RuleInputs(video_id=video_id,scene_id=scene_id,interval=Interval(start,end,scene_id),
                           recognizer_validated=False,interval_complete=False,visibility_complete=False,
                           relations_known=False,alternatives_checked=False,stage_ended=False)
            for case in ('C04','C05','C06','C07','C08','C09','C13','C14')}

class Temporal(nn.Module):
    def __init__(self):
        super().__init__();self.adapter=nn.Sequential(nn.Linear(70,64),nn.ReLU(),nn.Linear(64,576));self.gru=nn.GRU(576,256,batch_first=True)
        self.head=nn.Sequential(nn.Dropout(.5),nn.Linear(512,1));self.actions=nn.Linear(256,18)
        with torch.no_grad():self.adapter[-1].weight.zero_();self.adapter[-1].bias.zero_()

    def forward(self,values,lengths):
        if values.ndim!=3 or values.shape[-1]!=646 or not torch.isfinite(values).all() or (lengths<1).any() or (lengths>values.shape[1]).any():raise ValueError('invalid temporal sequence')
        adapted=values[:,:,:576]+self.adapter(values[:,:,576:])
        packed=pack_padded_sequence(adapted,lengths.cpu(),batch_first=True,enforce_sorted=False)
        out,_=self.gru(packed);out,_=pad_packed_sequence(out,batch_first=True,total_length=values.shape[1])
        mask=torch.arange(values.shape[1],device=values.device)[None]<lengths.to(values.device)[:,None]
        pooled=torch.cat((out.sum(1)/lengths.to(values.device)[:,None],out.masked_fill(~mask[...,None],-torch.inf).amax(1)),1)
        return self.head(pooled).squeeze(1),self.actions(out)

def validate_folds(folds,ids,groups):
    expected=set(ids);seen=[]
    for fold in folds:
        a,b=fold['train'],fold['validation']
        if len(set(a))!=len(a) or len(set(b))!=len(b) or set(a)&set(b) or set(a)|set(b)!=expected:
            raise ValueError('invalid source partition')
        if {groups[v] for v in a}&{groups[v] for v in b}:raise ValueError('family leakage')
        seen.extend(b)
    if len(seen)!=len(expected) or set(seen)!=expected:raise ValueError('validation coverage is not exact')

def prepare(cache,overlay,compat,review,spatial,previous_experiment,output):
    doc,rows,binding,marker=data.load(cache,overlay,compat,review,spatial);old=read_json(Path(previous_experiment)/'protocol.json')
    dev={r['video_id'] for r in rows if r['split'] in ('train','dev_validation')}
    if dev!=set(old['development_ids']):raise ValueError('development split changed')
    if {r['video_id'] for r in rows if r['split']=='independent_test'}!=set(old['reserved_ids']):raise ValueError('reserved split changed')
    groups={r['video_id']:r['group_id'] for r in rows};validate_folds(old['folds'],dev,groups)
    for fold in old['folds']:validate_folds(fold['inner'],fold['train'],groups)
    validate_folds(old['final_inner'],dev,groups)
    plan={'version':VERSION,'cache':str(Path(cache).resolve()),'overlay':str(Path(overlay).resolve()),'compat':str(Path(compat).resolve()),
          'review':str(Path(review).resolve()),'spatial':str(Path(spatial).resolve()),'binding':binding,'code_sha256':code_hash(),
          'folds':old['folds'],'final_inner':old['final_inner'],'development_ids':old['development_ids'],'reserved_ids':old['reserved_ids'],
          'arms':list(ARMS),'seeds':list(SEEDS),'config':CONFIG,'primary_seed':42,'objects':list(data.OBJECTS),'taxonomy':list(data.TAXONOMY),
          'rule_features':list(RULE_NAMES),'selection':'inner only max min(accuracy,BA,macroF1),accuracy,BA,F1,BCE; outer unchanged',
          'augmentation':'train-only brightness variants, simultaneous featuremap/box horizontal mirror',
          'semantic_prior':'frozen original ImageNet coffee mug/cup localized classifier; no pseudo labels; unvalidated',
          'cup_background_calibration':'train-only explicitly reviewed cup-negative frames; log max-prior q99 center,q99-q90 scale,min.25',
          'normative_findings':'always unknown until recognizer,coverage,exceptions,relations and policy are verified',
          'target':'mean three-seed accuracy,balanced_accuracy,macroF1>=0.80,all36 development sources; independent production validation remains unfulfilled',
          'production_ready':False,'independent_external_test':False,'original_verdicts_changed':False}
    plan['protocol_sha256']=stable_hash(plan);out=Path(output);out.mkdir(parents=True,exist_ok=False);atomic_json(out/'protocol.json',plan)
    with zipfile.ZipFile(out/'source_snapshot.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for name in ('object_events.py','object_event_inputs.py','action_focus.py','action_focus_inputs.py','action_refinement.py','small_data.py','video_baseline.py','preprocessing.py','models/encoder.py'):
            archive.write(Path(__file__).parent/name,'ml/'+name)
    print(json.dumps({'prepared':str(out),'protocol_sha256':plan['protocol_sha256']}),flush=True)

class Experiment:
    def __init__(self,directory,device='cuda'):
        torch.set_num_threads(4);self.directory=Path(directory);self.device=device;self.plan=read_json(self.directory/'protocol.json')
        if self.plan['config']!=CONFIG or self.plan['version']!=VERSION or self.plan['code_sha256']!=code_hash() or self.plan['protocol_sha256']!=stable_hash({k:v for k,v in self.plan.items() if k!='protocol_sha256'}):raise ValueError('protocol/code changed')
        self.document,rows,binding,self.marker=data.load(*[self.plan[k] for k in ('cache','overlay','compat','review','spatial')])
        if binding!=self.plan['binding']:raise ValueError('inputs changed')
        self.rows={r['video_id']:r for r in rows};self.memo={};self.fits=self.directory/'fits';self.fits.mkdir(exist_ok=True)

    def guard_ids(self,ids):
        if not ids or len(set(ids))!=len(ids) or not set(ids)<=set(self.plan['development_ids']):raise ValueError('unique development sources only')

    def train_spatial(self,ids,seed):
        self.guard_ids(ids);identity={'protocol':self.plan['protocol_sha256'],'kind':'spatial','ids':sorted(ids),'seed':seed};path=self.fits/(stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('spatial identity mismatch')
            return path
        started=time.perf_counter();torch.manual_seed(seed);rng=np.random.default_rng(seed)
        examples=[];boxes=[];actions=[];known=[];cup_negatives=[]
        for video in ids:
            r=self.rows[video]
            for n in range(len(r['actions'])):
                if (r['actions'][n]>=0).any() or r['object_known'][n].any():
                    examples.append((video,n));boxes.append(r['boxes'][n]);actions.append(r['actions'][n]);known.append(r['object_known'][n])
                if bool(r['object_known'][n,8]) and not any(box[0]==8 for box in r['boxes'][n]):cup_negatives.append(float(r['cup_prior'][n].max()))
        a=torch.stack(actions);target=object_targets(boxes,torch.stack(known));weights=auxiliary_weights(a[None]);model=SpatialHeads().to(self.device)
        model.state_support.copy_(weights['enabled'].to(self.device));model.object_support.copy_(target[2].any((0,2,3)).to(self.device))
        weights={k:v.to(self.device) for k,v in weights.items()};optimizer=torch.optim.AdamW(model.parameters(),lr=CONFIG['frame_lr'],weight_decay=.01)
        losses=[]
        for _ in range(CONFIG['frame_epochs']):
            for indices in np.array_split(rng.permutation(len(examples)),max(1,math.ceil(len(examples)/16))):
                maps=np.stack([self.rows[examples[i][0]]['maps'][int(rng.integers(0,3))][examples[i][1]] for i in indices]).astype(np.float32)
                x=torch.from_numpy(maps).to(self.device);t=[v[indices].to(self.device) for v in target]
                if rng.random()<.5:
                    x=x.flip(-1);t[0]=t[0].flip(-1);t[1]=t[1].flip(-1);t[1][:,:,0]=1-t[1][:,:,0];t[2]=t[2].flip(-1)
                loss=frame_loss(model(x),t,a[indices].to(self.device),weights)
                if not torch.isfinite(loss):raise ValueError('nonfinite spatial loss')
                optimizer.zero_grad(set_to_none=True);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();losses.append(float(loss.detach()))
        atomic_checkpoint(path,{'format':VERSION,'identity':identity,'model':{k:v.cpu() for k,v in model.state_dict().items()},
                               'cup_calibration':cup_background_calibration(cup_negatives),'cup_negative_frames':len(cup_negatives),
                               'loss':losses,'seconds':time.perf_counter()-started,'production_ready':False})
        print(json.dumps({'fit':'spatial','seed':seed,'videos':len(ids),'seconds':time.perf_counter()-started}),flush=True);return path

    def observations(self,path,ids):
        state=safe_torch_load(path);key=path.stem
        if state['identity']['protocol']!=self.plan['protocol_sha256']:raise ValueError('spatial protocol mismatch')
        model=SpatialHeads().to(self.device).eval();model.load_state_dict(state['model'],strict=True);result=[]
        for video in ids:
            cache_key=(key,video)
            if cache_key not in self.memo:
                r=self.rows[video];outputs=[]
                with torch.inference_mode():
                    for start in range(0,len(r['actions']),16):
                        values=torch.from_numpy(np.array(r['maps'][0][start:start+16],dtype=np.float32)).to(self.device)
                        out=model(values);outputs.append([v.cpu() for v in out[2:]])
                action,uniform,focused,meta=[torch.cat([o[k] for o in outputs]) for k in range(4)]
                probability=action.sigmoid();objects=meta[:,18:28]
                prior=calibrate_cup_prior(torch.from_numpy(np.array(r['cup_prior'],copy=True)),state['cup_calibration'])
                risk=rule_features(probability,objects,prior,model.state_support.cpu(),model.object_support.cpu())
                meta=torch.cat((meta,prior.flatten(1).amax(-1)[:,None],prior.flatten(1).mean(-1)[:,None]),1)
                self.memo[cache_key]={'video_id':video,'uniform':torch.cat((uniform,meta),1),'focused':torch.cat((focused,meta),1),
                                      'states':probability,'objects':objects,'boxes':meta[:,28:68].reshape(-1,10,4),
                                      'prior':prior,'rules':risk,'support':model.state_support.cpu(),'object_support':model.object_support.cpu()}
            result.append(self.memo[cache_key])
        return result

    def fit(self,ids,mode,seed):
        self.guard_ids(ids)
        if mode not in ('uniform','objects'):raise ValueError('unknown training mode')
        identity={'protocol':self.plan['protocol_sha256'],'kind':'temporal','mode':mode,'ids':sorted(ids),'seed':seed};path=self.fits/(stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('temporal identity mismatch')
            return path
        started=time.perf_counter();spatial=self.train_spatial(ids,seed);obs=self.observations(spatial,ids);torch.manual_seed(seed);rng=np.random.default_rng(seed)
        sequences=[o['uniform' if mode=='uniform' else 'focused'] for o in obs];joined=torch.cat(sequences);norm={'mean':joined.mean(0),'std':joined.std(0,unbiased=False).clamp_min(.01)}
        sequences=[(v-norm['mean'])/norm['std'] for v in sequences];targets=[self.rows[v]['actions'] for v in ids]
        actions=pad_sequence(targets,batch_first=True,padding_value=-1).to(self.device);weights=auxiliary_weights(actions)
        values=pad_sequence(sequences,batch_first=True).to(self.device);lengths=torch.tensor([len(v) for v in sequences]);y=torch.tensor([self.rows[v]['target'] for v in ids],device=self.device,dtype=torch.float32)
        model=Temporal().to(self.device);optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.05);model.train()
        for _ in range(CONFIG['pretrain_epochs']):
            starts=[int(rng.integers(0,max(1,len(v)-32+1))) for v in sequences]
            x=pad_sequence([v[s:s+32] for v,s in zip(sequences,starts)],batch_first=True).to(self.device)
            t=pad_sequence([v[s:s+32] for v,s in zip(targets,starts)],batch_first=True,padding_value=-1).to(self.device)
            l=torch.tensor([len(v[s:s+32]) for v,s in zip(sequences,starts)])
            _,a=model(x+torch.randn_like(x)*.03,l);loss=loss_masked(a,t,weights)
            optimizer.zero_grad(set_to_none=True);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        optimizer=torch.optim.AdamW(model.parameters(),lr=CONFIG['lr'],weight_decay=CONFIG['weight_decay']);objective=nn.BCEWithLogitsLoss(pos_weight=(y==0).sum()/(y==1).sum())
        pairs=previous.training_pairs([self.rows[v] for v in ids]);losses=[]
        for _ in range(CONFIG['epochs']):
            logits,a=model(values+torch.randn_like(values)*.03,lengths);loss=objective(logits,y)+.3*loss_masked(a,actions,weights)+.2*previous.pair_loss(logits,pairs)
            if not torch.isfinite(loss):raise ValueError('nonfinite temporal loss')
            optimizer.zero_grad(set_to_none=True);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();losses.append(float(loss.detach()))
        risk=torch.stack([o['rules'] for o in obs]).to(self.device);rmean=risk.mean(0);rstd=risk.std(0,unbiased=False).clamp_min(.05);head=nn.Linear(len(RULE_NAMES)*2,1).to(self.device)
        opt=torch.optim.AdamW(head.parameters(),lr=.01,weight_decay=1.)
        for _ in range(150):
            loss=objective(head((risk-rmean)/rstd).squeeze(1),y);opt.zero_grad(set_to_none=True);loss.backward();opt.step()
        atomic_checkpoint(path,{'format':VERSION,'identity':identity,'spatial':str(spatial.resolve()),'spatial_sha256':file_sha256(spatial),
            'model':{k:v.cpu() for k,v in model.state_dict().items()},'normalization':norm,'rule_head':{k:v.cpu() for k,v in head.state_dict().items()},
            'rule_mean':rmean.cpu(),'rule_std':rstd.cpu(),'loss':losses,'seconds':time.perf_counter()-started,'production_ready':False})
        print(json.dumps({'fit':mode,'seed':seed,'videos':len(ids),'seconds':time.perf_counter()-started}),flush=True);return path

    def predict(self,path,ids):
        state=safe_torch_load(path)
        if state['identity']['protocol']!=self.plan['protocol_sha256'] or file_sha256(state['spatial'])!=state['spatial_sha256']:raise ValueError('checkpoint lineage mismatch')
        observations=self.observations(Path(state['spatial']),ids);model=Temporal().to(self.device).eval();model.load_state_dict(state['model'],strict=True)
        norm=state['normalization'];key='uniform' if state['identity']['mode']=='uniform' else 'focused'
        sequences=[(o[key]-norm['mean'])/norm['std'] for o in observations]
        with torch.inference_mode():scores,_=model(pad_sequence(sequences,batch_first=True).to(self.device),torch.tensor([len(v) for v in sequences]))
        risk=torch.stack([o['rules'] for o in observations]);head=nn.Linear(24,1);head.load_state_dict(state['rule_head'])
        with torch.inference_mode():linear=head((risk-state['rule_mean'])/state['rule_std']).squeeze(1).sigmoid()
        predictions=[]
        for n,(video,o) in enumerate(zip(ids,observations)):
            g=float(scores[n].sigmoid().cpu());rl=float(linear[n]);physical=o['rules'][:12]
            # Only affirmative visible-state combinations enter the fixed probe;
            # absence-dependent ID/key/authentication claims are not manufactured.
            fixed=float(physical[:7].amax())
            predictions.append({'video_id':video,'truth':bool(self.rows[video]['target']),'gru':g,'linear':rl,'fixed':fixed,
                                'hybrid_linear':.5*(g+rl),'hybrid_fixed':.5*(g+fixed)})
        return predictions

    def choices(self,folds):
        pooled={arm:[] for arm in ARMS}
        for fold in folds:
            for mode in ('uniform','objects'):
                predictions=self.predict(self.fit(fold['train'],mode,42),fold['validation'])
                for p in predictions:
                    if mode=='uniform':pooled['uniform_gru'].append({**p,'score':p['gru']})
                    else:
                        for arm,key in [('objects_gru','gru'),('rules_linear','linear'),('policy_fixed','fixed'),('hybrid_linear','hybrid_linear'),('hybrid_fixed','hybrid_fixed')]:pooled[arm].append({**p,'score':p[key]})
        result={}
        for arm,pred in pooled.items():
            threshold=previous.calibrate(pred);bce=float(np.mean([-math.log(max(1e-7,min(1-1e-7,p['score'] if p['truth'] else 1-p['score']))) for p in pred]))
            result[arm]={'arm':arm,'threshold':threshold,'metrics':metrics(pred,threshold),'bce':bce,'oof':pred}
        return result,max(result.values(),key=previous.rank)

def box_iou(a,b):
    x0,y0,x1,y1=a;u0,v0,u1,v1=b
    inter=max(0,min(x1,u1)-max(x0,u0))*max(0,min(y1,v1)-max(y0,v0))
    return inter/max(1e-8,(x1-x0)*(y1-y0)+(u1-u0)*(v1-v0)-inter)

def localization_metrics(observations,rows):
    result={}
    for c,name in enumerate(data.OBJECTS):
        positive=negative=unsupported=hits=false=0;ious=[]
        for o in observations:
            r=rows[o['video_id']]
            for n,known in enumerate(r['object_known'][:,c]):
                if not bool(known):continue
                if not bool(o['object_support'][c]):unsupported+=1;continue
                truth=[box[1:] for box in r['boxes'][n] if box[0]==c];score=float(o['objects'][n,c])
                if truth:
                    positive+=1;cx,cy,w,h=o['boxes'][n,c].tolist();pred=[cx-w/2,cy-h/2,cx+w/2,cy+h/2]
                    iou=max(box_iou(pred,gt) for gt in truth);ious.append(iou);hits+=int(score>=.5 and iou>=.5)
                else:negative+=1;false+=int(score>=.5)
        result[name]={'positive_frames':positive,'negative_frames':negative,'unsupported_known_frames':unsupported,
                      'mean_top1_iou':float(np.mean(ious)) if ious else None,'localized_recall_iou50_score50':hits/positive if positive else None,
                      'negative_false_alarm_rate':false/negative if negative else None,'is_map':False}
    return result

def run(directory):
    torch.use_deterministic_algorithms(True);experiment=Experiment(directory);out=Path(directory)
    if (out/'complete.json').exists():raise ValueError('completed experiment immutable')
    result={a:{str(s):[] for s in SEEDS} for a in ARMS};nested={str(s):[] for s in SEEDS};reports=[];observations=[]
    for number,fold in enumerate(experiment.plan['folds']):
        choices,selected=experiment.choices(fold['inner'])
        for seed in SEEDS:
            for mode in ('uniform','objects'):
                predictions=experiment.predict(experiment.fit(fold['train'],mode,seed),fold['validation'])
                if seed==42 and mode=='objects':observations.extend(experiment.observations(experiment.train_spatial(fold['train'],seed),fold['validation']))
                for p in predictions:
                    mapping=[('uniform_gru','gru')] if mode=='uniform' else [('objects_gru','gru'),('rules_linear','linear'),('policy_fixed','fixed'),('hybrid_linear','hybrid_linear'),('hybrid_fixed','hybrid_fixed')]
                    for arm,key in mapping:
                        row={**p,'score':p[key],'threshold':choices[arm]['threshold'],'fold':number,'arm':arm};result[arm][str(seed)].append(row)
                        if arm==selected['arm']:nested[str(seed)].append(row)
        record={'fold':number,'choices':choices,'selected_arm':selected['arm'],'train':fold['train'],'validation':fold['validation']};reports.append(record);atomic_json(out/f'outer-fold-{number}.json',record)
        print(json.dumps({'outer_done':number,'selected':selected['arm']}),flush=True)
    choices,selected=experiment.choices(experiment.plan['final_inner']);mode='uniform' if selected['arm']=='uniform_gru' else 'objects'
    fitted=experiment.fit(experiment.plan['development_ids'],mode,42)
    decision={'protocol_sha256':experiment.plan['protocol_sha256'],'selected':selected,'fit':str(fitted.resolve()),'fit_sha256':file_sha256(fitted),'uses_reserved':False,'production_ready':False}
    atomic_json(out/'frozen_decision.json',decision)
    frames=[{'video_id':o['video_id'],'actions':o['states'],'actions_supported':o['support']} for o in observations]
    report={'version':VERSION,'comparisons':{a:{s:summarize(p) for s,p in ss.items()} for a,ss in result.items()},
            'nested_metrics':{s:summarize(p) for s,p in nested.items()},'oof':result,'nested_oof':nested,'folds':reports,'final_choices':choices,
            'frozen_decision':decision,'state_oof':auxiliary_metrics(frames,experiment.rows,'actions',data.TAXONOMY),
            'localization_oof':localization_metrics(observations,experiment.rows),
            'independent_external_test':False,'production_ready':False,'normative_status':'unknown'}
    atomic_checkpoint(out/'spatial_oof.pt',{'format':VERSION,'observations':observations})
    atomic_json(out/'cv_report.json',report);atomic_json(out/'complete.json',{'report_sha256':file_sha256(out/'cv_report.json'),'decision_sha256':file_sha256(out/'frozen_decision.json')})
    print(json.dumps({'comparisons':report['comparisons'],'nested':report['nested_metrics'],'final':selected['arm']}),flush=True)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare')
    for name in ('cache','overlay','compat','review','spatial','previous-experiment','output'):a.add_argument('--'+name,type=Path,required=True)
    a=s.add_parser('run');a.add_argument('--experiment',type=Path,required=True);a=p.parse_args(argv)
    if a.command=='prepare':prepare(a.cache,a.overlay,a.compat,a.review,a.spatial,a.previous_experiment,a.output)
    else:run(a.experiment)

if __name__=='__main__':main()
