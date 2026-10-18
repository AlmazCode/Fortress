"""Versioned local spatial maps and source-bound object/event observations."""
from __future__ import annotations
import argparse,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageEnhance
import torch
import torchvision
from ml import action_focus_inputs as base
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import transformed_image,display_transform
from ml.data.manifest import local_source
from ml.data.pts_index import iter_indexed_frames
from ml.models.encoder import FrozenEncoder,file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,load_feature_cache

VERSION='spatial-object-inputs-v2'
TAXONOMY=base.TAXONOMY+('cup_visible','cup_to_mouth','garment_on_desk')
OBJECTS=('cardlike_10','laptop_11','banknote_1','desk_device_4','safe_7','journal_12','small_box_13','green_bag','cup','garment')
IDS=(10,11,1,4,7,12,13)
SIZE=448
VARIANTS=(1.,.85,1.15)

def code_hash():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()

def cup_classifier(weights,weights_sha256):
    """Data-free512-neuron publisher-head compression; no dataset labels used."""
    model=torchvision.models.mobilenet_v3_small(weights=None)
    model.load_state_dict(safe_torch_load(weights,expected_sha256=weights_sha256,max_bytes=16*1024**2),strict=True)
    a,b=model.classifier[0],model.classifier[3]
    salience=a.weight.detach().norm(dim=1)*b.weight.detach().norm(dim=0)
    selected=salience.argsort(descending=True,stable=True)[:512].sort().values
    classifier=torch.nn.Sequential(torch.nn.Linear(576,512),torch.nn.Hardswish(),torch.nn.Linear(512,1000))
    with torch.no_grad():
        classifier[0].weight.copy_(a.weight[selected]);classifier[0].bias.copy_(a.bias[selected])
        classifier[2].weight.copy_(b.weight[:,selected]);classifier[2].bias.copy_(b.bias)
    return classifier.eval().requires_grad_(False)

