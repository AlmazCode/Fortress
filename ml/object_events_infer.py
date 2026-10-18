"""Dataset-free local bundle for spatial objects, actions and guarded rule probes."""
from __future__ import annotations
import argparse,hashlib,json,math,time
from pathlib import Path
import numpy as np
import torch
import torchvision
from ml import object_events as training
from ml import object_event_inputs as data
from ml.data.annotation_tasks import read_json
from ml.data.manifest import probe_video,source_hash
from ml.data.pts_index import build_index,iter_indexed_frames
from ml.data.scenes import define_scenes,sample_scenes
from ml.models.encoder import FrozenEncoder,file_sha256,safe_torch_load
from ml.video_baseline import atomic_checkpoint,atomic_json,metrics

VERSION='spatial-object-events-local-bundle-v1'
def code_hash():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()

def decision(directory):
    directory=Path(directory);marker=read_json(directory/'complete.json')
    if file_sha256(directory/'frozen_decision.json')!=marker['decision_sha256'] or file_sha256(directory/'cv_report.json')!=marker['report_sha256']:raise ValueError('frozen decision/report changed')
    result=read_json(directory/'frozen_decision.json')
    if file_sha256(result['fit'])!=result['fit_sha256']:raise ValueError('selected fit changed')
    return result

def tensor_bytes(tree):
    if isinstance(tree,torch.Tensor):return tree.numel()*tree.element_size()
    if isinstance(tree,dict):return sum(tensor_bytes(v) for v in tree.values())
    if isinstance(tree,(list,tuple)):return sum(tensor_bytes(v) for v in tree)
    return 0

def export(experiment,output):
    choice=decision(experiment);plan=read_json(Path(experiment)/'protocol.json');marker=read_json(Path(plan['spatial'])/'inputs.json')
    if plan['code_sha256']!=training.code_hash():raise ValueError('training code changed')
    state=safe_torch_load(Path(choice['fit']),expected_sha256=choice['fit_sha256'])
    spatial=safe_torch_load(Path(state['spatial']),expected_sha256=state['spatial_sha256'])
    if state['identity']['protocol']!=plan['protocol_sha256'] or spatial['identity']['protocol']!=plan['protocol_sha256']:raise ValueError('fit lineage mismatch')
    encoder=FrozenEncoder(weights_path=Path(marker['encoder_weights']),weights_sha256=marker['encoder_sha256'])
    classifier=data.cup_classifier(Path(marker['encoder_weights']),marker['encoder_sha256'])
    payload={'format':VERSION,'encoder':dict(encoder.features.state_dict()),'cup_classifier':dict(classifier.state_dict()),
             'spatial':spatial['model'],'temporal':state['model'],'normalization':state['normalization'],
             'cup_calibration':spatial['cup_calibration'],'rule_head':state['rule_head'],'rule_mean':state['rule_mean'],'rule_std':state['rule_std']}
    size=tensor_bytes(payload)
    if size>12*1024**2:raise ValueError('bundle tensors exceed12MiB')
    output=Path(output);output.mkdir(parents=True,exist_ok=False);atomic_checkpoint(output/'weights.pt',payload)
    metadata={'version':VERSION,'weights_sha256':file_sha256(output/'weights.pt'),'original_fit_sha256':choice['fit_sha256'],
              'spatial_fit_sha256':state['spatial_sha256'],'protocol_sha256':plan['protocol_sha256'],'arm':choice['selected']['arm'],
              'mode':state['identity']['mode'],'threshold':choice['selected']['threshold'],'input_version':data.VERSION,
              'size':448,'rate':2.,'variants':list(data.VARIANTS),'map_dtype':'float16','roi':list(data.base.ROI),
              'taxonomy':list(data.TAXONOMY),'objects':list(data.OBJECTS),'cup_classes':['coffee mug','cup'],
              'training_code_sha256':training.code_hash(),'inference_code_sha256':code_hash(),'tensor_bytes':size,
              'production_ready':False,'recognizers_validated':False,'normative_status':'unknown','human_approved_extra_labels':False}
    atomic_json(output/'bundle.json',metadata);print(json.dumps(metadata),flush=True);return metadata

class Encoder(torch.nn.Module):
    def __init__(self,state):
        super().__init__();self.features=torchvision.models.mobilenet_v3_small(weights=None).features
        self.features.load_state_dict(state,strict=True);self.eval().requires_grad_(False)

