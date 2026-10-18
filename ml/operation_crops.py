"""Fixed-camera detail views; no boxes or operation labels are inference inputs."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import numpy as np
from PIL import Image
import torch

from ml import temporal_actions as source
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import transformed_image,display_transform
from ml.data.pts_index import iter_indexed_frames
from ml.models.encoder import FrozenEncoder,file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint

VERSION='camera-operation-detail-inputs-v1'
# Camera layout chosen before the detail experiment, from the source view.
# These are generic image regions, not violation boundaries or known-video keys.
ROIS=((0.,.45,.70,.65),(.20,.43,.60,.57),(.57,.40,.94,.70),(0.,.44,.32,.65))


def code_hash():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()


def tensors(image,index):
    displayed=transformed_image(image,display_transform(index))
    width,height=displayed.size;result=[]
    for roi in ROIS:
        cropped=displayed.crop((round(roi[0]*width),round(roi[1]*height),round(roi[2]*width),round(roi[3]*height)))
        w,h=cropped.size;scale=min(448/w,448/h);size=(max(1,round(w*scale)),max(1,round(h*scale)))
        cropped=cropped.resize(size,Image.Resampling.BILINEAR)
        canvas=Image.new('RGB',(448,448));canvas.paste(cropped,((448-size[0])//2,(448-size[1])//2))
        value=torch.from_numpy(np.asarray(canvas,dtype=np.float32).copy()).permute(2,0,1)/255.
        value=(value-torch.tensor((.485,.456,.406))[:,None,None])/torch.tensor((.229,.224,.225))[:,None,None]
        result.append(value)
    return torch.stack(result)


def build(parent,destination,device='cuda'):
    parent,destination=Path(parent),Path(destination);plan=read_json(parent/'protocol.json')
    if plan['code_sha256']!=source.code_hash():raise ValueError('Operation supervision code changed')
    root=Path(plan['root']);prepared=root/'prepared';sources=Path(read_json(prepared/'readiness.json')['source_root'])
    encoder=FrozenEncoder(weights_path=Path(plan['encoder_weights']),weights_sha256=plan['encoder_sha256']).to(device).eval()
    destination.mkdir(parents=True,exist_ok=False);(destination/'inputs').mkdir();counts={}
    for video in plan['development_ids']:
        old_path=parent/'inputs'/(video+'.pt')
        if file_sha256(old_path)!=plan['inputs'][video]['sha256']:raise ValueError('Operation labels/source changed')
        old=safe_torch_load(old_path);index=read_json(prepared/'indices'/(video+'.json'))
        if old['source_sha256']!=index['source_sha256']:raise ValueError('Detail view source identity')
        expected=old['source_pts'];selected=set(expected);points=[];pending=[];values=[]
        def flush():
            if not pending:return
            images=torch.cat(pending).to(device)
            maps=encoder.features(images).cpu().to(torch.float16).to(torch.float32)
            values.append(maps.mean((-2,-1)).reshape(len(pending),4*576));pending.clear()
        with torch.inference_mode():
            for timing,frame in iter_indexed_frames(sources,index):
                if timing['source_pts'] in selected:
                    pending.append(tensors(frame.to_image(),index));points.append(timing['source_pts'])
                    if len(pending)==4:flush()
            flush()
        if points!=expected:raise ValueError('Detail frame PTS mismatch')
        features=torch.cat((old['features'][0,:,:576],torch.cat(values)),1)
        payload={**old,'features':features[None].repeat(3,1,1)}
        path=destination/'inputs'/(video+'.pt');atomic_checkpoint(path,payload)
        counts[video]={**plan['inputs'][video],'sha256':file_sha256(path)}
        print(__import__('json').dumps({'detail_cached':video,'frames':len(points)}),flush=True)
    updated={k:v for k,v in plan.items() if k!='protocol_sha256'}
    updated.update(inputs=counts,feature_source={'version':VERSION,'code_sha256':code_hash(),'rois':ROIS,
                     'parent_protocol_sha256':plan['protocol_sha256'],'augmentation':'same source samples; detail views without brightness variants',
                     'pretrained_encoder_unchanged':True,'new_camera_validated':False})
    updated['protocol_sha256']=stable_hash(updated);atomic_json(destination/'protocol.json',updated)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();torch.set_num_threads(4);torch.use_deterministic_algorithms(True);build(a.parent,a.output)


if __name__=='__main__':main()
