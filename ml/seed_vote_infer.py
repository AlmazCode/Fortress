"""Three measured seed controls, one shared CNN pass, source-bound review heads."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import torch

from ml import seed_vote
from ml import object_events as training
from ml import object_state_infer as control
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint,metrics

VERSION='three-seed-vote-extension-v1'
BASE_SHA='c5c673f54cabb1e675f058950454a4f431d39aae5fa656c26cc79f7853b0a077'
FILES={'vote_heads.pt','vote_protocol.json','vote_report.json','control/bundle.json'}


def code_hash():
    return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()


def vote_score(scores, thresholds):
    if (len(scores)!=3 or len(thresholds)!=3
            or any(type(v) not in (float,int) or not 0<=v<=1 for v in [*scores,*thresholds])):
        raise ValueError('Three finite seed decisions required')
    return sum(s>=t for s,t in zip(scores,thresholds))/3


def proof(bundle, metadata):
    bundle=Path(bundle);ext=metadata.get('seed_vote_extension',{})
    if (metadata.get('version')!=VERSION or metadata.get('threshold')!=.5
            or ext.get('version')!=VERSION or ext.get('inference_code_sha256')!=code_hash()
            or ext.get('seeds')!=[42,137,2026] or metadata.get('weights_sha256')!=BASE_SHA
            or metadata.get('risk_extension') or metadata.get('mode')!='uniform'
            or ext.get('model_sha256')!=stable_hash({k:v for k,v in ext.items() if k!='model_sha256'})
            or set(ext.get('files',{}))!=FILES):
        raise ValueError('Unsupported seed vote package')
    for name,digest in ext['files'].items():
        if file_sha256(bundle/name)!=digest:raise ValueError('Seed vote file changed')
    plan=json.loads((bundle/'vote_protocol.json').read_text(encoding='utf-8'))
    report=json.loads((bundle/'vote_report.json').read_text(encoding='utf-8'))
    quality=metrics(report['predictions'],.5)
    if (plan.get('version')!='fixed-three-seed-majority-v1'
            or plan.get('code_sha256')!=file_sha256(Path(seed_vote.__file__))
            or plan.get('protocol_sha256')!=stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'})
            or report.get('protocol_sha256')!=plan['protocol_sha256']
            or report.get('promotion_gate_passed') is not True
            or report.get('quality')!=quality or report.get('independent_test') is not False
            or plan.get('outer_tuning') is not False or plan.get('seed_order')!=list(seed_vote.SEEDS)
            or any(quality[k]<=report['control'][k] or quality[k]!=metadata['clip_metrics'][k]
                   for k in ('accuracy','balanced_accuracy','macro_f1'))):
        raise ValueError('Seed vote did not pass its measured gate')
    if (len(report['predictions'])!=36 or len({r['video_id'] for r in report['predictions']})!=36
            or {r['video_id'] for r in report['predictions']}!=set(plan['development_ids'])
            or set(plan['development_ids'])&set(plan['reserved_ids'])
            or ext.get('member_fit_sha256',[None])[0]!=metadata.get('original_fit_sha256')):
        raise ValueError('Seed vote source partition changed')
    vote_score([.5]*3,ext['thresholds'])
    return ext


def export(experiment, reference, base_bundle, output, control_reference):
    experiment,reference,base_bundle,output=map(Path,(experiment,reference,base_bundle,output))
    report=json.loads((experiment/'report.json').read_text());plan=json.loads((experiment/'protocol.json').read_text())
    final=json.loads((experiment/'final_members.json').read_text())
    old_report=json.loads((reference/'cv_report.json').read_text())
    old_plan=json.loads((reference/'protocol.json').read_text())
    metadata=json.loads((base_bundle/'bundle.json').read_text())
    preserved=json.loads(Path(control_reference).read_text())
    if preserved['sha256']!=metadata['original_fit_sha256']:
        raise ValueError('Preserved control fit changed')
    # Keep the deployed seed42 exactly. The equivalent rerun has its own SHA
    # (including timing metadata) and is preserved in final_members.json.
    final['members'][0]={**final['members'][0],'fit':preserved['fit'],'fit_sha256':preserved['sha256']}
    if (plan['control_report_sha256']!=file_sha256(reference/'cv_report.json')
            or report['promotion_gate_passed'] is not True or metadata['weights_sha256']!=BASE_SHA
            or file_sha256(base_bundle/'weights.pt')!=BASE_SHA
            or final['reference_protocol_sha256']!=old_plan['protocol_sha256']
            or sorted(final['development_ids'])!=sorted(plan['development_ids'])
            or [m['seed'] for m in final['members']]!=[42,137,2026]):
        raise ValueError('Seed vote export lineage')
    members=[]
    for entry in final['members']:
        fit=safe_torch_load(entry['fit'],expected_sha256=entry['fit_sha256'])
        if fit['identity']!={'protocol':old_plan['protocol_sha256'],'kind':'temporal','mode':'uniform',
                            'ids':sorted(plan['development_ids']),'seed':entry['seed']}:
            raise ValueError('Seed member was not trained on exact development partition')
        spatial=safe_torch_load(fit['spatial'],expected_sha256=fit['spatial_sha256'])
        if entry['seed']==42 and entry['fit_sha256']!=metadata['original_fit_sha256']:
            raise ValueError('First seed differs from the frozen control')
        if entry['seed']!=42:
            members.append({'seed':entry['seed'],'fit_sha256':entry['fit_sha256'],'spatial':spatial['model'],
                            'temporal':fit['model'],'normalization':fit['normalization'],'cup_calibration':spatial['cup_calibration']})
    threshold=old_report['final_choices']['uniform_gru']['threshold']
    if threshold!=metadata['threshold']:raise ValueError('Control threshold changed')
    output.mkdir(parents=True,exist_ok=False);(output/'control').mkdir()
    shutil.copy2(base_bundle/'weights.pt',output/'control/weights.pt')
    shutil.copy2(base_bundle/'bundle.json',output/'control/bundle.json')
    atomic_checkpoint(output/'vote_heads.pt',{'version':VERSION,'members':members})
    for src,dst in [('protocol.json','vote_protocol.json'),('report.json','vote_report.json')]:
        shutil.copy2(experiment/src,output/dst)
    ext={'version':VERSION,'inference_code_sha256':code_hash(),'seeds':[42,137,2026],
         'thresholds':[threshold]*3,'member_fit_sha256':[m['fit_sha256'] for m in final['members']],
         'files':{name:file_sha256(output/name) for name in sorted(FILES)},'new_source_videos':False,
         'classifier_score_kind':'fraction_of_positive_seed_votes','independent_test':False}
    ext['model_sha256']=stable_hash(ext)
    metadata.update(version=VERSION,threshold=.5,seed_vote_extension=ext,
                    clip_metrics={k:report['quality'][k] for k in ('accuracy','balanced_accuracy','macro_f1')})
    proof(output,metadata)
    atomic_json(output/'bundle.json',metadata)
    print(json.dumps({'exported':ext['model_sha256'],'bytes':sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),'quality':metadata['clip_metrics']}),flush=True)


class Predictor(control.Predictor):
    def __init__(self,bundle,device='cuda'):
        bundle=Path(bundle);metadata=json.loads((bundle/'bundle.json').read_text(encoding='utf-8-sig'))
        self.vote=proof(bundle,metadata)
        super().__init__(bundle/'control',device)
        self.metadata=metadata
        state=safe_torch_load(bundle/'vote_heads.pt',expected_sha256=self.vote['files']['vote_heads.pt'],max_bytes=32*1024**2)
        if state['version']!=VERSION or [m['seed'] for m in state['members']]!=[137,2026]:
            raise ValueError('Seed vote head identity')
        self.members=[]
        for n,entry in enumerate(state['members'],1):
            if entry['fit_sha256']!=self.vote['member_fit_sha256'][n]:raise ValueError('Foreign seed vote member')
            spatial=training.SpatialHeads().to(device).eval();spatial.load_state_dict(entry['spatial'],strict=True)
            temporal=training.Temporal().to(device).eval();temporal.load_state_dict(entry['temporal'],strict=True)
            norm=entry['normalization']
            if norm['mean'].shape!=(646,) or norm['std'].shape!=(646,) or (norm['std']<=0).any():
                raise ValueError('Seed vote normalization')
            self.members.append({'spatial':spatial,'temporal':temporal,'normalization':norm,'cup_calibration':entry['cup_calibration']})
        self.integrity_files=[(bundle/'control/weights.pt',BASE_SHA),*[(bundle/name,sha) for name,sha in self.vote['files'].items()]]

    def extra_score(self,member,maps,priors):
        outputs=[]
        with torch.inference_mode():
            for start in range(0,len(maps),16):
                out=member['spatial'](torch.from_numpy(np.array(maps[start:start+16],dtype=np.float32)).to(self.device))
                outputs.append((out[3].cpu(),out[5].cpu()))
            uniform=torch.cat([o[0] for o in outputs]);meta=torch.cat([o[1] for o in outputs])
            prior=training.calibrate_cup_prior(torch.from_numpy(np.array(priors,copy=True)),member['cup_calibration'])
            meta=torch.cat((meta,prior.flatten(1).amax(-1)[:,None],prior.flatten(1).mean(-1)[:,None]),1)
            features=torch.cat((uniform,meta),1);norm=member['normalization']
            sequence=(features-norm['mean'])/norm['std']
            logit,_=member['temporal'](sequence[None].to(self.device),torch.tensor([len(sequence)]))
            return float(logit.sigmoid()[0].cpu())

    def predict_maps(self,maps,priors,points,index,return_features=False):
        result=super().predict_maps(maps,priors,points,index,return_features)
        scores=[result['component_scores']['gru'],*[self.extra_score(m,maps,priors) for m in self.members]]
        result.update(score=vote_score(scores,self.vote['thresholds']),seed_component_scores=scores,
                      ensemble_size=3,score_is_calibrated_probability=False,clip_metrics=self.metadata['clip_metrics'])
        return result

    def analyze(self,video,**kwargs):
        result=super().analyze(video,**kwargs)
        result.update(threshold=.5,prediction='violation' if result['score']>=.5 else 'no_violation',
                      model_sha256=self.vote['model_sha256'])
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--base-bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--control-reference',type=Path,required=True)
    a=p.parse_args();export(a.experiment,a.reference,a.base_bundle,a.output,a.control_reference)
