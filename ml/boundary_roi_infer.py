"""Portable magnified-state research model, preserving one CNN and one GRU."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from ml import boundary_roi as training,boundary_crop_inputs as data,object_state_infer as base,boundary_infer as physical
from ml.data.annotation_tasks import read_json
from ml.data.pts_index import iter_indexed_frames
from ml.data.scenes import define_scenes,sample_scenes
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint

VERSION='magnified-boundary-local-bundle-v1'

def code_hash():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()

def export(experiment,reference_bundle,output):
    out=Path(experiment);plan=read_json(out/'protocol.json');choice=read_json(out/'frozen_decision.json');binding=read_json(out/'complete.json')
    if (plan['version']!=training.VERSION or plan['code_sha256']!=training.code_hash() or plan['protocol_sha256']!=training.helpers.stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'})
        or choice['protocol_sha256']!=plan['protocol_sha256'] or choice['uses_reserved'] is not False
        or file_sha256(out/'cv_report.json')!=binding['report_sha256'] or file_sha256(out/'frozen_decision.json')!=binding['decision_sha256']):raise ValueError('magnified frozen decision changed')
    checkpoint=safe_torch_load(choice['fit'],expected_sha256=choice['fit_sha256'])
    if checkpoint['identity']['protocol']!=plan['protocol_sha256'] or checkpoint['identity']['ids']!=sorted(plan['development_ids']):raise ValueError('magnified training identity')
    source=Path(reference_bundle);base.Predictor(source,'cpu');m=read_json(source/'bundle.json')
    if m['mode']!='uniform' or m['original_fit_sha256']!=choice['reference_fit']['sha256']:raise ValueError('exact uniform reference required')
    payload=safe_torch_load(source/'weights.pt',expected_sha256=m['weights_sha256'],max_bytes=base.MAX_BYTES)
    context=safe_torch_load(checkpoint['context'],expected_sha256=checkpoint['context_sha256']);payload['state_context']=context['model']
    payload['magnified_boundary_state']={'heads':checkpoint['state'],'readout':checkpoint['readout']};payload=base.compact_state(payload)
    size=base.base.tensor_bytes(payload)
    if size>base.MAX_BYTES:raise ValueError('complete magnified model exceeds12MB')
    destination=Path(output);destination.mkdir(parents=True,exist_ok=False);atomic_checkpoint(destination/'weights.pt',payload);file_size=(destination/'weights.pt').stat().st_size
    if file_size>base.MAX_BYTES:raise ValueError('serialized magnified model exceeds12MB')
    metadata={**m,'weights_sha256':file_sha256(destination/'weights.pt'),'tensor_bytes':size,'weights_file_bytes':file_size,
              'reference_protocol_sha256':m['protocol_sha256'],'protocol_sha256':plan['protocol_sha256'],'threshold':choice['selected']['threshold'],
              'roi_extension':{**m['roi_extension'],'context_sha256':checkpoint['context_sha256']},
              'magnified_boundary_extension':{'version':VERSION,'training_code_sha256':training.code_hash(),'input_code_sha256':data.code_hash(),
                'inference_code_sha256':code_hash(),'physical_code_sha256':physical.code_hash(),'taxonomy':list(training.parent.data.TAXONOMY),
                'arm':choice['selected']['arm'],'regions':[list(r) for r in data.REGIONS],'fit_sha256':choice['fit_sha256'],'review_sha256':plan['review_sha256'],
                'human_approved':False,'recognizers_validated':False,'scores_are_calibrated_probabilities':False,'normative_status':'unknown'}}
    atomic_json(destination/'bundle.json',metadata);print(json.dumps(metadata),flush=True);return metadata

class Predictor(base.Predictor):
    def __init__(self,bundle,device='cuda'):
        super().__init__(bundle,device);ext=self.metadata.get('magnified_boundary_extension',{})
        if (ext.get('version')!=VERSION or ext.get('training_code_sha256')!=training.code_hash() or ext.get('input_code_sha256')!=data.code_hash()
            or ext.get('inference_code_sha256')!=code_hash() or ext.get('physical_code_sha256')!=physical.code_hash()
            or ext.get('taxonomy')!=list(training.parent.data.TAXONOMY) or ext.get('regions')!=[list(r) for r in data.REGIONS]
            or ext.get('arm') not in training.ARMS or ext.get('recognizers_validated') is not False or ext.get('human_approved') is not False):raise ValueError('unsupported magnified extension')
        self.magnified=safe_torch_load(Path(bundle)/'weights.pt',expected_sha256=self.metadata['weights_sha256'],max_bytes=base.MAX_BYTES)['magnified_boundary_state']
        for head,dimension in zip(self.magnified['heads'],(1920,19,989,989)):
            if head['weight'].shape!=(dimension,) or head['normalization']['mean'].shape!=(dimension,) or head['normalization']['scale'].shape!=(dimension,) or not bool((head['normalization']['scale']>0).all()) or type(head['supported'])is not bool:raise ValueError('magnified head shape')
        if len(self.magnified['heads'])!=4:raise ValueError('magnified head count')
        self.magnified_arm=ext['arm'];self._magnified_crops=None

    def encode(self,root,index):
        sample=sample_scenes(index,define_scenes(index),rate=2.);pts=[s['time']['source_pts'] for s in sample if s['image_mask']]
        if len(set(pts))!=len(sample) or not 1<=len(pts)<=360:raise ValueError('magnified source frame budget')
        selected=set(pts);pending=[];pending_crop=[];pending_pts=[];maps=[];priors=[];points=[];colors=[];crops=[]
        def flush():
            if not pending:return
            images=torch.stack(pending);n=len(images);colors.extend(base.data.color_features(images[:,0]).unbind(0))
            values=self.encoder.features(images.to(self.device).flatten(0,1)).reshape(n,3,576,14,14)
            pooled=F.avg_pool2d(values[:,0],3,stride=1,padding=1).permute(0,2,3,1);prior=self.classifier(pooled).softmax(-1)[...,self.cup_indices].sum(-1)
            crops.extend(data.descriptors(self.encoder,torch.stack(pending_crop),self.device).unbind(0))
            maps.extend(values[:,0].cpu().numpy().astype(np.float16));priors.extend(prior.cpu().numpy());points.extend(pending_pts)
            pending.clear();pending_crop.clear();pending_pts.clear()
        with torch.inference_mode():
            for timing,frame in iter_indexed_frames(Path(root),index):
                if timing['source_pts'] in selected:
                    image=frame.to_image();pending.append(torch.stack([base.data.parent.tensor(image,index,b) for b in base.data.parent.VARIANTS]));pending_crop.append(data.tensors(image,index));pending_pts.append(timing['source_pts'])
                    if len(pending)==8:flush()
            flush()
        if points!=pts:raise ValueError('magnified source PTS changed')
        self._colors=torch.stack(colors);self._magnified_crops=torch.stack(crops)
        return np.asarray(maps,dtype=np.float16),np.asarray(priors,dtype=np.float32),points

    def predict_maps(self,maps,priors,points,index,return_features=False):
        colors=self._colors;crops=self._magnified_crops;self._magnified_crops=None
        if colors is None or crops is None or crops.shape!=(len(maps),2,960):raise ValueError('source-bound magnified crops required')
        bag=data.bag_geometry(colors);context=[]
        with torch.inference_mode():
            for start in range(0,len(maps),16):context.append(self.context(torch.from_numpy(np.array(maps[start:start+16],dtype=np.float32)).to(self.device))[2].sigmoid().cpu())
        states,support=training.predict_states(self.magnified['heads'],crops,bag,torch.cat(context),self.context.state_support.cpu())
        result=super().predict_maps(maps,priors,points,index,False);ridge_score=float(training.helpers.readout_predict(self.magnified['readout'],training.parent.boundary_summary(states)));gru=result['component_scores']['gru']
        score=gru if self.magnified_arm=='legacy_uniform' else .5*(ridge_score+gru) if self.magnified_arm=='roi_blend' else ridge_score
        for n,frame in enumerate(result['frames']):
            frame['boundary_state_scores']={name:float(states[n,c]) if bool(support[c]) else None for c,name in enumerate(training.parent.data.TAXONOMY)}
            frame['boundary_recognizers_validated']=False;frame['state_scores_reference_only']=True;frame['objects_reference_only']=True
        timing={r['source_pts']:r['timestamp_sec'] for r in index['frames']};events=training.parent.observed_events(states,support,points,timing)
        result.update(score=score,selected_arm=self.magnified_arm,boundary_components={'roi_states':ridge_score,'uniform_gru':gru},
                      boundary_events=[{**e,'validated':False} for e in events],bag_remains_observations=physical.bag_remains(states,support,points,timing),
                      classifier_protocol_sha256=self.metadata['protocol_sha256'],boundary_scores_are_calibrated_probabilities=False,boundary_events_are_normative_findings=False)
        if return_features:result['features']=torch.cat((crops.flatten(1),bag),1).numpy().copy();result['source_pts']=points
        return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('export')
    for name in ('experiment','reference-bundle','output'):a.add_argument('--'+name,type=Path,required=True)
    a=s.add_parser('infer');a.add_argument('--bundle',type=Path,required=True);a.add_argument('--video',type=Path,required=True);a.add_argument('--device',choices=('cuda','cpu'),default='cuda');a=p.parse_args()
    if a.command=='export':export(a.experiment,a.reference_bundle,a.output)
    else:print(json.dumps(Predictor(a.bundle,a.device).analyze(a.video)),flush=True)
