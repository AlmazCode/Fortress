"""Serialization repair for the frozen DINOv2 probe, reusing immutable inputs.

v1 completed its outer evaluation but its float64 readout could not pass the
existing strict FP32 torch checkpoint writer. Preserve v1, save FP64 coefficients
as ordinary finite JSON in a new protocol; no old loader or protocol is relaxed.
"""
import argparse
import json
from pathlib import Path

import torch
from ml import dino_probe as base
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,metrics


def run(parent, output):
    parent,output=Path(parent),Path(output)
    old=json.loads((parent/'protocol.json').read_text())
    if old['code_sha256']!=base.code_hash() or old['protocol_sha256']!=stable_hash({k:v for k,v in old.items() if k!='protocol_sha256'}):
        raise ValueError('DINOv2 parent changed')
    output.mkdir(parents=True,exist_ok=False)
    plan={'version':'dinov2-temporal-json-readout-v1','parent_protocol_sha256':old['protocol_sha256'],
          'parent':str(parent.resolve()),'code_sha256':file_sha256(Path(__file__)),
          'inputs_sha256':file_sha256(parent/'inputs.json'),'readout_serialization':'finite JSON, float64 values',
          'reserved_used':False,'independent_test':False}
    plan['protocol_sha256']=stable_hash(plan);atomic_json(output/'protocol.json',plan)
    marker=json.loads((parent/'inputs.json').read_text());data={}
    for entry in marker['entries']:
        data[entry['video_id']]=safe_torch_load(parent/'inputs'/(entry['video_id']+'.pt'),expected_sha256=entry['sha256'])
    if set(data)!=set(old['development_ids']) or set(data)&set(old['reserved_ids']):raise ValueError('DINOv2 repair partition')
    base.validate_folds(data,old['folds'],data);base.validate_folds(data,old['final_inner'],data)
    rows=[];fold_reports=[]
    for n,fold in enumerate(old['folds']):
        choice=base.select(data,fold['inner']);state=base.fit([data[v] for v in fold['train']],choice['candidate'])
        predictions=base.predict(state,[data[v] for v in fold['validation']])
        for row in predictions:row['threshold']=choice['threshold']
        rows.extend(predictions);fold_reports.append({'fold':n,'selected':choice,'predictions':predictions})
    quality=metrics([{**r,'score':r['score']-r['threshold']+.5} for r in rows],.5)
    selected=base.select(data,old['final_inner']);state=base.fit(list(data.values()),selected['candidate'])
    atomic_json(output/'final.json',{k:v.tolist() if isinstance(v,torch.Tensor) else v for k,v in state.items()})
    report={'protocol_sha256':plan['protocol_sha256'],'quality':quality,'control':old['control'],
            'folds':fold_reports,'predictions':rows,'selected':selected,'final_sha256':file_sha256(output/'final.json'),
            'promoted':all(quality[k]>old['control'][k] for k in ('accuracy','balanced_accuracy','macro_f1')),
            'independent_test':False,'deterministic_no_seed_average':True,'production_ready':False}
    atomic_json(output/'report.json',report)
    print(json.dumps({'quality':quality,'promoted':report['promoted'],'final':selected['candidate']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();torch.set_num_threads(4);run(a.parent,a.output)
