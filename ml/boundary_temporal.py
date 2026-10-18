"""Dense object boundaries supervise a small causal temporal convolution block."""
from __future__ import annotations
import argparse,hashlib,json,math,time,zipfile
from pathlib import Path
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from ml import boundary_inputs as data,state_focus as helpers,object_events as reference
from ml.action_refinement import auxiliary_metrics
from ml.data.annotation_tasks import read_json
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint,metrics
from ml.small_data import summarize

VERSION='dense-object-boundary-tcn-v1'
CONFIG={'hidden':32,'epochs':220,'learning_rate':.003,'weight_decay':.01,'dropout':.15,
        'feature_noise':.01,'auxiliary_weight':2.,'pair_weight':.1,'edge_weight':3.,'ridge_alpha':10.}
ARMS=('boundary_tcn','boundary_ridge','boundary_blend','boundary_ridge_blend','legacy_uniform')
SEEDS=(42,137,2026)

def code_hash():
    return helpers.stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                                'inputs':data.code_hash(),'readout':helpers.code_hash()})

def source_normalization(rows):
    # Each source has equal mass; no validation frames enter either moment.
    mean=torch.stack([r['features'].mean(0) for r in rows]).mean(0)
    second=torch.stack([r['features'].square().mean(0) for r in rows]).mean(0)
    minimum=torch.cat((torch.full((3456,),.05),torch.full((47,),.003)))
    return {'mean':mean,'scale':(second-mean.square()).clamp_min(0).sqrt().maximum(minimum)}

def frame_weights(targets,edge_weight=3.):
    if targets.ndim!=3 or targets.shape[-1]!=len(data.TAXONOMY) or not torch.isin(targets,torch.tensor([-1.,0.,1.],device=targets.device)).all():raise ValueError('masked boundary targets required')
    weights=torch.zeros_like(targets);support=[]
    change=(targets[:,1:]>=0)&(targets[:,:-1]>=0)&(targets[:,1:]!=targets[:,:-1])
    edge=torch.zeros_like(targets,dtype=torch.bool);edge[:,1:]|=change;edge[:,:-1]|=change
    for c in range(targets.shape[-1]):
        enabled=bool((targets[:,:,c]==0).any() and (targets[:,:,c]==1).any());support.append(enabled)
        if not enabled:continue
        for value in (0,1):
            mask=targets[:,:,c]==value;counts=mask.sum(1);sources=(counts>0).sum()
            w=mask/(counts.clamp_min(1)[:,None]*sources)*torch.where(edge[:,:,c],edge_weight,1.)
            weights[:,:,c]+=.5*w/w.sum()
    return weights,torch.tensor(support,dtype=torch.bool,device=targets.device)

class BoundaryNet(nn.Module):
    def __init__(self,dimension=data.DIM,hidden=32,dropout=.15):
        super().__init__();self.project=nn.Linear(dimension,hidden);self.norm=nn.LayerNorm(hidden)
        self.conv=nn.ModuleList([nn.Conv1d(hidden,hidden,3,dilation=d) for d in (1,2)])
        self.drop=nn.Dropout(dropout);self.states=nn.Linear(hidden,len(data.TAXONOMY));self.clip=nn.Linear(hidden*3+len(data.TAXONOMY)*3,1)

    def forward(self,values,lengths,support):
        if values.ndim!=3 or lengths.shape!=(len(values),) or support.shape!=(len(data.TAXONOMY),) or bool((lengths<1).any()) or bool((lengths>values.shape[1]).any()):raise ValueError('boundary sequence shapes')
        x=self.drop(F.gelu(self.norm(self.project(values))))
        for layer,dilation in zip(self.conv,(1,2)):
            z=layer(F.pad(x.transpose(1,2),(2*dilation,0))).transpose(1,2)
            x=x+self.drop(F.gelu(z))
        logits=self.states(x);p=logits.sigmoid()*support
        mask=torch.arange(values.shape[1],device=values.device)[None]<lengths[:,None]
        mean=(x*mask[:,:,None]).sum(1)/lengths[:,None]
        maximum=x.masked_fill(~mask[:,:,None],-torch.inf).amax(1)
        end=x[torch.arange(len(x),device=x.device),lengths-1]-x[:,0]
        pm=(p*mask[:,:,None]).sum(1)/lengths[:,None];tails=[];differences=[]
        for n,length in enumerate(lengths.tolist()):
            k=min(4,length);tails.append(p[n,length-k:length].mean(0));differences.append(tails[-1]-p[n,:k].mean(0))
        pooled=torch.cat((mean,maximum,end,pm,torch.stack(tails),torch.stack(differences)),1)
        return self.clip(pooled).squeeze(-1),logits

