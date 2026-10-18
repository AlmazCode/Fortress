"""Source-PTS-bound boundary labels and fixed region features for local research."""
from __future__ import annotations
import argparse,hashlib
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from ml import state_focus_inputs as parent,object_state_local
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.manifest import local_source
from ml.models.encoder import file_sha256
from ml.video_baseline import atomic_json

VERSION='object-boundary-inputs-v1'
TAXONOMY=('safe_open','green_bag_visible','bag_held_or_manipulated','bag_on_worktop','operator_at_station','person_at_counter')
BLOCKS=(2304,576,576,28,19)
DIM=sum(BLOCKS)

def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'parent':parent.code_hash(),'color':object_state_local.code_hash()})

def features(maps,color):
    """Fixed canvas regions; no object annotations or source ID at inference."""
    if maps.ndim!=4 or maps.shape[1:]!=(576,14,14) or color.shape!=(len(maps),1372) or not torch.isfinite(maps).all() or not torch.isfinite(color).all():
        raise ValueError('finite source-aligned CNN/color features required')
    return torch.cat((F.adaptive_avg_pool2d(maps,2).flatten(1),maps[:,:,1:9,6:14].mean((2,3)),
                      maps[:,:,6:14,:13].mean((2,3)),F.adaptive_avg_pool2d(color.reshape(-1,7,14,14),2).flatten(1),
                      object_state_local.color_signature(color)),1)

def exact_review(review,rows,parent_plan):
    if (review.get('version')!='object-boundary-review-v1' or review.get('taxonomy')!=list(TAXONOMY)
        or review.get('human_approved') is not False or review.get('original_verdicts_changed') is not False
        or review.get('original_source_bytes_changed') is not False):raise ValueError('boundary review provenance')
    dev=set(parent_plan['development_ids']);lookup={r['video_id']:r for r in rows}
    if len(review['videos'])!=len(dev) or {v['video_id'] for v in review['videos']}!=dev:raise ValueError('review must cover development exactly')
    for video in review['videos']:
        r=lookup[video['video_id']]
        if video['source_sha256']!=r['source_sha256']:raise ValueError('review source changed')
        evidence={e['source_pts']:e for e in video['evidence']}
        if len(evidence)!=len(video['evidence']):raise ValueError('duplicate boundary evidence')
        points=r['source_pts'].tolist();position={int(p):n for n,p in enumerate(points)}
        target=torch.full((len(points),len(TAXONOMY)),-1.);seen=set()
        for observation in video['observations']:
            point=observation['source_pts'];values=observation['values']
            if (type(point)is not int or point in seen or point not in position or len(values)!=len(TAXONOMY)
                or any(type(v)is not int or v not in (-1,0,1) for v in values)):raise ValueError('invalid boundary target')
            seen.add(point);e=evidence.get(point)
            if (e is None or e['source_sha256']!=r['source_sha256'] or e['video_id']!=video['video_id']
                or e['image_sha256']!=observation['image_sha256'] or abs(e['timestamp_sec']-observation['timestamp_sec'])>1e-7):raise ValueError('target is not exact evidence')
            target[position[point]]=torch.tensor(values,dtype=torch.float32)
        if seen!=set(points):raise ValueError('incomplete exact review coverage')
        for event in video['transitions']:
            a,b=evidence.get(event['before_pts']),evidence.get(event['after_pts'])
            if (event['type'] not in ('safe_opening','safe_closing','bag_placement','bag_pickup','operator_departure','counter_departure')
                or a is None or b is None or event['earliest_sec']!=a['timestamp_sec'] or event['latest_sec']!=b['timestamp_sec']
                or not 0<event['latest_sec']-event['earliest_sec']<=.501):raise ValueError('invalid observed boundary bracket')
        r['boundary_targets']=target;r['boundary_events']=video['transitions']
    return lookup

def build(parent_directory,position_directory,old_review,review,output):
    plan=read_json(Path(parent_directory)/'protocol.json');_,rows,_,_=parent.load(plan,position_directory,old_review)
    extra=read_json(review);lookup=exact_review(extra,rows,plan);root=Path(review).resolve().parent
    for video in extra['videos']:
        for evidence in video['evidence']:
            path=Path(evidence['path']).resolve(strict=True)
            if not path.is_relative_to(root) or file_sha256(path)!=evidence['image_sha256']:raise ValueError('boundary evidence changed')
    out=Path(output);out.mkdir(parents=True,exist_ok=False);entries=[]
    for video in plan['development_ids']:
        r=lookup[video];x=features(torch.from_numpy(np.array(r['maps'][0],dtype=np.float32)),
                                  torch.from_numpy(np.array(r['position_features'][:,parent.CNN_DIM:],copy=True)))
        path=out/(video+'.npy');np.save(path,x.numpy().astype(np.float32),allow_pickle=False)
        entries.append({k:r[k] for k in ('video_id','source_sha256','group_id','split','target')}|
                       {'path':path.name,'sha256':file_sha256(path),'source_pts':r['source_pts'].tolist(),
                        'targets':r['boundary_targets'].tolist(),'events':r['boundary_events']})
    marker={'version':VERSION,'code_sha256':code_hash(),'parent_protocol_sha256':plan['protocol_sha256'],
            'review_sha256':file_sha256(review),'review':str(Path(review).resolve()),'position_inputs_sha256':file_sha256(Path(position_directory)/'inputs.json'),
            'dimension':DIM,'blocks':list(BLOCKS),'rate':2.,'entries':entries,'production_ready':False,'human_approved':False}
    atomic_json(out/'inputs.json',marker);print({'sources':len(entries),'dimension':DIM,'sha256':file_sha256(out/'inputs.json')},flush=True)

def load(directory):
    root=Path(directory);marker=read_json(root/'inputs.json')
    if marker['version']!=VERSION or marker['code_sha256']!=code_hash() or marker['dimension']!=DIM or marker['blocks']!=list(BLOCKS):raise ValueError('boundary input version changed')
    if file_sha256(marker['review'])!=marker['review_sha256']:raise ValueError('boundary review changed')
    rows={}
    for e in marker['entries']:
        path=local_source(root,e['path'])
        if e['video_id'] in rows or file_sha256(path)!=e['sha256']:raise ValueError('duplicate/changed boundary inputs')
        x=np.load(path,allow_pickle=False);y=torch.tensor(e['targets'],dtype=torch.float32)
        points=e['source_pts']
        if (not 1<=len(points)<=360 or any(type(p)is not int for p in points) or any(a>=b for a,b in zip(points,points[1:]))
            or e['target'] not in (0,1) or x.dtype!=np.float32 or x.shape!=(len(points),DIM) or y.shape!=(len(x),len(TAXONOMY))
            or not np.isfinite(x).all() or not torch.isin(y,torch.tensor([-1.,0.,1.])).all()):raise ValueError('boundary input shapes/values')
        rows[e['video_id']]={**e,'features':torch.from_numpy(x),'boundary_targets':y}
    return marker,rows

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('parent','position','old-review','review','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.parent,a.position,a.old_review,a.review,a.output)
