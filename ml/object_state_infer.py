"""Local object ROI state bundle; one CNN, one GRU, explicit research gates."""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from ml import object_state_refine as training,state_focus as helpers,state_focus_inputs as data,object_events_infer as base
from ml import object_state_ensemble as ensemble
from ml import object_state_local as local,object_state_consensus as consensus
from ml import object_state_transitions as transitions
from ml.data.annotation_tasks import read_json
from ml.data.pts_index import iter_indexed_frames
from ml.data.scenes import define_scenes,sample_scenes
from ml.models.encoder import file_sha256,safe_torch_load,FrozenEncoder
from ml.video_baseline import atomic_json,atomic_checkpoint

VERSION='object-roi-state-local-bundle-v2'
MAX_BYTES=12_000_000

def code_hash():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()

def compact_state(value):
    """Serialize logical tensor values without backing storage of larger views."""
    if isinstance(value,torch.Tensor):return value.detach().cpu().contiguous().clone()
    if isinstance(value,dict):return {k:compact_state(v) for k,v in value.items()}
    if isinstance(value,list):return [compact_state(v) for v in value]
    if isinstance(value,tuple):return tuple(compact_state(v) for v in value)
    return value

def decision(directory):
    out=Path(directory);marker=read_json(out/'complete.json');plan=read_json(out/'protocol.json')
    pipeline={training.VERSION:training,ensemble.VERSION:ensemble,local.VERSION:local,consensus.VERSION:consensus,transitions.VERSION:transitions}.get(plan['version'])
    if pipeline is None:raise ValueError('unsupported ROI pipeline')
    if plan['code_sha256']!=pipeline.code_hash() or plan['protocol_sha256']!=helpers.stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'}) or file_sha256(out/'cv_report.json')!=marker['report_sha256'] or file_sha256(out/'frozen_decision.json')!=marker['decision_sha256']:raise ValueError('ROI decision changed')
    choice=read_json(out/'frozen_decision.json')
    if choice['protocol_sha256']!=plan['protocol_sha256'] or choice['uses_reserved'] is not False or file_sha256(choice['fit'])!=choice['fit_sha256']:raise ValueError('selected ROI fit changed')
    return plan,choice