def pack(rows,norm,device):
    lengths=torch.tensor([len(r['features']) for r in rows],dtype=torch.long,device=device);t=int(lengths.max())
    values=torch.zeros(len(rows),t,data.DIM,device=device);targets=torch.full((len(rows),t,len(data.TAXONOMY)),-1.,device=device)
    for n,r in enumerate(rows):
        length=len(r['features']);values[n,:length]=(r['features']-norm['mean'])/norm['scale'];targets[n,:length]=r['boundary_targets'].to(device)
    return values,lengths,targets

def boundary_summary(p):
    if p.ndim!=2 or p.shape[1]!=len(data.TAXONOMY) or len(p)<1:raise ValueError('state summary shape')
    k=min(4,len(p));delta=p[1:]-p[:-1]
    motion=delta.abs().mean(0) if len(delta) else torch.zeros_like(p[0])
    summary=[p.mean(0),p.amax(0),p.std(0,unbiased=False),p[-k:].mean(0),p[-k:].mean(0)-p[:k].mean(0),motion,p[0],p[-1]]
    operator_drop=(p[:,4].amax()-p[-k:,4].amax()).clamp(0,1);customer_drop=(p[:,5].amax()-p[-k:,5].amax()).clamp(0,1)
    bag=p[-k:,1].mean()*p[-k:,3].mean()
    probes=torch.stack((bag*operator_drop,bag*customer_drop,p[-k:,0].mean()*operator_drop,p[:,2].amax()*p[-k:,3].mean()))
    return torch.cat((*summary,probes))

def fit_model(rows,seed,config=CONFIG,device='cuda'):
    torch.manual_seed(seed);np.random.seed(seed);torch.set_num_threads(4)
    norm=source_normalization(rows);x,lengths,targets=pack(rows,norm,device);weights,support=frame_weights(targets,config['edge_weight'])
    net=BoundaryNet(hidden=config['hidden'],dropout=config['dropout']).to(device)
    labels=torch.tensor([r['target'] for r in rows],dtype=torch.float32,device=device);clip_weight=helpers.balanced_weights(labels)
    pairs=[(i,j) for i,a in enumerate(rows) for j,b in enumerate(rows) if a['group_id']==b['group_id'] and a['target']==1 and b['target']==0]
    optimizer=torch.optim.AdamW(net.parameters(),lr=config['learning_rate'],weight_decay=config['weight_decay'])
    for epoch in range(config['epochs']):
        net.train();optimizer.zero_grad(set_to_none=True)
        logits,state=net(x+torch.randn_like(x)*config['feature_noise'],lengths,support)
        clip=(F.binary_cross_entropy_with_logits(logits,labels,reduction='none')*clip_weight).sum()
        auxiliary=(F.binary_cross_entropy_with_logits(state,targets.clamp_min(0),reduction='none')*weights).sum()/support.sum().clamp_min(1)
        contrast=F.softplus(torch.stack([.5-logits[i]+logits[j] for i,j in pairs])).mean() if pairs else logits.sum()*0
        loss=clip+config['auxiliary_weight']*auxiliary+config['pair_weight']*contrast
        if not bool(torch.isfinite(loss)):raise ValueError('nonfinite boundary training')
        loss.backward();nn.utils.clip_grad_norm_(net.parameters(),1.);optimizer.step()
    net.eval()
    with torch.inference_mode():_,state=net(x,lengths,support)
    probabilities=state.sigmoid()*support
    summaries=torch.stack([boundary_summary(probabilities[n,:length].cpu()) for n,length in enumerate(lengths.tolist())])
    readout=helpers.fit_readout(summaries,labels.cpu(),[r['group_id'] for r in rows],config['ridge_alpha'],[summaries.shape[1]])
    return {'model':{k:v.detach().cpu().clone() for k,v in net.state_dict().items()},'normalization':norm,'support':support.cpu(),
            'readout':readout,'last_loss':float(loss.detach()),'epochs':config['epochs'],'training_pairs':len(pairs),'state_scores_are_calibrated_probabilities':False}

def predict_model(state,rows,device='cuda'):
    net=BoundaryNet(hidden=CONFIG['hidden'],dropout=CONFIG['dropout']).to(device);net.load_state_dict(state['model'],strict=True);net.eval()
    x,lengths,_=pack(rows,state['normalization'],device);support=state['support'].to(device)
    with torch.inference_mode():logits,states=net(x,lengths,support)
    predictions=[]
    for n,length in enumerate(lengths.tolist()):
        p=states[n,:length].sigmoid().cpu()*state['support'];summary=boundary_summary(p)
        predictions.append({'video_id':rows[n]['video_id'],'tcn':float(logits[n].sigmoid()),
                            'ridge':float(helpers.readout_predict(state['readout'],summary)),
                            'actions':p,'actions_supported':state['support']})
    return predictions

