"""Portable weak-risk extension; retains exactly one original CNN and one GRU."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import json
import numpy as np
import torch
from torch.nn.utils.rnn import pad_packed_sequence
from ml import temporal_risk as training
from ml import operation_crops as crops
from ml import object_state_infer as base
from ml.object_events_infer import tensor_bytes
from ml.models.encoder import file_sha256,safe_torch_load
from ml.data.annotation_tasks import read_json
from ml.data.pts_index import iter_indexed_frames
from ml.video_baseline import atomic_checkpoint,atomic_json

VERSION='weak-risk-local-extension-v1'
LOCALIZATION_GATE={'peak_hit_rate':.6,'weak_frame_f1':.5}


def code_hash():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()


def enabled(report):
    localization=report['localization'];n=localization['positive_videos_with_intervals']
    local=bool(n and localization['peak_in_weak_interval']/n>=LOCALIZATION_GATE['peak_hit_rate']
               and localization['weak_frame_f1']>=LOCALIZATION_GATE['weak_frame_f1'])
    baseline={k:float(np.mean([m[k] for m in report['comparisons']['base_control'].values()]))
              for k in ('accuracy','balanced_accuracy','macro_f1')}
    clip=report['promoted'] and all(report['nested_mean'][k]>=baseline[k] for k in baseline)
    return bool(clip),local


def export(experiment,parent,destination):
    experiment,parent,destination=Path(experiment),Path(parent),Path(destination)
    plan=read_json(experiment/'protocol.json');marker=read_json(experiment/'complete.json')
    if (plan['code_sha256']!=training.code_hash() or file_sha256(experiment/'cv_report.json')!=marker['report_sha256']
            or file_sha256(experiment/'final.pt')!=marker['fit_sha256']):raise ValueError('Risk experiment changed')
    report=read_json(experiment/'cv_report.json');clip_enabled,local_enabled=enabled(report)
    head=safe_torch_load(experiment/'final.pt',expected_sha256=marker['fit_sha256'])
    if head['train_ids']!=sorted(plan['development_ids']) or head['protocol_sha256']!=plan['protocol_sha256']:raise ValueError('Risk fit lineage')
    metadata=read_json(parent/'bundle.json')
    # Load and verify the actual original portable model before extending it.
    original=base.Predictor(parent,'cpu');del original
    if metadata.get('risk_extension'):raise ValueError('Cannot recursively extend a risk package')
    payload=safe_torch_load(parent/'weights.pt',expected_sha256=metadata['weights_sha256'],max_bytes=base.MAX_BYTES)
    metrics=report['nested_mean'] if clip_enabled else plan['control']
    decisions={'selected_arm':head['selected_arm'],'event_threshold':head['event_threshold'],
               'clip_threshold':head['threshold'],'base_threshold':metadata['threshold'],
               'clip_enabled':clip_enabled,'localizer_enabled':local_enabled,'protocol_sha256':plan['protocol_sha256'],
               'clip_metrics':metrics,'evaluation_sha256':marker['report_sha256']}
    payload['weak_risk']={'head':{k:head[k] for k in ('weight','bias','mean','scale')},'decisions':decisions}
    destination.mkdir(parents=True,exist_ok=False);atomic_checkpoint(destination/'weights.pt',payload)
    size=(destination/'weights.pt').stat().st_size
    if size>base.MAX_BYTES:raise ValueError('Extended model exceeds12MB')
    atomic_json(destination/'evaluation.json',report)
    extension={'version':VERSION,'training_code_sha256':training.code_hash(),'inference_code_sha256':code_hash(),
               'crop_code_sha256':crops.code_hash(),'rois':crops.ROIS,'localization_gate':LOCALIZATION_GATE,
               'parent_weights_sha256':metadata['weights_sha256'],'weak_labels':True,'normative_status':'unknown',**decisions}
    metadata.update(weights_sha256=file_sha256(destination/'weights.pt'),weights_file_bytes=size,tensor_bytes=tensor_bytes(payload),
                    threshold=head['threshold'] if clip_enabled else metadata['threshold'],risk_extension=extension)
    atomic_json(destination/'bundle.json',metadata)
    return extension


class Predictor(base.Predictor):
    def __init__(self,bundle,device='cuda'):
        super().__init__(bundle,device);ext=self.metadata.get('risk_extension',{})
        if (ext.get('version')!=VERSION or ext.get('training_code_sha256')!=training.code_hash()
                or ext.get('inference_code_sha256')!=code_hash() or ext.get('crop_code_sha256')!=crops.code_hash()
                or ext.get('rois')!=[list(r) for r in crops.ROIS] or ext.get('localization_gate')!=LOCALIZATION_GATE
                or ext.get('normative_status')!='unknown' or ext.get('weak_labels') is not True):raise ValueError('Unsupported risk extension')
        state=safe_torch_load(Path(bundle)/'weights.pt',expected_sha256=self.metadata['weights_sha256'],max_bytes=base.MAX_BYTES)['weak_risk']
        if any(ext[k]!=v for k,v in state['decisions'].items()):raise ValueError('Risk decisions changed')
        if file_sha256(Path(bundle)/'evaluation.json')!=ext['evaluation_sha256']:raise ValueError('Risk evaluation changed')
        report=read_json(Path(bundle)/'evaluation.json')
        if enabled(report)!=(ext['clip_enabled'],ext['localizer_enabled']) or report['protocol_sha256']!=ext['protocol_sha256']:
            raise ValueError('Risk evaluation lineage')
        self.head=state['head'];self.risk_decisions=state['decisions'];self._details=None
        if (self.head['weight'].shape!=(training.DIM,) or self.head['mean'].shape!=(training.DIM,)
                or self.head['scale'].shape!=(training.DIM,) or (self.head['scale']<=0).any()):raise ValueError('Risk head shape')

    def encode(self,root,index):
        maps,priors,points=super().encode(root,index)
        selected=set(points);decoded=[];pending=[];tokens=[]
        def flush():
            if not pending:return
            images=torch.cat(pending).to(self.device)
            values=self.encoder.features(images).cpu().to(torch.float16).to(torch.float32)
            tokens.append(values.mean((-2,-1)).reshape(len(pending),4*576));pending.clear()
        with torch.inference_mode():
            for timing,frame in iter_indexed_frames(Path(root),index):
                if timing['source_pts'] in selected:
                    pending.append(crops.tensors(frame.to_image(),index));decoded.append(timing['source_pts'])
                    if len(pending)==4:flush()
            flush()
        if decoded!=points:raise ValueError('Risk detail source PTS mismatch')
        self._details=torch.cat((torch.from_numpy(np.array(maps,dtype=np.float32)).mean((-2,-1)),torch.cat(tokens)),1)
        return maps,priors,points

    def predict_maps(self,maps,priors,points,index,return_features=False):
        details=self._details;self._details=None
        if details is None or len(details)!=len(points):raise ValueError('Source-bound risk detail features required')
        captured=[]
        hook=self.temporal.gru.register_forward_hook(lambda module,args,out:captured.append(pad_packed_sequence(out[0],batch_first=True)[0].detach().cpu()))
        try:result=super().predict_maps(maps,priors,points,index,return_features)
        finally:hook.remove()
        if len(captured)!=1:raise ValueError('Risk extension must reuse exactly one GRU forward')
        values=training.combine(captured[0][0],details)
        z=(values-self.head['mean'])/self.head['scale']
        p=(z@self.head['weight']+self.head['bias']).sigmoid()
        before=torch.cat((p[:1],p[:-1]));after=torch.cat((p[1:],p[-1:]));p=.25*before+.5*p+.25*after
        score=float(p.topk(min(3,len(p))).values.mean());d=self.risk_decisions
        result['reference_clip_score']=result['score'];result['weak_risk_score']=score
        if d['clip_enabled']:
            if d['selected_arm']=='risk_localizer':result['score']=score
            elif d['selected_arm']=='risk_blend':result['score']=.5*(result['score']+score)
        result['clip_metrics']=d['clip_metrics'];result['risk_localizer_enabled']=d['localizer_enabled']
        if d['localizer_enabled']:
            threshold=d['event_threshold'];current=[];events=[]
            def end():
                if current:events.append({'action':'risk_candidate','source_pts':[f['source_pts'] for f in current],
                     'start_sec':current[0]['timestamp_sec'],'end_sec':current[-1]['timestamp_sec'],'interval_validated':False})
            for n,frame in enumerate(result['frames']):
                probability=float(p[n]);frame['weak_risk_score']=probability
                # A decision score, explicitly not a calibrated probability: .5 iff p>=threshold.
                frame['state_scores']['risk_candidate']=probability/(probability+threshold)
                if probability>=threshold:
                    if current and frame['timestamp_sec']-current[-1]['timestamp_sec']>.75:end();current=[]
                    current.append(frame)
                elif current:end();current=[]
            end();result['candidate_events'].extend(events)
        result['weak_scenario_interpretations_are_verified_findings']=False
        return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('export');a.add_argument('--experiment',type=Path,required=True);a.add_argument('--parent',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('infer');a.add_argument('--bundle',type=Path,required=True);a.add_argument('--video',type=Path,required=True);a.add_argument('--device',default='cuda')
    args=p.parse_args()
    if args.command=='export':result=export(args.experiment,args.parent,args.output)
    else:result=Predictor(args.bundle,args.device).analyze(args.video)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
