"""Portable local source-action heads, preserving the measured clip ensemble."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import torch
import torch.nn.functional as F

from ml import action_kernel, action_linear, action_calibration, dino_probe, seed_vote_infer
from ml.data.deduplicate import stable_hash
from ml.data.pts_index import iter_indexed_frames
from ml.models.encoder import file_sha256, safe_torch_load
from ml.video_baseline import atomic_json, atomic_checkpoint

VERSION='source-action-heads-local-v1'


def artifact_sha(path):
    path=Path(path)
    if path.is_file() and not path.is_symlink() and path.stat().st_size==0:
        return hashlib.sha256(b'').hexdigest()
    return file_sha256(path)


def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
                        'linear':action_linear.code_hash(),'kernel':action_kernel.code_hash(),
                        'calibration':action_calibration.code_hash(),'seed':seed_vote_infer.code_hash()})


def methods(report, calibration=None):
    """Fixed priority: linear, kernel, calibration, then unchanged control."""
    result=[]
    for name in action_kernel.TAXONOMY:
        row=report['classes'][name]; baseline=row['control']['f1']; method='control'
        for candidate in ('linear','kernel'):
            m=row[candidate]
            if m['precision']>=.8 and m['recall']>=.5 and m['f1']>=.8 and m['f1']>baseline:
                method=candidate; break
        if method=='control' and calibration:
            m=calibration['classes'][name]['candidate']
            if m['precision']>=.8 and m['recall']>=.5 and m['f1']>=.8 and m['f1']>baseline:method='calibration'
        result.append(method)
    return result


def decision_score(p, threshold):
    """Monotone display score whose .5 cut equals the inner-only threshold.

    This is a decision margin, not a calibrated probability. Disabled heads do
    not produce a positive score, including a raw output equal to one.
    """
    p=np.asarray(p,dtype=np.float64)
    if not np.isfinite(p).all() or ((p<0)|(p>1)).any() or not np.isfinite(threshold) or threshold<=0:
        raise ValueError('Invalid action scores/threshold')
    if threshold>1:return np.zeros_like(p)
    return np.where(p<threshold,.5*p/threshold,.5+.5*(p-threshold)/max(1-threshold,1e-12))


def head_scores(state, features, kind):
    banks={}; result=[]
    for entry in state['heads']:
        if entry['head'] is None:result.append(None);continue
        key=entry['bank'];bank=state['banks'][key]
        if key not in banks:
            x=action_kernel.frame_features(features,bank['mode'])
            if kind=='kernel':x=torch.exp(-bank['gamma']*(1-x@bank['anchors'].T).clamp_min(0))
            x=(x-bank['mean'])/bank['scale']
            if not torch.isfinite(x).all():raise ValueError('Nonfinite action normalization')
            banks[key]=x
        h=entry['head'];z=(banks[key]@h['weight']+h['bias']).clamp(-30,30)
        result.append(z.sigmoid().numpy())
    return result


def proof(bundle,metadata):
    bundle=Path(bundle);ext=metadata.get('source_action_extension',{})
    if (metadata.get('version')!=VERSION or ext.get('code_sha256')!=code_hash()
            or ext.get('model_sha256')!=stable_hash({k:v for k,v in ext.items() if k!='model_sha256'})
            or metadata.get('production_ready') is not False):raise ValueError('Unsupported source-action package')
    for name,digest in ext['files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or artifact_sha(bundle/path)!=digest:raise ValueError('Source-action file changed')
    actual={p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file() and p.name!='bundle.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    expected={name for name in ext['files'] if Path(name).name!='bundle.json'}
    if actual!=expected:raise ValueError('Unexpected source-action package files')
    plan=json.loads((bundle/'action_protocol.json').read_text());report=json.loads((bundle/'action_report.json').read_text())
    cal_plan=json.loads((bundle/'calibration_protocol.json').read_text());cal=json.loads((bundle/'calibration_report.json').read_text())
    if (plan['code_sha256']!=action_linear.code_hash()
            or plan['protocol_sha256']!=stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'})
            or report['protocol_sha256']!=plan['protocol_sha256'] or report['independent_test'] is not False
            or ext['methods']!=methods(report,cal) or not any(m!='control' for m in ext['methods'])
            or set(plan['development_ids'])&set(plan['reserved_ids']) or len(plan['development_ids'])!=36):
        raise ValueError('Action promotion gate or partition changed')
    if (cal_plan['code_sha256']!=action_calibration.code_hash()
            or cal_plan['protocol_sha256']!=stable_hash({k:v for k,v in cal_plan.items() if k!='protocol_sha256'})
            or cal['protocol_sha256']!=cal_plan['protocol_sha256'] or cal_plan['folds']!=plan['folds']
            or cal_plan['development_ids']!=plan['development_ids'] or cal.get('independent_test') is not False):
        raise ValueError('Temporal calibration protocol changed')
    # Recompute every metric from packaged held-family predictions, including
    # unsupported classes as misses. Do not trust a hand-written F1 summary.
    targets=[];linear=[];kernel=[];control=[];calibrated=[];seen=[]
    for n,fold in enumerate(plan['folds']):
        v=set(fold['validation']);t=set(fold['train'])
        if v&t or v|t!=set(plan['development_ids']):raise ValueError('Action fold leakage')
        seen.extend(fold['validation'])
        a=np.load(bundle/f'oof/linear-{n}.npz');b=np.load(bundle/f'oof/kernel-{n}.npz');cc=np.load(bundle/f'oof/calibration-{n}.npz')
        if (not np.array_equal(a['targets'],b['targets']) or not np.array_equal(a['targets'],cc['targets'])
                or not np.array_equal(a['control'],cc['control'],equal_nan=True)):raise ValueError('Action targets/control differ')
        targets.append(a['targets']);linear.append(a['decisions']);kernel.append(b['decisions']);control.append(a['control'])
        calibrated.append(cc['decisions'])
    if len(seen)!=36 or set(seen)!=set(plan['development_ids']):raise ValueError('Action OOF coverage')
    y=np.concatenate(targets)
    for kind,values in [('linear',linear),('kernel',kernel),('control',control)]:
        p=np.concatenate(values)
        for c,name in enumerate(action_kernel.TAXONOMY):
            if action_kernel.statistics(y[:,c],p[:,c],.5)!=report['classes'][name][kind]:raise ValueError('Action metrics disagree with OOF')
    for c,name in enumerate(action_kernel.TAXONOMY):
        if (action_kernel.statistics(y[:,c],np.concatenate(calibrated)[:,c],.5)!=cal['classes'][name]['candidate']
                or report['classes'][name]['control']!=cal['classes'][name]['control']):raise ValueError('Calibration metrics disagree with OOF')
    seed=json.loads((bundle/'seed_vote/bundle.json').read_text())
    seed_vote_infer.proof(bundle/'seed_vote',seed)
    if metadata['clip_metrics']!=seed['clip_metrics'] or ext['base_model_sha256']!=seed['seed_vote_extension']['model_sha256']:
        raise ValueError('Clip control changed')
    return ext


def export(experiment,calibration,seed_bundle,output):
    experiment,calibration,seed_bundle,output=map(Path,(experiment,calibration,seed_bundle,output));plan=json.loads((experiment/'protocol.json').read_text());report=json.loads((experiment/'report.json').read_text());cal=json.loads((calibration/'report.json').read_text())
    if plan['code_sha256']!=action_linear.code_hash() or report['final_sha256']!=file_sha256(experiment/'final.pt'):raise ValueError('Action fit changed')
    accepted=methods(report,cal)
    if not any(m!='control' for m in accepted):raise ValueError('No action candidate passed')
    output.mkdir(parents=True,exist_ok=False);shutil.copytree(seed_bundle,output/'seed_vote');(output/'oof').mkdir()
    shutil.copy2(experiment/'final.pt',output/'linear.pt')
    parent=Path(plan['parent']);old=json.loads((parent/'protocol.json').read_text());marker=json.loads((parent/'inputs.json').read_text())
    if old['code_sha256']!=action_kernel.code_hash() or file_sha256(parent/'inputs.json')!=plan['inputs_sha256']:raise ValueError('Kernel lineage')
    if 'kernel' in accepted:
        data={e['video_id']:safe_torch_load(parent/'inputs'/(e['video_id']+'.pt'),expected_sha256=e['sha256']) for e in marker['entries']}
        choices=action_kernel.select(data,old['final_inner']);_,state=action_kernel.train_selected(data,old['development_ids'],old['development_ids'],choices)
        state.update(version=action_kernel.VERSION,protocol_sha256=old['protocol_sha256'],taxonomy=list(action_kernel.TAXONOMY))
        atomic_checkpoint(output/'kernel.pt',state)
    for n in range(4):
        shutil.copy2(experiment/f'fold-{n}.npz',output/f'oof/linear-{n}.npz')
        shutil.copy2(parent/f'fold-{n}.npz',output/f'oof/kernel-{n}.npz')
        shutil.copy2(calibration/f'fold-{n}.npz',output/f'oof/calibration-{n}.npz')
    for src,dst in [('protocol.json','action_protocol.json'),('report.json','action_report.json')]:shutil.copy2(experiment/src,output/dst)
    for src,dst in [('protocol.json','calibration_protocol.json'),('report.json','calibration_report.json')]:shutil.copy2(calibration/src,output/dst)
    for name,digest in plan['source_files'].items():
        if file_sha256(Path(plan['source_root'])/name)!=digest:raise ValueError('Encoder source changed')
    shutil.copytree(plan['source_root'],output/'encoder_source',ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git'))
    if file_sha256(plan['weights'])!=dino_probe.WEIGHTS_SHA256:raise ValueError('Encoder weights changed')
    shutil.copy2(plan['weights'],output/'encoder.pth')
    metadata=json.loads((seed_bundle/'bundle.json').read_text());seed=metadata.pop('seed_vote_extension')
    ext={'version':VERSION,'code_sha256':code_hash(),'base_model_sha256':seed['model_sha256'],'methods':accepted,
         'protocol_sha256':plan['protocol_sha256'],'scores_are_calibrated':False,'independent_test':False,
         'files':{p.relative_to(output).as_posix():artifact_sha(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    ext['model_sha256']=stable_hash(ext)
    metadata.update(version=VERSION,source_action_extension=ext,ensemble_size=3,
                    action_metrics={n:(cal['classes'][n]['candidate'] if m=='calibration' else report['classes'][n][m])
                                    for n,m in zip(action_kernel.TAXONOMY,accepted) if m!='control'})
    proof(output,metadata);atomic_json(output/'bundle.json',metadata)
    print(json.dumps({'exported':ext['model_sha256'],'methods':dict(zip(action_kernel.TAXONOMY,accepted)),
                      'bytes':sum(p.stat().st_size for p in output.rglob('*') if p.is_file())}),flush=True)


class Predictor(seed_vote_infer.Predictor):
    def __init__(self,bundle,device='cuda'):
        bundle=Path(bundle);metadata=json.loads((bundle/'bundle.json').read_text(encoding='utf-8-sig'));self.actions=proof(bundle,metadata)
        super().__init__(bundle/'seed_vote',device);self.metadata=metadata
        self.calibration=json.loads((bundle/'calibration_report.json').read_text())['choices']
        self.action_states={}
        for kind in ('linear','kernel'):
            if kind in self.actions['methods']:
                state=safe_torch_load(bundle/(kind+'.pt'),expected_sha256=self.actions['files'][kind+'.pt'],max_bytes=64*1024**2)
                if state['train_ids']!=sorted(json.loads((bundle/'action_protocol.json').read_text())['development_ids']) or state['taxonomy']!=list(action_kernel.TAXONOMY):raise ValueError('Action training source identity')
                self.action_states[kind]=state
        self.action_encoder=dino_probe.encoder(bundle/'encoder_source',bundle/'encoder.pth',device)
        self.integrity_files=[(bundle/name,sha) for name,sha in self.actions['files'].items()]
        self._source_actions=None

    def encode(self,root,index):
        maps,priors,points=super().encode(root,index)
        selected=set(points);pending=[];values=[];actual=[]
        def flush():
            if not pending:return
            with torch.inference_mode():
                out=self.action_encoder.forward_features(torch.cat(pending).to(self.device))
                patch=out['x_norm_patchtokens'].transpose(1,2).reshape(len(pending)*2,384,28,28)
                pooled=F.adaptive_avg_pool2d(patch,(2,2)).flatten(1)
                values.append(torch.cat((out['x_norm_clstoken'],pooled),1).reshape(len(pending),3840).cpu())
            pending.clear()
        for timing,frame in iter_indexed_frames(Path(root),index):
            if timing['source_pts'] in selected:
                pending.append(dino_probe.tensors(frame.to_image(),index));actual.append(timing['source_pts'])
                if len(pending)==2:flush()
        flush()
        if actual!=points:raise ValueError('Action source PTS changed')
        self._source_actions=torch.cat(values)
        return maps,priors,points

    def predict_maps(self,maps,priors,points,index,return_features=False):
        features=self._source_actions;self._source_actions=None
        if features is None or features.shape!=(len(points),3840):raise ValueError('Missing source action features')
        result=super().predict_maps(maps,priors,points,index,return_features)
        predictions={kind:head_scores(state,features,kind) for kind,state in self.action_states.items()}
        replaced=set()
        for c,(name,kind) in enumerate(zip(action_kernel.TAXONOMY,self.actions['methods'])):
            if kind=='control':continue
            replaced.add(name)
            if kind=='calibration':
                entry=self.calibration[c];p=action_calibration.filtered(
                    [f['state_scores'][name] if f['state_scores'][name] is not None else float('nan') for f in result['frames']],
                    [f['timestamp_sec'] for f in result['frames']],entry['mode'])
            else:p=predictions[kind][c];entry=self.action_states[kind]['heads'][c]
            if p is None:raise ValueError('Accepted action class is unsupported')
            scores=decision_score(p,entry['threshold'])
            for n,frame in enumerate(result['frames']):
                frame['state_scores'][name]=float(scores[n])
                frame.setdefault('action_head_scores',{})[name]={'score':float(p[n]),'threshold':entry['threshold'],'method':kind}
        result['candidate_events']=[e for e in result['candidate_events'] if e['action'] not in replaced]
        for name in sorted(replaced):
            current=[]
            def end_run():
                if current:result['candidate_events'].append({'action':name,'source_pts':[f['source_pts'] for f in current],
                    'start_sec':current[0]['timestamp_sec'],'end_sec':current[-1]['timestamp_sec'],'interval_validated':False})
            for frame in result['frames']:
                if frame['state_scores'][name]>=.5:
                    if current and frame['timestamp_sec']-current[-1]['timestamp_sec']>.75:end_run();current=[]
                    current.append(frame)
                elif current:end_run();current=[]
            end_run()
        result.update(action_metrics=self.metadata['action_metrics'],rule_probes=[],rule_probes_disabled='New visual context heads are unvalidated for normative rules')
        return result

    def analyze(self,video,**kwargs):
        result=super().analyze(video,**kwargs);result['model_sha256']=self.actions['model_sha256'];return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,required=True);p.add_argument('--calibration',type=Path,required=True);p.add_argument('--seed-bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();torch.set_num_threads(4);export(a.experiment,a.calibration,a.seed_bundle,a.output)
