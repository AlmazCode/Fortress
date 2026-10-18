"""Stronger frozen visual features, nested grouped selection, no new sources.

The old 12MB/CNN/GRU budget is a research choice, not a ForteBank requirement.
DINOv2 is frozen; only a small deterministic ridge readout is fitted locally.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F

from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import display_transform, transformed_image
from ml.data.pts_index import iter_indexed_frames
from ml.models.encoder import file_sha256, safe_torch_load
from ml.video_baseline import atomic_json, atomic_checkpoint, calibrate_video, metrics

VERSION = 'dinov2-temporal-readout-v1'
WEIGHTS_SHA256 = 'b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9'
SOURCE_COMMIT = '7764ea0f912e53c92e82eb78a2a1631e92725fc8'
SIZE = 392
VIEWS = ((0.,0.,1.,1.), (0.,.25,1.,.80))
GRID = [{'mode': mode, 'ridge': ridge} for mode in ('appearance','temporal') for ridge in (.001,.01,.1,1.,10.)]


def code_hash():
    return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()


def tensors(image, index):
    image = transformed_image(image, display_transform(index))
    w,h = image.size
    values = []
    for x1,y1,x2,y2 in VIEWS:
        crop = image.crop((round(x1*w),round(y1*h),round(x2*w),round(y2*h)))
        scale = min(SIZE/crop.width,SIZE/crop.height)
        crop = crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))),Image.Resampling.BICUBIC)
        canvas = Image.new('RGB',(SIZE,SIZE));canvas.paste(crop,((SIZE-crop.width)//2,(SIZE-crop.height)//2))
        x = torch.from_numpy(np.asarray(canvas,dtype=np.float32).copy()).permute(2,0,1)/255.
        values.append((x-torch.tensor((.485,.456,.406))[:,None,None])/torch.tensor((.229,.224,.225))[:,None,None])
    return torch.stack(values)


def encoder(source, weights, device='cuda'):
    if file_sha256(weights) != WEIGHTS_SHA256:
        raise ValueError('DINOv2 pretrained weights changed')
    model = torch.hub.load(str(source),'dinov2_vits14',source='local',pretrained=False)
    model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True),strict=True)
    return model.to(device).eval()


def encode(model, root, index, points, device='cuda'):
    if not 1 <= len(points) <= 180 or len(points) != len(set(points)):
        raise ValueError('DINOv2 source frame budget')
    selected=set(points);pending=[];result=[];actual=[]
    def flush():
        if not pending:return
        x=torch.cat(pending).to(device)
        with torch.inference_mode():
            output=model.forward_features(x)
            patch=output['x_norm_patchtokens'].transpose(1,2).reshape(len(x),384,SIZE//14,SIZE//14)
            pooled=F.adaptive_avg_pool2d(patch,(2,2)).flatten(1)
            features=torch.cat((output['x_norm_clstoken'],pooled),1).reshape(len(pending),-1)
        result.append(features.cpu());pending.clear()
    for timing,frame in iter_indexed_frames(Path(root),index):
        if timing['source_pts'] in selected:
            pending.append(tensors(frame.to_image(),index));actual.append(timing['source_pts'])
            if len(pending)==2:flush()
    flush()
    if actual!=points:raise ValueError('DINOv2 source PTS mismatch')
    return torch.cat(result)


def summary(x, mode):
    if x.ndim!=2 or not 1<=len(x)<=180 or not torch.isfinite(x).all():raise ValueError('DINOv2 feature shape')
    values=[x.mean(0),x.std(0,unbiased=False),x.amax(0)]
    if mode=='temporal':
        for k in range(4):
            start=min(len(x)-1,round(k*len(x)/4))
            end=min(len(x),max(start+1,round((k+1)*len(x)/4)))
            values.append(x[start:end].mean(0))
        values.extend(((x[1:]-x[:-1]).abs().mean(0) if len(x)>1 else torch.zeros_like(x[0]),x[-1]-x[0]))
    elif mode!='appearance':raise ValueError('Unknown DINOv2 readout')
    return torch.cat(values).double()


def fit(rows, candidate):
    x=torch.stack([summary(r['features'],candidate['mode']) for r in rows])
    y=torch.tensor([2*int(r['target'])-1 for r in rows],dtype=torch.float64)
    if len(y.unique())!=2:raise ValueError('Readout needs both training classes')
    mean=x.mean(0);scale=x.std(0,unbiased=False).clamp_min(.05)
    z=(x-mean)/scale
    weights=torch.stack([(y==v).sum().double().reciprocal()*len(y)/2 for v in y]).sqrt()
    a=z*weights[:,None]
    alpha=torch.linalg.solve(a@a.T/x.shape[1]+candidate['ridge']*torch.eye(len(x),dtype=torch.float64),y*weights)
    weight=a.T@alpha/x.shape[1]
    return {'mean':mean,'scale':scale,'weight':weight,'candidate':candidate,'train_ids':sorted(r['video_id'] for r in rows)}


def predict(state, rows):
    result=[]
    for row in rows:
        x=(summary(row['features'],state['candidate']['mode'])-state['mean'])/state['scale']
        score=float(torch.sigmoid(x@state['weight']))
        result.append({'video_id':row['video_id'],'truth':bool(row['target']),'score':score})
    return result


def validate_folds(data, folds, expected):
    covered=[]
    for fold in folds:
        train,test=set(fold['train']),set(fold['validation'])
        if train&test or train|test!=set(expected):raise ValueError('Invalid DINOv2 partition')
        if {data[v]['group_id'] for v in train}&{data[v]['group_id'] for v in test}:
            raise ValueError('DINOv2 family leakage')
        covered.extend(test)
        if 'inner' in fold:validate_folds(data,fold['inner'],train)
    if sorted(covered)!=sorted(expected):raise ValueError('DINOv2 validation coverage')


def prepare(root, output, source, weights):
    root,output=Path(root),Path(output)
    parent=json.loads((root/'temporal-operations-stage-v1c/protocol.json').read_text())
    sources=Path(json.loads((root/'prepared/readiness.json').read_text())['source_root'])
    output.mkdir(parents=True,exist_ok=False);(output/'inputs').mkdir()
    source=Path(source).resolve();files={str(p.relative_to(source)).replace('\\','/'):file_sha256(p) for p in source.rglob('*.py')}
    plan={'version':VERSION,'code_sha256':code_hash(),'source_commit':SOURCE_COMMIT,'source_files':files,
          'source_root':str(source),'weights':str(Path(weights).resolve()),'weights_sha256':WEIGHTS_SHA256,
          'size':SIZE,'views':VIEWS,'grid':GRID,'sample_policy':'every second existing 2fps frame; source PTS, at most180',
          'development_ids':parent['development_ids'],'reserved_ids':parent['reserved_ids'],
          'folds':parent['folds'],'final_inner':parent['final_inner'],'parent_protocol_sha256':parent['protocol_sha256'],
          'control':parent['control'],'encoder_frozen':True,'no_extra_source_videos':True,
          'selection':'inner min(accuracy,balanced_accuracy,macro_f1), then accuracy; threshold inner-only',
          'promotion':'all three outer metrics strictly better than fixed control; prototype only',
          'independent_test':False,'production_ready':False}
    plan['protocol_sha256']=stable_hash(plan);atomic_json(output/'protocol.json',plan)
    model=encoder(source,weights);entries=[]
    for video in parent['development_ids']:
        started=time.monotonic()
        old=root/'temporal-operations-stage-v1c/inputs'/(video+'.pt')
        if file_sha256(old)!=parent['inputs'][video]['sha256']:raise ValueError('Development input changed')
        old=safe_torch_load(old);index=json.loads((root/'prepared/indices'/(video+'.json')).read_text())
        if index['source_sha256']!=old['source_sha256']:raise ValueError('DINOv2 input identity')
        points=old['source_pts'][::2]
        features=encode(model,sources,index,points)
        payload={'video_id':video,'group_id':old['group_id'],'target':old['target'],'source_sha256':old['source_sha256'],
                 'source_pts':points,'features':features,'elapsed_seconds':time.monotonic()-started}
        path=output/'inputs'/(video+'.pt');atomic_checkpoint(path,payload)
        entries.append({'video_id':video,'sha256':file_sha256(path),'source_sha256':old['source_sha256']})
        print(json.dumps({'dino_cached':video,'frames':len(points),'elapsed_seconds':payload['elapsed_seconds']}),flush=True)
    atomic_json(output/'inputs.json',{'protocol_sha256':plan['protocol_sha256'],'entries':entries})


def select(data, folds):
    choices=[]
    for candidate in GRID:
        rows=[]
        for fold in folds:
            state=fit([data[v] for v in fold['train']],candidate)
            rows.extend(predict(state,[data[v] for v in fold['validation']]))
        threshold=calibrate_video(rows,partition='dev_validation');m=metrics(rows,threshold)
        choices.append({'candidate':candidate,'threshold':threshold,'metrics':m})
    return max(choices,key=lambda c:(min(c['metrics'][k] for k in ('accuracy','balanced_accuracy','macro_f1')),c['metrics']['accuracy']))


def run(output):
    output=Path(output);plan=json.loads((output/'protocol.json').read_text())
    if plan['code_sha256']!=code_hash() or plan['protocol_sha256']!=stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'}):
        raise ValueError('DINOv2 experiment changed')
    if (output/'report.json').exists():raise ValueError('DINOv2 experiment is complete')
    marker=json.loads((output/'inputs.json').read_text());data={}
    for entry in marker['entries']:
        path=output/'inputs'/(entry['video_id']+'.pt')
        data[entry['video_id']]=safe_torch_load(path,expected_sha256=entry['sha256'])
    if set(data)!=set(plan['development_ids']) or set(data)&set(plan['reserved_ids']):raise ValueError('DINOv2 development partition')
    validate_folds(data,plan['folds'],data)
    validate_folds(data,plan['final_inner'],data)
    rows=[];fold_reports=[]
    for n,fold in enumerate(plan['folds']):
        choice=select(data,fold['inner']);state=fit([data[v] for v in fold['train']],choice['candidate'])
        prediction=predict(state,[data[v] for v in fold['validation']])
        for row in prediction:row['threshold']=choice['threshold']
        rows.extend(prediction);fold_reports.append({'fold':n,'selected':choice,'predictions':prediction})
        print(json.dumps({'dino_fold':n,'metrics':metrics(prediction,choice['threshold']),'choice':choice['candidate']}),flush=True)
    # Per-fold inner-selected thresholds, not a threshold fitted on outer labels.
    adapted=[{**r,'score':r['score']-r['threshold']+.5} for r in rows]
    quality=metrics(adapted,.5)
    selected=select(data,plan['final_inner']);state=fit(list(data.values()),selected['candidate'])
    atomic_checkpoint(output/'final.pt',state)
    report={'protocol_sha256':plan['protocol_sha256'],'quality':quality,'control':plan['control'],'folds':fold_reports,
            'predictions':rows,'selected':selected,'final_sha256':file_sha256(output/'final.pt'),
            'promoted':all(quality[k]>plan['control'][k] for k in ('accuracy','balanced_accuracy','macro_f1')),
            'independent_test':False,'deterministic_no_seed_average':True,'production_ready':False}
    atomic_json(output/'report.json',report);print(json.dumps({'dino_quality':quality,'promoted':report['promoted']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--root',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a.add_argument('--source',type=Path,required=True);a.add_argument('--weights',type=Path,required=True)
    a=sub.add_parser('run');a.add_argument('--output',type=Path,required=True);a=p.parse_args()
    torch.set_num_threads(4)
    if a.command=='prepare':prepare(a.root,a.output,a.source,a.weights)
    else:run(a.output)
