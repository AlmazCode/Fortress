"""Fixed magnified object crops with the same local frozen CNN and source PTS."""
from __future__ import annotations
import argparse,hashlib
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from ml import boundary_inputs as parent
from ml.data.annotation_tasks import read_json
from ml.data.pts_index import iter_indexed_frames
from ml.data.extract_frames import display_transform,transformed_image
from ml.data.manifest import local_source
from ml.models.encoder import FrozenEncoder,file_sha256
from ml.preprocessing import preprocess_image
from ml.video_baseline import atomic_json

VERSION='magnified-object-boundary-inputs-v1'
REGIONS=((.50,.27,1.,.60),(0.,.30,.95,.67))

def code_hash():return parent.stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),'parent':parent.code_hash()})

def tensors(image,index):
    displayed=transformed_image(image,display_transform(index));w,h=displayed.size
    return torch.stack([preprocess_image(displayed.crop((round(a*w),round(b*h),round(c*w),round(d*h))))['tensor'] for a,b,c,d in REGIONS])

def descriptors(encoder,images,device):
    if images.ndim!=5 or images.shape[1:]!=(2,3,224,224) or len(images)>8:raise ValueError('bounded two-crop tensor batch required')
    rgb=(images*images.new_tensor((.229,.224,.225))[None,None,:,None,None]+images.new_tensor((.485,.456,.406))[None,None,:,None,None]).clamp(0,1)
    x=rgb.flatten(0,1);mean=F.avg_pool2d(x,28);std=(F.avg_pool2d(x.square(),28)-mean.square()).clamp_min(0).sqrt()
    with torch.inference_mode():cnn=encoder.features(images.to(device).flatten(0,1)).mean((2,3)).cpu()
    return torch.cat((cnn,torch.cat((mean,std),1).flatten(1)),1).reshape(len(images),2,960)

def bag_geometry(color):
    rgb=color[:,:588].reshape(-1,3,196);r,g,b=rgb.unbind(1);weight=(torch.minimum(g-r,g-b)-.01).clamp_min(0)
    grid=(torch.arange(14,dtype=weight.dtype)+.5)/14;yy,xx=torch.meshgrid(grid,grid,indexing='ij');x=xx.flatten();y=yy.flatten()
    normalized=weight/weight.sum(1,keepdim=True).clamp_min(1e-6);cx=normalized@x;cy=normalized@y
    vx=(normalized*(x-cx[:,None]).square()).sum(1);vy=(normalized*(y-cy[:,None]).square()).sum(1)
    xy=(normalized*(x-cx[:,None])*(y-cy[:,None])).sum(1)
    active=weight>.015;area=active.float().mean(1);top=weight.topk(3,1).values.mean(1)
    below=(normalized*(y>.55)).sum(1);right=(normalized*(x>.5)).sum(1);ratio=(vx/(vy+.0001)).clamp_max(10)
    geometry=torch.stack((cx,cy,vx,vy,xy,area,top,below,right,ratio),1)*(weight.sum(1)>0)[:,None]
    return torch.cat((parent.object_state_local.color_signature(color),geometry),1)

def build(boundary_directory,position_directory,prepared,weights,weights_sha256,output,device='cuda'):
    torch.set_num_threads(4);marker,rows=parent.load(boundary_directory);position=read_json(Path(position_directory)/'inputs.json')
    root=Path(read_json(Path(prepared)/'readiness.json')['source_root']);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    encoder=FrozenEncoder(weights_path=weights,weights_sha256=weights_sha256).to(device);entries=[]
    for video,row in rows.items():
        index=read_json(Path(prepared)/'indices'/(video+'.json'));wanted=set(row['source_pts']);pending=[];pending_pts=[];points=[];values=[]
        def flush():
            if pending:values.append(descriptors(encoder,torch.stack(pending),device));points.extend(pending_pts);pending.clear();pending_pts.clear()
        for timing,frame in iter_indexed_frames(root,index):
            if timing['source_pts'] in wanted:
                pending.append(tensors(frame.to_image(),index));pending_pts.append(timing['source_pts'])
                if len(pending)==8:flush()
        flush()
        if points!=row['source_pts'] or index['source_sha256']!=row['source_sha256']:raise ValueError('crop source PTS/SHA changed')
        p=next(e for e in position['entries'] if e['video_id']==video);path=local_source(Path(position_directory),p['path'])
        if p['source_pts']!=points or p['source_sha256']!=row['source_sha256'] or file_sha256(path)!=p['sha256']:raise ValueError('color source binding')
        color=torch.from_numpy(np.array(np.load(path,allow_pickle=False)[:,parent.parent.CNN_DIM:],copy=True));bag=bag_geometry(color)
        file=out/(video+'.npz');np.savez(file,crops=torch.cat(values).numpy().astype(np.float32),bag=bag.numpy().astype(np.float32))
        entries.append({k:row[k] for k in ('video_id','source_sha256','group_id','split','target','source_pts','targets','events')}|
                       {'path':file.name,'sha256':file_sha256(file)})
        print(video,len(points),flush=True)
    atomic_json(out/'inputs.json',{'version':VERSION,'code_sha256':code_hash(),'parent_inputs_sha256':file_sha256(Path(boundary_directory)/'inputs.json'),
                'parent_protocol_sha256':marker['parent_protocol_sha256'],'review':marker['review'],'review_sha256':marker['review_sha256'],
                'encoder_sha256':weights_sha256,'regions':[list(r) for r in REGIONS],'rate':2.,'entries':entries,'production_ready':False,'human_approved':False})

def load(directory):
    root=Path(directory);marker=read_json(root/'inputs.json')
    if marker['version']!=VERSION or marker['code_sha256']!=code_hash() or marker['regions']!=[list(r) for r in REGIONS] or file_sha256(marker['review'])!=marker['review_sha256']:raise ValueError('object crop input binding')
    rows={}
    for e in marker['entries']:
        path=local_source(root,e['path'])
        if e['video_id'] in rows or file_sha256(path)!=e['sha256']:raise ValueError('crop input bytes')
        with np.load(path,allow_pickle=False) as a:
            crops=torch.from_numpy(a['crops'].copy());bag=torch.from_numpy(a['bag'].copy())
        n=len(e['source_pts']);targets=torch.tensor(e['targets'],dtype=torch.float32)
        if crops.shape!=(n,2,960) or bag.shape!=(n,29) or targets.shape!=(n,6) or not torch.isfinite(crops).all() or not torch.isfinite(bag).all():raise ValueError('crop input shape')
        rows[e['video_id']]={**e,'crops':crops,'bag':bag,'boundary_targets':targets}
    return marker,rows

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('boundary','position','prepared','weights','weights-sha256','output'):p.add_argument('--'+name,required=True,type=str if name=='weights-sha256' else Path)
    a=p.parse_args();build(a.boundary,a.position,a.prepared,a.weights,a.weights_sha256,a.output)