def tensor(image,index,brightness):
    im=transformed_image(image,display_transform(index));x0,y0,x1,y1=base.ROI
    im=im.crop((round(x0*im.width),round(y0*im.height),round(x1*im.width),round(y1*im.height)))
    im=ImageEnhance.Brightness(im).enhance(brightness)
    scale=min(SIZE/im.width,SIZE/im.height);w,h=round(im.width*scale),round(im.height*scale)
    canvas=Image.new('RGB',(SIZE,SIZE));canvas.paste(im.resize((w,h),Image.Resampling.BILINEAR),((SIZE-w)//2,(SIZE-h)//2))
    value=torch.from_numpy(np.asarray(canvas,dtype=np.float32).transpose(2,0,1).copy())/255
    return (value-torch.tensor((.485,.456,.406))[:,None,None])/torch.tensor((.229,.224,.225))[:,None,None]

def box_to_roi(box,width,height):
    x,y,w,h=box;left,top,right,bottom=(round(base.ROI[0]*width),round(base.ROI[1]*height),round(base.ROI[2]*width),round(base.ROI[3]*height))
    x0,y0,x1,y1=max(x,left),max(y,top),min(x+w,right),min(y+h,bottom)
    if x1<=x0 or y1<=y0:return None
    scale=min(SIZE/(right-left),SIZE/(bottom-top));rw,rh=round((right-left)*scale),round((bottom-top)*scale)
    px,py=(SIZE-rw)//2,(SIZE-rh)//2
    return [(px+(x0-left)*rw/(right-left))/SIZE,(py+(y0-top)*rh/(bottom-top))/SIZE,
            (px+(x1-left)*rw/(right-left))/SIZE,(py+(y1-top)*rh/(bottom-top))/SIZE]

def build(cache,output,weights,weights_sha256,device='cuda'):
    torch.set_num_threads(4);document,rows=load_feature_cache(cache);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    if weights_sha256!=document['encoder']['weights_sha256']:raise ValueError('encoder mismatch')
    encoder=FrozenEncoder(weights_path=weights,weights_sha256=weights_sha256).to(device).eval()
    classifier=cup_classifier(weights,weights_sha256).to(device);names=torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1.meta['categories']
    cup_indices=[names.index(n) for n in ('coffee mug','cup')]
    prepared=Path(document['prepared_dir']);source=Path(read_json(prepared/'readiness.json')['source_root']);entries=[]
    for row in rows:
        if row['split']=='independent_test':continue
        index=read_json(prepared/'indices'/(row['video_id']+'.json'))
        with np.load(local_source(Path(cache),row['path']),allow_pickle=False) as z:pts=z['source_pts'].copy()
        select=set(pts.tolist());maps=[[],[],[]];prior=[];points=[];pending=[];pending_pts=[]
        def flush():
            if not pending:return
            images=torch.stack(pending).to(device);n=len(images)
            values=encoder.features(images.flatten(0,1)).reshape(n,3,576,14,14)
            for v in range(3):maps[v].extend(values[:,v].cpu().numpy().astype(np.float16))
            pooled=torch.nn.functional.avg_pool2d(values[:,0],3,stride=1,padding=1).permute(0,2,3,1)
            p=classifier(pooled).softmax(-1)[...,cup_indices].sum(-1)
            prior.extend(p.cpu().numpy());points.extend(pending_pts);pending.clear();pending_pts.clear()
        with torch.inference_mode():
            for timing,frame in iter_indexed_frames(source,index):
                if timing['source_pts'] in select:
                    pending.append(torch.stack([tensor(frame.to_image(),index,b) for b in VARIANTS]));pending_pts.append(timing['source_pts'])
                    if len(pending)==8:flush()
            flush()
        if points!=pts.tolist():raise ValueError('spatial source PTS mismatch')
        files=[]
        for v,values in enumerate(maps):
            path=out/f'{row["video_id"]}.{v}.npy';np.save(path,np.asarray(values,dtype=np.float16));files.append({'path':path.name,'sha256':file_sha256(path)})
        path=out/f'{row["video_id"]}.prior.npy';np.save(path,np.asarray(prior,dtype=np.float32));files.append({'path':path.name,'sha256':file_sha256(path)})
        entries.append({k:row[k] for k in ('video_id','split','group_id','source_sha256','target')}|{'files':files,'source_pts':points})
        print(f'spatial {row["video_id"]}: {len(points)} frames',flush=True)
    marker={'version':VERSION,'code_sha256':code_hash(),'base_sha256':stable_hash(document),'size':SIZE,'roi':list(base.ROI),
            'variants':list(VARIANTS),'map_dtype':'float16 cache; float32 heads','rate':2.,'entries':entries,
            'encoder_weights':str(Path(weights).resolve()),'encoder_sha256':weights_sha256,'cup_prior_classes':['coffee mug','cup'],
            'prior_is_pretrained_unvalidated':True,'prior_head':'publisher512salience-v1','production_ready':False}
    atomic_json(out/'inputs.json',marker)

def load(cache,overlay,compat,review,spatial):
    torch.set_num_threads(4)
    doc,rows,binding,_,old_review=base.load_review(cache,overlay,compat)
    extra=read_json(review);root=Path(review).resolve().parent
    if (extra['version']!='object-event-review-v1' or extra['human_approved'] is not False or extra['original_verdicts_changed'] is not False
            or extra['base_overlay_sha256']!=file_sha256(overlay) or extra['extra_taxonomy']!=list(TAXONOMY[15:])):raise ValueError('object review provenance changed')
    lookup={r['video_id']:r for r in rows};observations={}
    for entry in extra['entries']:
        e=entry['evidence'];key=(e['video_id'],e['source_pts']);row=lookup[e['video_id']]
        if key in observations or row['split']=='independent_test' or e['source_sha256']!=row['source_sha256']:raise ValueError('reserved/duplicate object review')
        path=Path(e['path']).resolve(strict=True)
        if not path.is_relative_to(root) or file_sha256(path)!=e['image_sha256']:raise ValueError('evidence mismatch')
        if len(entry['extra_states'])!=3 or any(type(v)is not int or v not in (-1,0,1) for v in entry['extra_states']):raise ValueError('invalid extra target')
        for box in entry['boxes']:
            x,y,w,h=box['bbox']
            if box['category'] not in OBJECTS[7:] or not np.isfinite([x,y,w,h]).all() or min(x,y)<0 or min(w,h)<=0 or x+w>e['width'] or y+h>e['height']:raise ValueError('invalid assistant box')
        observations[key]=entry
    prepared=Path(doc['prepared_dir']);package=Path(read_json(prepared/'readiness.json')['source_root'])
    coco=read_json(package/'annotations/objects.coco.json');provided={};images={(i['video_id'],i['source_pts']):i for i in coco['images']}
    for b in coco['annotations']:provided.setdefault(b['image_id'],[]).append(b)
    marker=read_json(Path(spatial)/'inputs.json')
    dev={r['video_id'] for r in rows if r['split'] in ('train','dev_validation')}
    if (marker['version']!=VERSION or marker['code_sha256']!=code_hash() or marker['base_sha256']!=stable_hash(doc)
            or marker['size']!=SIZE or marker['roi']!=list(base.ROI) or marker['variants']!=list(VARIANTS)
            or {e['video_id'] for e in marker['entries']}!=dev or len(marker['entries'])!=len(dev)):raise ValueError('spatial binding mismatch')
    for row in rows:
        if row['video_id'] not in dev:continue
        row['actions']=torch.cat([row['actions'],torch.full((len(row['actions']),3),-1.)],1)
        row['boxes']=[];row['object_known']=torch.zeros(len(row['actions']),len(OBJECTS),dtype=torch.bool)
        index=read_json(prepared/'indices'/(row['video_id']+'.json'));timing={f['source_pts']:f['timestamp_sec'] for f in index['frames']}
        for n,p in enumerate(row['source_pts']):
            key=(row['video_id'],int(p));boxes=[]
            if key in images:
                img=images[key];row['object_known'][n,:7]=True
                for b in provided.get(img['id'],[]):
                    if b['category_id'] in IDS:
                        box=box_to_roi(b['bbox'],img['width'],img['height'])
                        if box:boxes.append([IDS.index(b['category_id']),*box])
            if key in observations:
                e=observations[key];ev=e['evidence']
                if abs(timing[int(p)]-ev['timestamp_sec'])>1e-7:raise ValueError('extra PTS/time mismatch')
                row['actions'][n,15:]=torch.tensor(e['extra_states'])
                for name in e['reviewed_visible_classes']:row['object_known'][n,OBJECTS.index(name)]=True
                for b in e['boxes']:
                    box=box_to_roi(b['bbox'],ev['width'],ev['height'])
                    if box:boxes.append([OBJECTS.index(b['category']),*box])
            row['boxes'].append(boxes)
        entry=next(e for e in marker['entries'] if e['video_id']==row['video_id'])
        if entry['source_pts']!=row['source_pts'].tolist() or any(entry[k]!=row[k] for k in ('split','group_id','source_sha256','target')):raise ValueError('spatial source lineage changed')
        arrays=[]
        for v,f in enumerate(entry['files']):
            path=local_source(Path(spatial),f['path'])
            if file_sha256(path)!=f['sha256']:raise ValueError('spatial bytes changed')
            a=np.load(path,mmap_mode='r',allow_pickle=False)
            shape=(len(row['actions']),576,14,14) if v<3 else (len(row['actions']),14,14)
            if a.shape!=shape or a.dtype!=(np.float16 if v<3 else np.float32) or not np.isfinite(a).all():raise ValueError('invalid spatial array')
            arrays.append(a)
        row['maps']=arrays[:3];row['cup_prior']=arrays[3]
    binding.update(object_review_sha256=file_sha256(review),spatial_sha256=stable_hash(marker))
    return doc,rows,binding,marker

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('cache','output','weights'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--weights-sha256',required=True);a=p.parse_args();build(a.cache,a.output,a.weights,a.weights_sha256)