def export(experiment,output):
    plan,choice=decision(experiment);parent=base.decision(plan['parent']);parent_plan=read_json(Path(plan['parent'])/'protocol.json')
    state_core=local if plan['version'] in (local.VERSION,consensus.VERSION,transitions.VERSION) else training
    selector=transitions if plan['version']==transitions.VERSION else consensus if plan['version']==consensus.VERSION else ensemble if plan['version']==ensemble.VERSION else None
    clip=safe_torch_load(choice['fit'],expected_sha256=choice['fit_sha256']);frame=safe_torch_load(clip['frame_fit'],expected_sha256=clip['frame_sha256'])
    fit_protocol=plan.get('roi_protocol_sha256',plan['protocol_sha256'])
    if clip['identity']['protocol']!=fit_protocol or frame['identity']['ids']!=sorted(plan['development_ids']) or frame['identity']['protocol']!=fit_protocol:raise ValueError('ROI lineage')
    candidate=choice['selected']['candidate'];reference={'fit':parent['fit'],'sha256':parent['fit_sha256']}
    if candidate['arm']=='blend':reference=read_json(Path(experiment)/'final_reference.json')
    if choice.get('reference_fit'):reference=choice['reference_fit']
    neural=safe_torch_load(reference['fit'],expected_sha256=reference['sha256']);spatial=safe_torch_load(neural['spatial'],expected_sha256=neural['spatial_sha256'])
    context=safe_torch_load(frame['context'],expected_sha256=frame['context_sha256'])
    if neural['identity']['ids']!=sorted(plan['development_ids']) or neural['identity']['protocol']!=parent_plan['protocol_sha256'] or (candidate['arm'] in ('blend','state_blend','policy_blend','transition_blend','legacy_uniform') and neural['identity']['mode']!='uniform'):raise ValueError('reference lineage')
    marker=read_json(Path(parent_plan['spatial'])/'inputs.json');encoder=FrozenEncoder(weights_path=Path(marker['encoder_weights']),weights_sha256=marker['encoder_sha256'])
    classifier=data.parent.cup_classifier(Path(marker['encoder_weights']),marker['encoder_sha256'])
    payload={'format':base.VERSION,'encoder':dict(encoder.features.state_dict()),'cup_classifier':dict(classifier.state_dict()),
             'spatial':spatial['model'],'temporal':neural['model'],'normalization':neural['normalization'],'cup_calibration':spatial['cup_calibration'],
             'rule_head':neural['rule_head'],'rule_mean':neural['rule_mean'],'rule_std':neural['rule_std'],
             'roi_state':frame['state'],'state_context':context['model'],'roi_readout':clip['readout']}
    payload=compact_state(payload);size=base.tensor_bytes(payload)
    if size>MAX_BYTES:raise ValueError('full FP32 model exceeds12MB')
    out=Path(output);out.mkdir(parents=True,exist_ok=False);atomic_checkpoint(out/'weights.pt',payload)
    file_bytes=(out/'weights.pt').stat().st_size
    if file_bytes>MAX_BYTES:raise ValueError('serialized ROI model exceeds12MB')
    metadata={'version':base.VERSION,'weights_sha256':file_sha256(out/'weights.pt'),'original_fit_sha256':reference['sha256'],
              'spatial_fit_sha256':neural['spatial_sha256'],'protocol_sha256':plan['protocol_sha256'],
              'arm':'uniform_gru' if neural['identity']['mode']=='uniform' else parent['selected']['arm'],'mode':neural['identity']['mode'],
              'threshold':choice['selected']['threshold'],'input_version':data.parent.VERSION,'size':448,'rate':2.,'variants':list(data.parent.VARIANTS),
              'map_dtype':'float16','roi':list(data.parent.base.ROI),'taxonomy':list(data.parent.TAXONOMY),'objects':list(data.parent.OBJECTS),
              'cup_classes':['coffee mug','cup'],'training_code_sha256':training.original.code_hash(),'inference_code_sha256':base.code_hash(),
              'tensor_bytes':size,'weights_file_bytes':file_bytes,'production_ready':False,'recognizers_validated':False,'normative_status':'unknown','human_approved_extra_labels':False,
              'roi_extension':{'version':VERSION,'training_code_sha256':state_core.code_hash(),'inference_code_sha256':code_hash(),
                               'pipeline_version':plan['version'],'ensemble_code_sha256':selector.code_hash() if selector else None,
                               'input_code_sha256':data.code_hash(),'candidate':candidate,'taxonomy':list(data.TAXONOMY),
                               'fit_sha256':choice['fit_sha256'],'frame_sha256':clip['frame_sha256'],'context_sha256':frame['context_sha256'],
                               'scores_are_calibrated_probabilities':False,'cup_prior_excluded_from_new_rules':True,
                               'reference_gru_has_original_metadata':True,'appearance_is_os_state':False}}
    atomic_json(out/'bundle.json',metadata);print(json.dumps(metadata),flush=True);return metadata