def observed_events(probabilities,support,points,timing,truth=None):
    """Two samples confirm a change; its first observation is the bracket end."""
    result=[]
    for c,up,down in ((0,'safe_opening','safe_closing'),(3,'bag_placement','bag_pickup')):
        if not bool(support[c]):continue
        binary=probabilities[:,c]>=.5
        for n in range(1,len(binary)-1):
            if binary[n]==binary[n-1] or binary[n]!=binary[n+1]:continue
            if truth is not None and (truth[n-1,c]<0 or truth[n,c]<0 or truth[n+1,c]<0):continue
            result.append({'type':up if bool(binary[n]) else down,'source_pts':int(points[n]),'time_sec':timing[int(points[n])],
                           'confirmed_at_sec':timing[int(points[n+1])],'normative_status':'unknown'})
    return result

def event_metrics(predictions,rows,prepared,tolerance=.5):
    kinds=('safe_opening','safe_closing','bag_placement','bag_pickup');report={}
    for kind in kinds:
        tp=fp=fn=unsupported=0;errors=[]
        for prediction in predictions:
            r=rows[prediction['video_id']];index=read_json(Path(prepared)/'indices'/(r['video_id']+'.json'));timing={f['source_pts']:f['timestamp_sec'] for f in index['frames']}
            truth=[e for e in r['events'] if e['type']==kind];c=0 if kind.startswith('safe') else 3
            if not bool(prediction['actions_supported'][c]):unsupported+=len(truth);continue
            predicted=[];positions={int(p):n for n,p in enumerate(r['source_pts'])}
            for event in observed_events(prediction['actions'],prediction['actions_supported'],r['source_pts'],timing):
                if event['type']!=kind:continue
                n=positions[event['source_pts']];known=bool((r['boundary_targets'][n-1:n+2,c]>=0).all())
                near_truth=any(max(t['earliest_sec']-event['time_sec'],event['time_sec']-t['latest_sec'],0.)<=tolerance for t in truth)
                if known or near_truth:predicted.append(event)
            pairs=[]
            for i,e in enumerate(predicted):
                for j,t in enumerate(truth):
                    distance=max(t['earliest_sec']-e['time_sec'],e['time_sec']-t['latest_sec'],0.)
                    if distance<=tolerance:pairs.append((distance,i,j))
            seen_p=set();seen_t=set()
            for distance,i,j in sorted(pairs):
                if i not in seen_p and j not in seen_t:seen_p.add(i);seen_t.add(j);errors.append(distance)
            tp+=len(seen_p);fp+=len(predicted)-len(seen_p);fn+=len(truth)-len(seen_t)
        precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
        report[kind]={'tp':tp,'fp':fp,'fn':fn,'unsupported_events':unsupported,'precision':precision,'recall':recall,
                      'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,'matched_mean_bracket_distance_seconds':float(np.mean(errors)) if errors else None}
    return {'tolerance_seconds':tolerance,'confirmation_samples':2,'truth':'assistant brackets; not human acceptance','by_type':report}

def prepare(parent,inputs,reference_stage,output):
    p=read_json(Path(parent)/'protocol.json');marker,rows=data.load(inputs)
    if marker['parent_protocol_sha256']!=p['protocol_sha256'] or set(rows)!=set(p['development_ids']):raise ValueError('boundary/parent lineage')
    groups={v:r['group_id'] for v,r in rows.items()};reference.validate_folds(p['folds'],p['development_ids'],groups)
    for fold in p['folds']:reference.validate_folds(fold['inner'],fold['train'],groups)
    reference.validate_folds(p['final_inner'],p['development_ids'],groups)
    ref=read_json(Path(reference_stage)/'frozen_decision.json');binding=read_json(Path(reference_stage)/'complete.json')
    if file_sha256(Path(reference_stage)/'frozen_decision.json')!=binding['decision_sha256'] or ref['selected']['arm']!='legacy_uniform' or ref['uses_reserved'] is not False:raise ValueError('frozen reference required')
    plan={'version':VERSION,'code_sha256':code_hash(),'parent':str(Path(parent).resolve()),'parent_protocol_sha256':p['protocol_sha256'],
          'inputs':str(Path(inputs).resolve()),'inputs_sha256':file_sha256(Path(inputs)/'inputs.json'),'review_sha256':marker['review_sha256'],
          'reference_stage':str(Path(reference_stage).resolve()),'reference_decision_sha256':binding['decision_sha256'],'reference_fit':ref['reference_fit'],
          **{k:p[k] for k in ('folds','final_inner','development_ids','reserved_ids')},'seeds':list(SEEDS),'config':CONFIG,
          'arms':list(ARMS),'selection':'same inner folds; rank min accuracy/BA/macroF1 then metrics and BCE; seed42 chooses thresholds; outer seeds42/137/2026',
          'event_evaluation':{'tolerance_seconds':.5,'threshold':.5,'confirmation_samples':2,'unknown_adjacent_states_unscored':True},
          'epoch_selection':'fixed220; no outer/reserved early stopping','target_accuracy':.8,'human_approved':False,
          'production_ready':False,'independent_external_test':False,'original_verdicts_changed':False}
    plan['protocol_sha256']=helpers.stable_hash(plan);out=Path(output);out.mkdir(parents=True,exist_ok=False);atomic_json(out/'protocol.json',plan)
    with zipfile.ZipFile(out/'source_snapshot.zip','x',zipfile.ZIP_DEFLATED) as z:
        for name in ('boundary_inputs.py','boundary_temporal.py'):z.write(Path(__file__).parent/name,'ml/'+name)
    print({'protocol_sha256':plan['protocol_sha256'],'config':CONFIG,'arms':ARMS},flush=True)

class Experiment:
    def __init__(self,directory,device='cuda'):
        torch.set_num_threads(4);self.directory=Path(directory);self.plan=read_json(self.directory/'protocol.json');self.device=device
        if self.plan['version']!=VERSION or self.plan['config']!=CONFIG or self.plan['arms']!=list(ARMS) or self.plan['code_sha256']!=code_hash() or self.plan['protocol_sha256']!=helpers.stable_hash({k:v for k,v in self.plan.items() if k!='protocol_sha256'}):raise ValueError('boundary protocol/code changed')
        if file_sha256(Path(self.plan['inputs'])/'inputs.json')!=self.plan['inputs_sha256']:raise ValueError('boundary inputs changed')
        _,self.rows=data.load(self.plan['inputs']);self.fits=self.directory/'fits';self.fits.mkdir(exist_ok=True);self.memo={};self.old={}
        self.parent=read_json(Path(self.plan['parent'])/'protocol.json');m=read_json(Path(self.plan['parent'])/'complete.json')
        if self.parent['protocol_sha256']!=self.plan['parent_protocol_sha256'] or file_sha256(Path(self.plan['parent'])/'cv_report.json')!=m['report_sha256']:raise ValueError('reference parent changed')
        report=read_json(Path(self.plan['parent'])/'cv_report.json')
        for n,fold in enumerate(self.plan['folds']):
            for seed in SEEDS:self.old[(tuple(sorted(fold['train'])),seed)]={v['video_id']:v['score'] for v in report['oof']['uniform_gru'][str(seed)] if v['fold']==n}
            for inner in fold['inner']:self.old[(tuple(sorted(inner['train'])),42)]={v['video_id']:v['score'] for v in report['folds'][n]['choices']['uniform_gru']['oof'] if v['video_id'] in inner['validation']}
        for inner in self.plan['final_inner']:self.old[(tuple(sorted(inner['train'])),42)]={v['video_id']:v['score'] for v in report['final_choices']['uniform_gru']['oof'] if v['video_id'] in inner['validation']}
        self.prepared=read_json(Path(self.parent['cache'])/'cache.json')['prepared_dir']

    def guard(self,ids):
        if not ids or len(set(ids))!=len(ids) or not set(ids)<=set(self.plan['development_ids']):raise ValueError('unique development train sources required')

    def fit(self,ids,seed):
        self.guard(ids);identity={'protocol':self.plan['protocol_sha256'],'kind':'boundary_tcn','ids':sorted(ids),'seed':seed};path=self.fits/(helpers.stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('boundary fit identity')
            return path
        start=time.perf_counter();state=fit_model([self.rows[v] for v in sorted(ids)],seed,device=self.device)
        atomic_checkpoint(path,{'format':VERSION,'identity':identity,'state':state,'seconds':time.perf_counter()-start,'production_ready':False})
        print({'fit':path.stem,'sources':len(ids),'seed':seed,'seconds':time.perf_counter()-start,'last_loss':state['last_loss']},flush=True);return path

    def observations(self,path,ids):
        checkpoint=safe_torch_load(path)
        if checkpoint['identity']['protocol']!=self.plan['protocol_sha256']:raise ValueError('boundary checkpoint lineage')
        missing=[v for v in ids if (path.stem,v) not in self.memo]
        if missing:
            for prediction in predict_model(checkpoint['state'],[self.rows[v] for v in missing],self.device):self.memo[(path.stem,prediction['video_id'])]=prediction
        return [self.memo[(path.stem,v)] for v in ids]

    def reference(self,train,seed,ids):
        key=(tuple(sorted(train)),seed)
        if key not in self.old:
            if set(train)!=set(self.plan['development_ids']) or seed!=42:raise ValueError('missing exact train-only GRU predictions')
            ref=self.plan['reference_fit']
            if file_sha256(ref['fit'])!=ref['sha256']:raise ValueError('reference weights changed')
            e=reference.Experiment(self.plan['parent'],self.device);checkpoint=safe_torch_load(ref['fit'])
            if checkpoint['identity']['ids']!=sorted(train) or checkpoint['identity']['protocol']!=self.parent['protocol_sha256']:raise ValueError('reference training identity')
            self.old[key]={p['video_id']:p['gru'] for p in e.predict(Path(ref['fit']),ids)}
        if not set(ids)<=set(self.old[key]):raise ValueError('missing reference prediction coverage')
        return [self.old[key][v] for v in ids]

    def predictions(self,train,ids,seed):
        observed=self.observations(self.fit(train,seed),ids);old=self.reference(train,seed,ids);result={a:[] for a in ARMS}
        for o,g in zip(observed,old):
            values=(o['tcn'],o['ridge'],.5*(o['tcn']+g),.5*(o['ridge']+g),g)
            for arm,value in zip(ARMS,values):result[arm].append({'video_id':o['video_id'],'truth':bool(self.rows[o['video_id']]['target']),'score':value})
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
    torch.use_deterministic_algorithms(True);torch.backends.cudnn.benchmark=False;e=Experiment(directory);out=Path(directory)
    if (out/'complete.json').exists():raise ValueError('completed boundary experiment immutable')
    nested={str(s):[] for s in SEEDS};comparisons={a:{str(s):[] for s in SEEDS} for a in ARMS};frames=[];folds=[]
    for n,fold in enumerate(e.plan['folds']):
        choices,selected=e.choices(fold['inner'])
        for seed in SEEDS:
            predictions=e.predictions(fold['train'],fold['validation'],seed)
            if seed==42:frames.extend(e.observations(e.fit(fold['train'],seed),fold['validation']))
            for arm,rows in predictions.items():
                rows=[{**r,'threshold':choices[arm]['threshold'],'fold':n,'arm':arm} for r in rows];comparisons[arm][str(seed)].extend(rows)
                if arm==selected['arm']:nested[str(seed)].extend(rows)
        record={'fold':n,'selected':selected['arm'],'choices':choices};folds.append(record);atomic_json(out/f'outer-fold-{n}.json',record);print({'outer_done':n,'selected':selected['arm']},flush=True)
    choices,selected=e.choices(e.plan['final_inner']);fit=e.fit(e.plan['development_ids'],42)
    decision={'protocol_sha256':e.plan['protocol_sha256'],'selected':selected,'fit':str(fit.resolve()),'fit_sha256':file_sha256(fit),
              'reference_fit':e.plan['reference_fit'],'uses_reserved':False,'production_ready':False};atomic_json(out/'frozen_decision.json',decision)
    by_id={v:{'actions':r['boundary_targets']} for v,r in e.rows.items()};report={'version':VERSION,'nested_metrics':{s:summarize(p) for s,p in nested.items()},
             'comparisons':{a:{s:summarize(p) for s,p in ss.items()} for a,ss in comparisons.items()},'nested_oof':nested,'oof':comparisons,'folds':folds,
             'final_choices':choices,'frozen_decision':decision,'frame_metrics':auxiliary_metrics(frames,by_id,'actions',data.TAXONOMY),
             'event_metrics':event_metrics(frames,e.rows,e.prepared),
             'production_ready':False,'independent_external_test':False,'normative_status':'unknown'}
    atomic_checkpoint(out/'frame_oof.pt',{'format':VERSION,'observations':frames});atomic_json(out/'cv_report.json',report)
    atomic_json(out/'complete.json',{'report_sha256':file_sha256(out/'cv_report.json'),'decision_sha256':file_sha256(out/'frozen_decision.json')})
    print({'nested':report['nested_metrics'],'selected':selected['arm']},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare')
    for name in ('parent','inputs','reference','output'):a.add_argument('--'+name,type=Path,required=True)
    a=s.add_parser('run');a.add_argument('--experiment',type=Path,required=True);args=p.parse_args()
    if args.command=='prepare':prepare(args.parent,args.inputs,args.reference,args.output)
    else:run(args.experiment)
