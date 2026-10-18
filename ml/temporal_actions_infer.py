"""Standalone frozen-CNN/one-GRU temporal operation candidate, offline only."""
from __future__ import annotations
import argparse
import hashlib
import math
from pathlib import Path
import time

import numpy as np
import torch
import torchvision

from ml import temporal_actions as training
from ml import object_event_inputs as inputs
from ml.data.annotation_tasks import read_json
from ml.data.manifest import probe_video, source_hash
from ml.data.pts_index import build_index, iter_indexed_frames
from ml.data.scenes import define_scenes, sample_scenes
from ml.models.encoder import FrozenEncoder, file_sha256, safe_torch_load
from ml.video_baseline import atomic_json, atomic_checkpoint

VERSION = 'temporal-operations-local-bundle-v1'
ELIGIBILITY = {'frame_precision':.65,'frame_recall':.15,'interval_precision_proxy':.35}


def code_hash():
    return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()


def export(experiment, destination):
    experiment, destination = Path(experiment), Path(destination)
    marker = read_json(experiment/'complete.json');plan=read_json(experiment/'protocol.json')
    if (plan['code_sha256']!=training.code_hash()
            or file_sha256(experiment/'cv_report.json')!=marker['report_sha256']
            or file_sha256(experiment/'final.pt')!=marker['fit_sha256']):
        raise ValueError('Completed temporal operation artifacts changed')
    report=read_json(experiment/'cv_report.json')
    state=safe_torch_load(experiment/'final.pt',expected_sha256=marker['fit_sha256'])
    if (state['train_ids']!=sorted(plan['development_ids']) or state['protocol_sha256']!=plan['protocol_sha256']
            or report['protocol_sha256']!=plan['protocol_sha256']):raise ValueError('Temporal operation fit lineage')
    encoder=FrozenEncoder(weights_path=Path(plan['encoder_weights']),weights_sha256=plan['encoder_sha256'])
    statistics={r['class']:r for r in report['results']['temporal_actions']['actions']['classes']}
    eligible=[False]
    for c,name in enumerate(training.TAXONOMY[1:],1):
        row=statistics[name]
        eligible.append(bool(state['fine_support'][c]) and row['precision']>=ELIGIBILITY['frame_precision']
                        and row['recall']>=ELIGIBILITY['frame_recall']
                        and row['interval_precision_proxy']>=ELIGIBILITY['interval_precision_proxy'])
    payload={'encoder':{k:v.cpu().clone() for k,v in encoder.features.state_dict().items()},
             'threshold':state['threshold'],'action_thresholds':state['action_thresholds'],
             'fine_eligible':eligible,'clip_promoted':report['promoted_clip_model'],'protocol_sha256':plan['protocol_sha256'],
             **{k:state[k] for k in ('model','normalization','fine_support','coarse_support')}}
    destination.mkdir(parents=True,exist_ok=False)
    atomic_checkpoint(destination/'weights.pt',payload)
    if (destination/'weights.pt').stat().st_size>training.MAX_BYTES:raise ValueError('Operation bundle exceeds12MB')
    atomic_json(destination/'evaluation.json',report)
    metadata={'version':VERSION,'weights_sha256':file_sha256(destination/'weights.pt'),'evaluation_sha256':file_sha256(destination/'evaluation.json'),
              'training_code_sha256':training.code_hash(),'inference_code_sha256':code_hash(),'protocol_sha256':plan['protocol_sha256'],
              'original_fit_sha256':marker['fit_sha256'],'encoder_pretrained_sha256':plan['encoder_sha256'],
              'taxonomy':list(training.TAXONOMY),'coarse':list(training.COARSE),'fine_eligible':eligible,'eligibility':ELIGIBILITY,
              'threshold':state['threshold'],'action_thresholds':state['action_thresholds'],
              'input_version':inputs.VERSION,'size':448,'rate':2.,'roi':list(inputs.base.ROI),'map_dtype':'float16',
              'clip_promoted':report['promoted_clip_model'],'prototype_only':True,'production_ready':False,
              'recognizers_validated':False,'normative_status':'unknown','extra_labels_human_approved':False}
    atomic_json(destination/'bundle.json',metadata)
    return metadata