class Predictor(base.Predictor):
    def __init__(self,bundle,device='cuda'):
        super().__init__(bundle,device);m=self.metadata;ext=m.get('roi_extension',{})
        version=ext.get('pipeline_version',training.VERSION)
        self.state_core=local if version in (local.VERSION,consensus.VERSION,transitions.VERSION) else training
        selector=transitions if version==transitions.VERSION else consensus if version==consensus.VERSION else ensemble if version==ensemble.VERSION else None
        self.transition_policy=version==transitions.VERSION
        allowed=selector.candidates() if selector else helpers.candidates()
        if version not in (training.VERSION,ensemble.VERSION,local.VERSION,consensus.VERSION,transitions.VERSION) or ext.get('version')!=VERSION or ext.get('training_code_sha256')!=self.state_core.code_hash() or ext.get('inference_code_sha256')!=code_hash() or ext.get('input_code_sha256')!=data.code_hash() or ext.get('taxonomy')!=list(data.TAXONOMY) or ext.get('candidate') not in allowed or (selector and ext.get('ensemble_code_sha256')!=selector.code_hash()):raise ValueError('unsupported ROI extension')
        state=safe_torch_load(Path(bundle)/'weights.pt',expected_sha256=m['weights_sha256'],max_bytes=MAX_BYTES)
        if m.get('weights_file_bytes')!=(Path(bundle)/'weights.pt').stat().st_size:raise ValueError('serialized ROI size mismatch')
        if base.tensor_bytes(state)!=m['tensor_bytes'] or base.tensor_bytes(state)>MAX_BYTES:raise ValueError('ROI size mismatch')
        self.state=state['roi_state'];self.readout=state['roi_readout'];self.candidate=ext['candidate']
        if self.candidate['arm'] in ('blend','state_blend','policy_blend','transition_blend','legacy_uniform') and m['mode']!='uniform':raise ValueError('uniform reference required')
        self.context=training.original.SpatialHeads().to(device).eval();self.context.load_state_dict(state['state_context'],strict=True)
        for name,dim in (('bag',583),('safe',1372),('laptop',1372),('bag_appearance',5247),('safe_appearance',5247),('laptop_appearance',5247)):
            model=self.state[name]
            if model['weight'].shape[0]!=dim or model['normalization']['mean'].shape!=(dim,) or model['normalization']['scale'].shape!=(dim,) or (model['normalization']['scale']<=0).any():raise ValueError('ROI head shape')
        if (self.candidate['arm'] in ('persistent','policy_blend','transition','transition_blend','legacy_uniform'))!=(self.readout is None):raise ValueError('ROI readout mismatch')
        if self.state_core is local:
            p=self.state['bag_presence'];d=self.state['door_state']
            if p['weight'].shape!=(19,) or p['normalization']['mean'].shape!=(19,) or d['weight'].shape!=(data.DIM,) or d['normalization']['mean'].shape!=(data.DIM,):raise ValueError('local appearance head shape')
        self._colors=None

    def encode(self,root,index):
        sample=sample_scenes(index,define_scenes(index),rate=2.);pts=[s['time']['source_pts'] for s in sample if s['image_mask']]
        if len(set(pts))!=len(sample) or not 1<=len(pts)<=360:raise ValueError('source frame budget')
        select=set(pts);pending=[];pending_pts=[];points=[];maps=[];priors=[];colors=[]
        def flush():
            if not pending:return
            images=torch.stack(pending);n=len(images);colors.extend(data.color_features(images[:,0]).unbind(0))
            values=self.encoder.features(images.to(self.device).flatten(0,1)).reshape(n,3,576,14,14)
            pooled=F.avg_pool2d(values[:,0],3,stride=1,padding=1).permute(0,2,3,1)
            prior=self.classifier(pooled).softmax(-1)[...,self.cup_indices].sum(-1)
            maps.extend(values[:,0].cpu().numpy().astype(np.float16));priors.extend(prior.cpu().numpy());points.extend(pending_pts)
            pending.clear();pending_pts.clear()
        with torch.inference_mode():
            for timing,frame in iter_indexed_frames(Path(root),index):
                if timing['source_pts'] in select:
                    pending.append(torch.stack([data.parent.tensor(frame.to_image(),index,b) for b in data.parent.VARIANTS]));pending_pts.append(timing['source_pts'])
                    if len(pending)==8:flush()
            flush()
        if points!=pts:raise ValueError('source color/CNN PTS mismatch')
        self._colors=torch.stack(colors)
        return np.asarray(maps,dtype=np.float16),np.asarray(priors,dtype=np.float32),points

    def predict_features(self,features,maps_color,context_scores,reference_gru=None):
        if features.ndim!=2 or features.shape[1]!=data.DIM or maps_color.shape!=(len(features),583,14,14) or context_scores.shape!=(len(features),18) or not 1<=len(features)<=360 or not torch.isfinite(features).all() or not torch.isfinite(maps_color).all():raise ValueError('ROI source feature shapes')
        p,support,boxes=self.state_core.refine_predict(self.state,maps_color,features[:,data.CNN_DIM:],context_scores,self.context.state_support.cpu())
        if self.transition_policy:
            risk,available=transitions.probes(p,support);score=float(risk.amax())
            if self.candidate['arm'] in ('transition_blend','legacy_uniform'):
                if reference_gru is None or not math.isfinite(reference_gru) or not 0<=reference_gru<=1:raise ValueError('reference GRU required')
                score=reference_gru if self.candidate['arm']=='legacy_uniform' else .5*(score+reference_gru)
            return score,p,support,risk,available,boxes
        arm={'state_blend':'states','policy_blend':'persistent','legacy_uniform':'persistent'}.get(self.candidate['arm'],self.candidate['arm'])
        summarizer=local.state_summary if self.state_core is local else helpers.state_summary
        summary,risk,available=summarizer(p,support);x,_=helpers.readout_features(arm,helpers.visual_summary(features),summary)
        score=float(risk[:4].amax()) if arm=='persistent' else float(helpers.readout_predict(self.readout,x))
        if self.candidate['arm'] in ('blend','state_blend','policy_blend','legacy_uniform'):
            if reference_gru is None or not math.isfinite(reference_gru) or not 0<=reference_gru<=1:raise ValueError('reference GRU required')
            score=reference_gru if self.candidate['arm']=='legacy_uniform' else .5*(score+reference_gru)
        return score,p,support,risk,available,boxes

    def predict_maps(self,maps,priors,points,index,return_features=False):
        colors=self._colors;self._colors=None
        if colors is None or colors.shape!=(len(maps),data.COLOR_DIM):raise ValueError('source-bound colors required')
        result=super().predict_maps(maps,priors,points,index,False);features=data.combine(torch.from_numpy(np.array(maps,dtype=np.float32)),colors);context=[]
        with torch.inference_mode():
            for start in range(0,len(maps),16):context.append(self.context(torch.from_numpy(np.array(maps[start:start+16],dtype=np.float32)).to(self.device))[2].sigmoid().cpu())
        maps_color=torch.cat((torch.from_numpy(np.array(maps,dtype=np.float32)),colors.reshape(-1,7,14,14)),1)
        score,states,support,risk,available,boxes=self.predict_features(features,maps_color,torch.cat(context),result['component_scores']['gru'])
        for n,frame in enumerate(result['frames']):
            frame['state_scores']={name:float(states[n,c]) if bool(support[c]) else None for c,name in enumerate(data.TAXONOMY)}
            frame['object_rois']={name:base.displayed_box([(float(box[n,0])+float(box[n,2]))/2,(float(box[n,1])+float(box[n,3]))/2,float(box[n,2]-box[n,0]),float(box[n,3]-box[n,1])],index) for name,box in boxes.items() if self.state[name]['supported'] and (name!='bag' or states[n,18]>=.5)}
            frame['object_rois_validated']=False
            frame['reference_objects']=frame['objects'];frame['objects']=[o for o in frame['objects'] if o['class']!='green_bag']
            if bool(support[18]) and states[n,18]>=.5 and frame['object_rois'].get('bag'):
                frame['objects'].append({'class':'green_bag','score':float(states[n,18]),'box_displayed_xyxy':frame['object_rois']['bag'],
                                         'score_is_calibrated':False,'localization_validated':False})
        timing={r['source_pts']:r['timestamp_sec'] for r in index['frames']};events=[]
        for c,name in enumerate(data.TAXONOMY):
            if not bool(support[c]):continue
            current=[]
            def end_run():
                if current:events.append({'action':name,'source_pts':current.copy(),'start_sec':timing[current[0]],'end_sec':timing[current[-1]],'interval_validated':False})
            for n,point in enumerate(points):
                if states[n,c]>=.5:
                    if current and timing[point]-timing[current[-1]]>.75:end_run();current=[]
                    current.append(point)
                elif current:end_run();current=[]
            end_run()
        result.update(score=score,selected_arm=self.candidate['name'],candidate_events=events,
                      rule_probes=[{'probe':name,'score':float(risk[c]) if bool(available[c]) else None,'observation_status':'experimental' if bool(available[c]) else 'unknown',
                                    'normative_status':'unknown','recognizer_validated':False} for c,name in enumerate(transitions.RULES if self.transition_policy else local.RULES if self.state_core is local else helpers.RULES)],
                      state_scores_are_calibrated_probabilities=False,appearance_is_os_state=False,cup_prior_excluded_from_new_rules=True,
                      component_scores_are_reference_only=True,
                      classifier_protocol_sha256=self.metadata['protocol_sha256'])
        if return_features:result['features']=features.numpy().copy();result['source_pts']=points
        return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('export');a.add_argument('--experiment',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=s.add_parser('infer');a.add_argument('--bundle',type=Path,required=True);a.add_argument('--video',type=Path,required=True);a.add_argument('--device',choices=('cpu','cuda'),default='cuda');a=p.parse_args()
    if a.command=='export':export(a.experiment,a.output)
    else:print(json.dumps(Predictor(a.bundle,a.device).analyze(a.video)),flush=True)