def displayed_box(box,index):
    width,height=index['width'],index['height']
    if abs(index['rotation'])%180:width,height=height,width
    left,top,right,bottom=(round(data.base.ROI[0]*width),round(data.base.ROI[1]*height),round(data.base.ROI[2]*width),round(data.base.ROI[3]*height))
    scale=min(448/(right-left),448/(bottom-top));rw,rh=round((right-left)*scale),round((bottom-top)*scale);px,py=(448-rw)//2,(448-rh)//2
    cx,cy,w,h=map(float,box)
    x0=max(left,min(right,left+((cx-w/2)*448-px)*(right-left)/rw));x1=max(left,min(right,left+((cx+w/2)*448-px)*(right-left)/rw))
    y0=max(top,min(bottom,top+((cy-h/2)*448-py)*(bottom-top)/rh));y1=max(top,min(bottom,top+((cy+h/2)*448-py)*(bottom-top)/rh))
    return [x0,y0,x1,y1] if x0<x1 and y0<y1 else None

class Predictor:
    def __init__(self,bundle,device='cuda'):
        torch.set_num_threads(4);self.device=device;self.metadata=read_json(Path(bundle)/'bundle.json');m=self.metadata
        if (m['version']!=VERSION or m['training_code_sha256']!=training.code_hash() or m['inference_code_sha256']!=code_hash()
                or m['input_version']!=data.VERSION or m['size']!=448 or m['rate']!=2. or m['variants']!=list(data.VARIANTS)
                or m['roi']!=list(data.base.ROI) or m['taxonomy']!=list(data.TAXONOMY) or m['objects']!=list(data.OBJECTS)
                or m['arm'] not in training.ARMS or m['mode'] not in ('uniform','objects') or m['production_ready'] is not False
                or type(m['threshold']) not in (int,float) or not math.isfinite(m['threshold']) or not 0<=m['threshold']<=1
                or (m['arm']=='uniform_gru')!=(m['mode']=='uniform') or m['cup_classes']!=['coffee mug','cup']):raise ValueError('unsupported spatial bundle')
        state=safe_torch_load(Path(bundle)/'weights.pt',expected_sha256=m['weights_sha256'],max_bytes=12*1024**2)
        if state['format']!=VERSION or tensor_bytes(state)>12*1024**2:raise ValueError('invalid bundle state')
        self.encoder=Encoder(state['encoder']).to(device)
        self.classifier=torch.nn.Sequential(torch.nn.Linear(576,512),torch.nn.Hardswish(),torch.nn.Linear(512,1000)).to(device).eval()
        self.classifier.load_state_dict(state['cup_classifier'],strict=True)
        names=torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1.meta['categories'];self.cup_indices=[names.index(n) for n in m['cup_classes']]
        self.spatial=training.SpatialHeads().to(device).eval();self.spatial.load_state_dict(state['spatial'],strict=True)
        self.temporal=training.Temporal().to(device).eval();self.temporal.load_state_dict(state['temporal'],strict=True)
        self.norm=state['normalization'];self.cup_calibration=state['cup_calibration']
        self.rule_head=torch.nn.Linear(24,1);self.rule_head.load_state_dict(state['rule_head'],strict=True);self.rule_head.eval()
        self.rule_mean,self.rule_std=state['rule_mean'],state['rule_std']
        self.correction=state.get('log_weight_correction')
        if self.correction is not None:
            if self.correction.shape!=(18,) or not m.get('calibration_code_sha256'):raise ValueError('invalid probability correction')
        if m.get('calibration_code_sha256'):
            from ml.object_rules import code_hash as calibration_hash
            if calibration_hash()!=m['calibration_code_sha256']:raise ValueError('calibration code changed')

    def encode(self,root,index):
        sample=sample_scenes(index,define_scenes(index),rate=2.);pts=[s['time']['source_pts'] for s in sample if s['image_mask']]
        if len(set(pts))!=len(sample) or not 1<=len(pts)<=360:raise ValueError('missing/duplicate/over-budget source frames')
        selected=set(pts);pending=[];pending_pts=[];points=[];maps=[];priors=[]
        def flush():
            if not pending:return
            batch=torch.stack(pending).to(self.device);n=len(batch)
            values=self.encoder.features(batch.flatten(0,1)).reshape(n,3,576,14,14)
            pooled=torch.nn.functional.avg_pool2d(values[:,0],3,stride=1,padding=1).permute(0,2,3,1)
            prior=self.classifier(pooled).softmax(-1)[...,self.cup_indices].sum(-1)
            maps.extend(values[:,0].cpu().numpy().astype(np.float16));priors.extend(prior.cpu().numpy());points.extend(pending_pts);pending.clear();pending_pts.clear()
        with torch.inference_mode():
            for timing,frame in iter_indexed_frames(Path(root),index):
                if timing['source_pts'] in selected:
                    pending.append(torch.stack([data.tensor(frame.to_image(),index,b) for b in data.VARIANTS]));pending_pts.append(timing['source_pts'])
                    if len(pending)==8:flush()
            flush()
        if points!=pts:raise ValueError('decoded source PTS mismatch')
        return np.asarray(maps,dtype=np.float16),np.asarray(priors,dtype=np.float32),points

    def predict_maps(self,maps,priors,points,index,return_features=False):
        if (not 1<=len(maps)<=360 or maps.shape!=(len(maps),576,14,14) or maps.dtype!=np.float16
                or priors.shape!=(len(maps),14,14) or not np.isfinite(priors).all() or (priors<0).any() or (priors>1).any()
                or len(points)!=len(maps) or any(type(p)is not int for p in points) or any(a>=b for a,b in zip(points,points[1:]))
                or not set(points)<={r['source_pts'] for r in index['frames']}):raise ValueError('invalid source-bound spatial sequence')
        outputs=[]
        with torch.inference_mode():
            for start in range(0,len(maps),16):
                out=self.spatial(torch.from_numpy(np.array(maps[start:start+16],dtype=np.float32)).to(self.device))
                outputs.append([v.cpu() for v in out[2:]])
        action,uniform,focused,meta=[torch.cat([o[k] for o in outputs]) for k in range(4)]
        states=action.sigmoid();objects=meta[:,18:28];boxes=meta[:,28:68].reshape(-1,10,4)
        if self.correction is not None:
            from ml.object_rules import correct
            states=correct(states,self.correction)
        prior=training.calibrate_cup_prior(torch.from_numpy(np.array(priors,copy=True)),self.cup_calibration)
        support=self.spatial.state_support.cpu();object_support=self.spatial.object_support.cpu()
        risk=training.rule_features(states,objects,prior,support,object_support)
        meta=torch.cat((meta,prior.flatten(1).amax(-1)[:,None],prior.flatten(1).mean(-1)[:,None]),1)
        features=torch.cat((uniform if self.metadata['mode']=='uniform' else focused,meta),1)
        values=(features-self.norm['mean'])/self.norm['std']
        with torch.inference_mode():
            logit,_=self.temporal(values[None].to(self.device),torch.tensor([len(values)]))
            linear=self.rule_head((risk-self.rule_mean)/self.rule_std).sigmoid()[0]
        g,rl,fixed=float(logit.sigmoid()[0].cpu()),float(linear),float(risk[:7].amax())
        scores={'uniform_gru':g,'objects_gru':g,'rules_linear':rl,'policy_fixed':fixed,'hybrid_linear':.5*(g+rl),'hybrid_fixed':.5*(g+fixed)}
        timing={r['source_pts']:r['timestamp_sec'] for r in index['frames']};frames=[]
        for n,p in enumerate(points):
            detected=[]
            for c,name in enumerate(data.OBJECTS):
                if bool(object_support[c]) and objects[n,c]>=.5:
                    box=displayed_box(boxes[n,c],index)
                    if box:detected.append({'class':name,'score':float(objects[n,c]),'box_displayed_xyxy':box})
            frames.append({'source_pts':p,'timestamp_sec':timing[p],
                           'state_scores':{name:float(states[n,c]) if bool(support[c]) else None for c,name in enumerate(data.TAXONOMY)},
                           'objects':detected,'cup_prior_unvalidated':float(prior[n].max())})
        events=[]
        for c,name in enumerate(data.TAXONOMY):
            if not bool(support[c]):continue
            runs=[];current=[]
            for n,p in enumerate(points):
                if states[n,c]>=.5:
                    if current and timing[p]-timing[current[-1]]>.75:runs.append(current);current=[]
                    current.append(p)
                elif current:runs.append(current);current=[]
            if current:runs.append(current)
            for run in runs:events.append({'action':name,'start_sec':timing[run[0]],'end_sec':timing[run[-1]],'source_pts':run,'interval_validated':False})
        result={'score':scores[self.metadata['arm']],'selected_arm':self.metadata.get('selection_arm',self.metadata['arm']),'gru_mode':self.metadata['mode'],
                'component_scores':{'gru':g,'rules_linear':rl,'policy_fixed':fixed},'frames':frames,'candidate_events':events,
                'rule_probes':training.rule_diagnostics(states,objects,prior,support,object_support),'normative_status':'unknown'}
        from rules.engine import evaluate_template
        evidence=training.technical_rule_inputs(index.get('video_id','raw'),index.get('video_id','raw')+':unreviewed',timing[points[0]],timing[points[-1]])
        result['rule_template_status']={case:evaluate_template('presence' if case in ('C13','C14') else 'unresolved-state',value) for case,value in evidence.items()}
        result['scene_boundaries_reviewed']=False
        result['rule_probability_correction']=self.correction is not None
        if return_features:result['features']=features.numpy().copy();result['source_pts']=points
        return result

    def analyze(self,video,*,return_features=False):
        if self.device=='cuda':torch.cuda.synchronize()
        started=time.perf_counter();source=Path(video).resolve(strict=True);digest=source_hash(source,2*1024**3);metadata,_=probe_video(source)
        if metadata['duration_sec']>180:raise ValueError('source duration budget')
        row={'video_id':'raw-'+digest[:24],'path':source.name,'sha256':digest,'canonical_id':'sha256:'+digest,'group_id':'sha256:'+digest,
             'split':'excluded','scene_id':'unreviewed','official_label':None,'provenance':{'kind':'original','source_id':digest,'sha256':digest},**metadata}
        index=build_index(source.parent,row,dataset_version='spatial-raw-v1',split_version='not-training')
        maps,priors,points=self.encode(source.parent,index);result=self.predict_maps(maps,priors,points,index,return_features)
        if self.device=='cuda':torch.cuda.synchronize()
        return {**result,'source_sha256':digest,'threshold':self.metadata['threshold'],
                'prediction':'violation' if result['score']>=self.metadata['threshold'] else 'no_violation',
                'elapsed_seconds':time.perf_counter()-started,'model_sha256':self.metadata['weights_sha256'],
                'production_ready':False,'event_intervals_validated':False,'extra_labels_human_approved':False}

