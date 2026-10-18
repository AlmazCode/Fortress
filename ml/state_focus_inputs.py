"""Local positional CNN/color features, preserving original source timestamps."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from ml import object_event_inputs as parent
from ml.data.annotation_tasks import read_json
from ml.data.manifest import local_source
from ml.data.pts_index import iter_indexed_frames
from ml.models.encoder import file_sha256
from ml.video_baseline import atomic_json

VERSION='position-color-inputs-v1'
CNN_DIM=576*4*4
COLOR_DIM=7*14*14
DIM=CNN_DIM+COLOR_DIM
TAXONOMY=parent.TAXONOMY+('green_bag_visible','screen_bright_content')

def code_hash():
    return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()

def color_features(normalized):
    if normalized.ndim!=4 or normalized.shape[1:]!=(3,448,448):raise ValueError('448px input required')
    mean=normalized.new_tensor((.485,.456,.406))[None,:,None,None]
    std=normalized.new_tensor((.229,.224,.225))[None,:,None,None]
    rgb=(normalized*std+mean).clamp(0,1)
    avg=F.avg_pool2d(rgb,32);spread=(F.avg_pool2d(rgb.square(),32)-avg.square()).clamp_min(0).sqrt()
    gray=(rgb*rgb.new_tensor((.299,.587,.114))[None,:,None,None]).sum(1,keepdim=True)
    edge=F.pad((gray[:,:,:,1:]-gray[:,:,:,:-1]).abs(),(0,1))+F.pad((gray[:,:,1:]-gray[:,:,:-1]).abs(),(0,0,0,1))
    return torch.cat((avg,spread,F.avg_pool2d(edge,32)),1).flatten(1)

def combine(maps,color):
    if maps.ndim!=4 or maps.shape[1:]!=(576,14,14) or color.shape!=(len(maps),COLOR_DIM):raise ValueError('positional feature shape')
    return torch.cat((F.adaptive_avg_pool2d(maps,(4,4)).flatten(1),color),1)

def build(parent_experiment,output):
    torch.set_num_threads(4)
    plan=read_json(Path(parent_experiment)/'protocol.json')
    document,rows,binding,marker=parent.load(*[plan[k] for k in ('cache','overlay','compat','review','spatial')])
    if binding!=plan['binding']:raise ValueError('parent inputs changed')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    prepared=Path(document['prepared_dir']);source=Path(read_json(prepared/'readiness.json')['source_root']);entries=[]
    for row in rows:
        if row['video_id'] not in plan['development_ids']:continue
        index=read_json(prepared/'indices'/(row['video_id']+'.json'));selected=set(row['source_pts'].tolist())
        colors=[];points=[]
        for timing,frame in iter_indexed_frames(source,index):
            if timing['source_pts'] in selected:
                value=parent.tensor(frame.to_image(),index,1.)
                colors.append(color_features(value[None])[0]);points.append(timing['source_pts'])
        if points!=row['source_pts'].tolist():raise ValueError('color source PTS mismatch')
        color=torch.stack(colors);values=[]
        for start in range(0,len(points),16):
            maps=torch.from_numpy(np.array(row['maps'][0][start:start+16],dtype=np.float32))
            values.append(combine(maps,color[start:start+16]))
        path=out/(row['video_id']+'.npy');np.save(path,torch.cat(values).numpy())
        entries.append({k:row[k] for k in ('video_id','group_id','split','source_sha256','target')}|
                       {'source_pts':points,'path':path.name,'sha256':file_sha256(path)})
        print(json.dumps({'cached':row['video_id'],'frames':len(points)}),flush=True)
    atomic_json(out/'inputs.json',{'version':VERSION,'code_sha256':code_hash(),'parent_protocol_sha256':plan['protocol_sha256'],
                                'parent_binding':binding,'dimension':DIM,'cnn_dimension':CNN_DIM,'color_dimension':COLOR_DIM,
                                'entries':entries,'production_ready':False})

def load(parent_plan,directory,review):
    document,rows,binding,_=parent.load(*[parent_plan[k] for k in ('cache','overlay','compat','review','spatial')])
    marker=read_json(Path(directory)/'inputs.json');extra=read_json(review);root=Path(review).resolve().parent
    if marker['version']!=VERSION or marker['code_sha256']!=code_hash() or marker['parent_binding']!=binding or marker['parent_protocol_sha256']!=parent_plan['protocol_sha256'] or marker['dimension']!=DIM:raise ValueError('positional inputs changed')
    if extra['version']!='state-focus-review-v1' or extra['human_approved'] is not False or extra['original_verdicts_changed'] is not False or extra['parent_overlay_sha256']!=file_sha256(parent_plan['overlay']):raise ValueError('state review lineage')
    lookup={r['video_id']:r for r in rows};seen=set()
    for r in rows:
        r['actions']=torch.cat((r['actions'],torch.full((len(r['actions']),2),-1.)),1)
    for entry in extra['entries']:
        e=entry['evidence'];key=(e['video_id'],e['source_pts'])
        if key in seen or e['video_id'] not in parent_plan['development_ids']:raise ValueError('duplicate/reserved review')
        seen.add(key);r=lookup[e['video_id']];path=Path(e['path']).resolve(strict=True)
        if e['source_sha256']!=r['source_sha256'] or not path.is_relative_to(root) or file_sha256(path)!=e['image_sha256']:raise ValueError('state evidence changed')
        if len(entry['extra_states'])!=2 or any(type(v)is not int or v not in (-1,0,1) for v in entry['extra_states']):raise ValueError('state values')
        matches=np.where(r['source_pts']==e['source_pts'])[0]
        if len(matches)>1:raise ValueError('duplicate source PTS')
        if len(matches):
            n=int(matches[0]);r['actions'][n,18:]=torch.tensor(entry['extra_states'])
            for name,value in entry.get('corrections',{}).items():
                if name!='laptop_screen_lit' or type(value)is not int or value not in (-1,0,1):raise ValueError('unsupported state correction')
                r['actions'][n,12]=value
    dev=set(parent_plan['development_ids'])
    if {e['video_id'] for e in marker['entries']}!=dev or len(marker['entries'])!=len(dev):raise ValueError('positional source coverage')
    for e in marker['entries']:
        r=lookup[e['video_id']];path=local_source(Path(directory),e['path'])
        if any(e[k]!=r[k] for k in ('group_id','split','source_sha256','target')) or e['source_pts']!=r['source_pts'].tolist() or file_sha256(path)!=e['sha256']:raise ValueError('positional source mismatch')
        values=np.load(path,mmap_mode='r',allow_pickle=False)
        if values.shape!=(len(r['actions']),DIM) or values.dtype!=np.float32 or not np.isfinite(values).all():raise ValueError('positional array')
        r['position_features']=values
    return document,[lookup[v] for v in parent_plan['development_ids']],marker,extra

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.parent,a.output)