class Predictor:
    def __init__(self, bundle, device='cuda'):
        torch.set_num_threads(4);self.device=device;bundle=Path(bundle)
        self.metadata=read_json(bundle/'bundle.json');m=self.metadata
        if (m['version']!=VERSION or m['training_code_sha256']!=training.code_hash() or m['inference_code_sha256']!=code_hash()
                or m['taxonomy']!=list(training.TAXONOMY) or m['coarse']!=list(training.COARSE)
                or m['input_version']!=inputs.VERSION or m['size']!=448 or m['rate']!=2.
                or m['roi']!=list(inputs.base.ROI) or m['map_dtype']!='float16'
                or m['production_ready'] is not False or m['normative_status']!='unknown' or m['prototype_only'] is not True
                or m['eligibility']!=ELIGIBILITY or len(m['fine_eligible'])!=len(training.TAXONOMY)
                or len(m['action_thresholds'])!=len(training.TAXONOMY)
                or any(type(v)is not bool for v in m['fine_eligible'])
                or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=1 for v in m['action_thresholds'])
                or type(m['threshold']) not in (int,float) or not math.isfinite(m['threshold']) or not 0<=m['threshold']<=1):
            raise ValueError('Unsupported temporal operation bundle')
        if file_sha256(bundle/'evaluation.json')!=m['evaluation_sha256']:raise ValueError('Operation evaluation changed')
        report=read_json(bundle/'evaluation.json')
        if report['protocol_sha256']!=m['protocol_sha256'] or report['promoted_clip_model']!=m['clip_promoted']:
            raise ValueError('Operation evaluation lineage')
        state=safe_torch_load(bundle/'weights.pt',expected_sha256=m['weights_sha256'],max_bytes=training.MAX_BYTES)
        if any(state[k]!=m[k] for k in ('threshold','action_thresholds','fine_eligible','clip_promoted','protocol_sha256')):
            raise ValueError('Operation decision metadata changed')
        self.encoder=torchvision.models.mobilenet_v3_small(weights=None).features.to(device).eval().requires_grad_(False)
        self.encoder.load_state_dict(state['encoder'],strict=True)
        self.model=training.TemporalOperations().to(device).eval();self.model.load_state_dict(state['model'],strict=True)
        self.norm=state['normalization'];self.fine_support=state['fine_support'];self.coarse_support=state['coarse_support']
        if self.fine_support.shape!=(len(training.TAXONOMY),) or self.coarse_support.shape!=(len(training.COARSE),):
            raise ValueError('Operation recognizer support shape')
        if self.norm['mean'].shape!=(training.DIM,) or self.norm['scale'].shape!=(training.DIM,) or (self.norm['scale']<=0).any():
            raise ValueError('Operation normalizer shape')
        self.evaluation=report['results']['temporal_actions']

    def encode(self, root, index):
        samples=sample_scenes(index,define_scenes(index),rate=2.)
        points=[s['time']['source_pts'] for s in samples if s['image_mask']]
        if len(set(points))!=len(samples) or not 1<=len(points)<=360:raise ValueError('Operation source sample budget')
        selected=set(points);pending=[];decoded=[];values=[]
        def flush():
            if not pending:return
            maps=self.encoder(torch.stack(pending).to(self.device)).cpu().to(torch.float16).to(torch.float32)
            values.append(training.features(maps));pending.clear()
        with torch.inference_mode():
            for timing,frame in iter_indexed_frames(Path(root),index):
                if timing['source_pts'] in selected:
                    pending.append(inputs.tensor(frame.to_image(),index,1.));decoded.append(timing['source_pts'])
                    if len(pending)==8:flush()
            flush()
        if decoded!=points:raise ValueError('Operation source PTS mismatch')
        return torch.cat(values),points

    def predict_features(self, values, points, times):
        if values.shape!=(len(points),training.DIM) or len(points)!=len(times) or not torch.isfinite(values).all():
            raise ValueError('Operation input feature shape')
        x=((values-self.norm['mean'])/self.norm['scale']).to(self.device)
        with torch.inference_mode():
            video,coarse,fine=self.model(x[None],torch.tensor([len(x)]))
            coarse=coarse[0].sigmoid().cpu();fine=fine[0].softmax(-1).cpu()
        frames=[]
        thresholds={name:.5 for name in training.COARSE}
        thresholds.update({name:self.metadata['action_thresholds'][c] for c,name in enumerate(training.TAXONOMY) if c})
        for n,(point,timestamp) in enumerate(zip(points,times)):
            scores={name:float(coarse[n,c]) if bool(self.coarse_support[c]) else None for c,name in enumerate(training.COARSE)}
            scores.update({name:float(fine[n,c]) if bool(self.fine_support[c]) and self.metadata['fine_eligible'][c] else None
                           for c,name in enumerate(training.TAXONOMY) if c})
            frames.append({'source_pts':point,'timestamp_sec':timestamp,'state_scores':scores,'objects':[]})
        events=[]
        for name,threshold in thresholds.items():
            current=[]
            def end():
                if current:events.append({'action':name,'source_pts':[f['source_pts'] for f in current],
                    'start_sec':current[0]['timestamp_sec'],'end_sec':current[-1]['timestamp_sec'],'interval_validated':False})
            for frame in frames:
                score=frame['state_scores'].get(name)
                if score is not None and score>=threshold:
                    if current and frame['timestamp_sec']-current[-1]['timestamp_sec']>.75:end();current=[]
                    current.append(frame)
                elif current:end();current=[]
            end()
        return {'score':float(video.sigmoid()[0]),'frames':frames,'candidate_events':events,'event_thresholds':thresholds,
                'normative_status':'unknown','production_ready':False,'event_intervals_validated':False,
                'state_scores_are_calibrated_probabilities':False,'selected_arm':'temporal_actions'}

    def analyze(self, video):
        started=time.perf_counter();source=Path(video).resolve(strict=True);digest=source_hash(source,2*1024**3)
        metadata,_=probe_video(source)
        if metadata['duration_sec']>180:raise ValueError('Operation source duration budget')
        row={'video_id':'raw-'+digest[:24],'path':source.name,'sha256':digest,'canonical_id':'sha256:'+digest,'group_id':'sha256:'+digest,
             'split':'excluded','scene_id':'unreviewed','official_label':None,'provenance':{'kind':'original','source_id':digest,'sha256':digest},**metadata}
        index=build_index(source.parent,row,dataset_version=VERSION,split_version='not-training')
        features,points=self.encode(source.parent,index)
        timing={f['source_pts']:f['timestamp_sec'] for f in index['frames']}
        result=self.predict_features(features,points,[timing[p] for p in points])
        if self.device=='cuda':torch.cuda.synchronize()
        threshold=self.metadata['threshold']
        return {**result,'source_sha256':digest,'threshold':threshold,'prediction':'violation' if result['score']>=threshold else 'no_violation',
                'elapsed_seconds':time.perf_counter()-started,'model_sha256':self.metadata['weights_sha256'],
                'protocol_sha256':self.metadata['protocol_sha256'],'extra_labels_human_approved':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('export');p.add_argument('--experiment',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('infer');p.add_argument('--bundle',type=Path,required=True);p.add_argument('--video',type=Path,required=True);p.add_argument('--device',default='cuda')
    args=parser.parse_args()
    if args.command=='export':result=export(args.experiment,args.output)
    else:result=Predictor(args.bundle,args.device).analyze(args.video)
    import json
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