def evaluate_reserved(experiment,bundle):
    out=Path(experiment)
    if (out/'reserved_report.json').exists():raise ValueError('reserved evaluation already exists')
    frozen=decision(experiment);plan=read_json(out/'protocol.json');predictor=Predictor(bundle)
    if predictor.metadata['original_fit_sha256']!=frozen['fit_sha256']:raise ValueError('bundle/decision mismatch')
    doc=read_json(Path(plan['cache'])/'cache.json');prepared=Path(doc['prepared_dir']);source=Path(read_json(prepared/'readiness.json')['source_root'])
    labels={v['video_id']:v for v in read_json(prepared/'labels.json')['videos']};predictions=[]
    for video in plan['reserved_ids']:
        label=labels[video];result=predictor.analyze(source/label['video_path'])
        if result['source_sha256']!=label['source_sha256']:raise ValueError('reserved source changed')
        predictions.append({'video_id':video,'truth':label['verdict']=='violation','score':result['score'],'elapsed_seconds':result['elapsed_seconds']})
        atomic_json(out/(video+'.reserved.json'),result)
    report={'role':'previously_observed_internal_holdout','uses_training':False,'predictions':predictions,
            'metrics':metrics(predictions,predictor.metadata['threshold']),'threshold':predictor.metadata['threshold'],
            'production_ready':False,'independent_external_test':False,'normative_status':'unknown'}
    atomic_json(out/'reserved_report.json',report);print(json.dumps(report),flush=True);return report

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('export');a.add_argument('--experiment',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('infer');a.add_argument('--bundle',type=Path,required=True);a.add_argument('--video',type=Path,required=True);a.add_argument('--device',choices=('cpu','cuda'),default='cuda')
    a=sub.add_parser('evaluate-reserved');a.add_argument('--experiment',type=Path,required=True);a.add_argument('--bundle',type=Path,required=True)
    a=p.parse_args(argv)
    if a.command=='export':export(a.experiment,a.output)
    elif a.command=='infer':print(json.dumps(Predictor(a.bundle,a.device).analyze(a.video)),flush=True)
    else:evaluate_reserved(a.experiment,a.bundle)

if __name__=='__main__':main()
