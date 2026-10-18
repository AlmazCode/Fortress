"""Preregistered train-only weighted-BCE correction for observable rule scores."""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
import torch
from torch import nn
from ml import object_events as base
from ml import object_events_infer as portable
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256,safe_torch_load,FrozenEncoder
from ml.video_baseline import atomic_json,atomic_checkpoint,metrics
from ml.small_data import summarize

VERSION='posterior-object-rules-v1'
ARMS=('posterior_rules_linear','posterior_policy_fixed','posterior_hybrid_linear','posterior_hybrid_fixed')
def code_hash():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()
def correct(probability,log_weight):return (probability.clamp(1e-6,1-1e-6).logit()-log_weight).sigmoid()

def prepare(parent,preregister,output):
    plan=read_json(Path(parent)/'protocol.json');pre=read_json(preregister)
    if pre['parent_protocol_sha256']!=plan['protocol_sha256'] or pre['parent_complete_existed'] is not False or pre['reserved_not_evaluated'] is not True:raise ValueError('calibration was not preregistered')
    document={'version':VERSION,'parent':str(Path(parent).resolve()),'parent_protocol_sha256':plan['protocol_sha256'],
              'parent_code_sha256':plan['code_sha256'],'code_sha256':code_hash(),'preregister_sha256':file_sha256(preregister),
              'new_arms':list(ARMS),'seeds':[42,137,2026],'primary_seed':42,'folds':plan['folds'],'final_inner':plan['final_inner'],
              'development_ids':plan['development_ids'],'reserved_ids':plan['reserved_ids'],
              'selection':'same inner folds; all6 parent arms+4 posterior arms; no outer/test threshold optimization',
              'correction':'sigmoid(logit(q)-log(train_pos_weight)); disabled states remain unknown',
              'linear':'zero init;150 fullbatch AdamW steps lr.01 weight_decay1;train-only mean/std(.05 minimum)',
              'production_ready':False,'independent_external_test':False}
    document['protocol_sha256']=stable_hash(document);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    atomic_json(out/'protocol.json',document);(out/'source_snapshot.py').write_text(Path(__file__).read_text(encoding='utf-8-sig'),encoding='utf-8')
    print(json.dumps({'prepared':str(out),'protocol_sha256':document['protocol_sha256']}),flush=True)

class Experiment:
    def __init__(self,directory):
        torch.set_num_threads(4);self.directory=Path(directory);self.plan=read_json(self.directory/'protocol.json')
        if self.plan['code_sha256']!=code_hash() or self.plan['protocol_sha256']!=stable_hash({k:v for k,v in self.plan.items() if k!='protocol_sha256'}):raise ValueError('posterior code/protocol changed')
        self.base=base.Experiment(self.plan['parent']);self.base_report=read_json(Path(self.plan['parent'])/'cv_report.json')
        choice=portable.decision(self.plan['parent'])
        if self.base.plan['protocol_sha256']!=self.plan['parent_protocol_sha256'] or self.base.plan['code_sha256']!=self.plan['parent_code_sha256']:raise ValueError('parent lineage changed')
        binding={'report_sha256':file_sha256(Path(self.plan['parent'])/'cv_report.json'),'decision_fit_sha256':choice['fit_sha256']}
        path=self.directory/'parent_binding.json'
        if path.exists() and read_json(path)!=binding:raise ValueError('parent report changed')
        if not path.exists():atomic_json(path,binding)
        self.fits=self.directory/'fits';self.fits.mkdir(exist_ok=True)

    def neural(self,ids,seed,final=False):
        self.base.guard_ids(ids)
        identity={'protocol':self.base.plan['protocol_sha256'],'kind':'temporal','mode':'objects','ids':sorted(ids),'seed':seed}
        path=self.base.fits/(stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('neural identity mismatch')
            return path
        if not final:raise ValueError('required frozen parent fit absent')
        destination=self.directory/'final_neural';destination.mkdir(exist_ok=True);original=self.base.fits
        try:
            self.base.fits=destination
            return self.base.fit(ids,'objects',seed)
        finally:self.base.fits=original

    def fit(self,ids,seed,final=False):
        neural=self.neural(ids,seed,final);digest=file_sha256(neural)
        identity={'protocol':self.plan['protocol_sha256'],'ids':sorted(ids),'seed':seed,'neural_sha256':digest}
        path=self.fits/(stable_hash(identity)+'.pt')
        if path.exists():
            if safe_torch_load(path)['identity']!=identity:raise ValueError('readout identity mismatch')
            return path
        state=safe_torch_load(neural);spatial=Path(state['spatial']);observed=self.base.observations(spatial,ids)
        targets=torch.cat([self.base.rows[v]['actions'] for v in ids]);weights=base.auxiliary_weights(targets[None])['positive_weight'];log_weight=weights.log()
        features=[]
        for o in observed:
            states=correct(o['states'],log_weight)
            features.append(base.rule_features(states,o['objects'],o['prior'],o['support'],o['object_support']))
        features=torch.stack(features);mean=features.mean(0);std=features.std(0,unbiased=False).clamp_min(.05)
        y=torch.tensor([self.base.rows[v]['target'] for v in ids],dtype=torch.float32);head=nn.Linear(24,1)
        nn.init.zeros_(head.weight);nn.init.zeros_(head.bias);optimizer=torch.optim.AdamW(head.parameters(),lr=.01,weight_decay=1.)
        loss_fn=nn.BCEWithLogitsLoss(pos_weight=(y==0).sum()/(y==1).sum())
        for _ in range(150):
            loss=loss_fn(head((features-mean)/std).squeeze(1),y);optimizer.zero_grad(set_to_none=True);loss.backward();optimizer.step()
        atomic_checkpoint(path,{'format':VERSION,'identity':identity,'neural':str(neural.resolve()),'spatial_sha256':state['spatial_sha256'],
                                'log_weight':log_weight,'head':dict(head.state_dict()),'mean':mean,'std':std,'production_ready':False})
        print(json.dumps({'readout_fit':len(ids),'seed':seed}),flush=True);return path

    def predict(self,path,ids):
        state=safe_torch_load(path)
        if state['identity']['protocol']!=self.plan['protocol_sha256'] or file_sha256(state['neural'])!=state['identity']['neural_sha256']:raise ValueError('readout/neural lineage mismatch')
        nnstate=safe_torch_load(Path(state['neural']));observed=self.base.observations(Path(nnstate['spatial']),ids)
        raw=self.base.predict(Path(state['neural']),ids);features=[]
        for o in observed:
            features.append(base.rule_features(correct(o['states'],state['log_weight']),o['objects'],o['prior'],o['support'],o['object_support']))
        f=torch.stack(features);head=nn.Linear(24,1);head.load_state_dict(state['head'])
        with torch.no_grad():linear=head((f-state['mean'])/state['std']).squeeze(1).sigmoid()
        result=[]
        for n,p in enumerate(raw):
            fixed=float(f[n,:7].amax());rl=float(linear[n]);g=p['gru']
            result.append({**p,'posterior_rules_linear':rl,'posterior_policy_fixed':fixed,'posterior_hybrid_linear':.5*(g+rl),'posterior_hybrid_fixed':.5*(g+fixed)})
        return result

    def choices(self,folds,parent_choices):
        result=dict(parent_choices);predictions=[]
        expected={v for fold in folds for v in fold['validation']}
        for choice in parent_choices.values():
            if {p['video_id'] for p in choice['oof']}!=expected:raise ValueError('parent inner OOF mismatch')
        for fold in folds:predictions.extend(self.predict(self.fit(fold['train'],42),fold['validation']))
        for arm in ARMS:
            rows=[{**p,'score':p[arm]} for p in predictions];threshold=base.previous.calibrate(rows)
            bce=float(np.mean([-math.log(max(1e-7,min(1-1e-7,p['score'] if p['truth'] else 1-p['score']))) for p in rows]))
            result[arm]={'arm':arm,'threshold':threshold,'metrics':metrics(rows,threshold),'bce':bce,'oof':rows}
        return result,max(result.values(),key=base.previous.rank)

def run(directory):
    experiment=Experiment(directory);out=Path(directory)
    if (out/'complete.json').exists():raise ValueError('completed posterior experiment immutable')
    nested={str(s):[] for s in base.SEEDS};results={a:{str(s):[] for s in base.SEEDS} for a in (*base.ARMS,*ARMS)};reports=[]
    for n,fold in enumerate(experiment.plan['folds']):
        parent=experiment.base_report['folds'][n];choices,selected=experiment.choices(fold['inner'],parent['choices'])
        for seed in base.SEEDS:
            new=experiment.predict(experiment.fit(fold['train'],seed),fold['validation'])
            for arm in results:
                if arm in base.ARMS:rows=experiment.base_report['oof'][arm][str(seed)];rows=[p for p in rows if p['fold']==n]
                else:rows=[{**p,'score':p[arm],'threshold':choices[arm]['threshold'],'fold':n,'arm':arm} for p in new]
                results[arm][str(seed)].extend(rows)
                if arm==selected['arm']:nested[str(seed)].extend(rows)
        record={'fold':n,'choices':choices,'selected':selected['arm']};reports.append(record);atomic_json(out/f'outer-fold-{n}.json',record)
    choices,selected=experiment.choices(experiment.plan['final_inner'],experiment.base_report['final_choices'])
    if selected['arm'] in ARMS:
        fitted=experiment.fit(experiment.plan['development_ids'],42,True);state=safe_torch_load(fitted);neural=state['neural']
    else:
        fitted=None;original=experiment.base_report['frozen_decision'];neural=original['fit']
        if selected['arm']!=original['selected']['arm']:raise ValueError('parent final selection mismatch')
    choice={'protocol_sha256':experiment.plan['protocol_sha256'],'selected':selected,'neural_fit':str(Path(neural).resolve()),
            'neural_sha256':file_sha256(neural),'readout_fit':str(fitted.resolve()) if fitted else None,'readout_sha256':file_sha256(fitted) if fitted else None,
            'uses_reserved':False,'production_ready':False}
    atomic_json(out/'frozen_decision.json',choice)
    report={'version':VERSION,'comparisons':{a:{s:summarize(p) for s,p in ss.items()} for a,ss in results.items()},'nested_metrics':{s:summarize(p) for s,p in nested.items()},
            'oof':results,'nested_oof':nested,'folds':reports,'final_choices':choices,'frozen_decision':choice,'production_ready':False,'independent_external_test':False}
    atomic_json(out/'cv_report.json',report);atomic_json(out/'complete.json',{'report_sha256':file_sha256(out/'cv_report.json'),'decision_sha256':file_sha256(out/'frozen_decision.json')})
    print(json.dumps({'nested':report['nested_metrics'],'selected':selected['arm']}),flush=True)

def export(directory,output):
    out=Path(directory);plan=read_json(out/'protocol.json');marker=read_json(out/'complete.json')
    if plan['code_sha256']!=code_hash() or file_sha256(out/'frozen_decision.json')!=marker['decision_sha256'] or file_sha256(out/'cv_report.json')!=marker['report_sha256']:raise ValueError('posterior decision changed')
    choice=read_json(out/'frozen_decision.json');parent_plan=read_json(Path(plan['parent'])/'protocol.json');inputs=read_json(Path(parent_plan['spatial'])/'inputs.json')
    state=safe_torch_load(Path(choice['neural_fit']),expected_sha256=choice['neural_sha256']);spatial=safe_torch_load(Path(state['spatial']),expected_sha256=state['spatial_sha256'])
    encoder=FrozenEncoder(weights_path=Path(inputs['encoder_weights']),weights_sha256=inputs['encoder_sha256']);classifier=base.data.cup_classifier(Path(inputs['encoder_weights']),inputs['encoder_sha256'])
    payload={'format':portable.VERSION,'encoder':dict(encoder.features.state_dict()),'cup_classifier':dict(classifier.state_dict()),'spatial':spatial['model'],'temporal':state['model'],
             'normalization':state['normalization'],'cup_calibration':spatial['cup_calibration'],'rule_head':state['rule_head'],'rule_mean':state['rule_mean'],'rule_std':state['rule_std']}
    selected=choice['selected']['arm'];arm=selected.removeprefix('posterior_')
    if choice['readout_fit']:
        corrected=safe_torch_load(Path(choice['readout_fit']),expected_sha256=choice['readout_sha256'])
        payload.update(log_weight_correction=corrected['log_weight'],rule_head=corrected['head'],rule_mean=corrected['mean'],rule_std=corrected['std'])
    size=portable.tensor_bytes(payload)
    if size>12*1024**2:raise ValueError('bundle exceeds12MiB')
    output=Path(output);output.mkdir(parents=True,exist_ok=False);atomic_checkpoint(output/'weights.pt',payload)
    metadata={'version':portable.VERSION,'weights_sha256':file_sha256(output/'weights.pt'),'original_fit_sha256':choice['neural_sha256'],
              'spatial_fit_sha256':state['spatial_sha256'],'protocol_sha256':plan['protocol_sha256'],'arm':arm,'selection_arm':selected,'mode':state['identity']['mode'],
              'threshold':choice['selected']['threshold'],'input_version':base.data.VERSION,'size':448,'rate':2.,'variants':list(base.data.VARIANTS),'map_dtype':'float16',
              'roi':list(base.data.base.ROI),'taxonomy':list(base.data.TAXONOMY),'objects':list(base.data.OBJECTS),'cup_classes':['coffee mug','cup'],
              'training_code_sha256':base.code_hash(),'inference_code_sha256':portable.code_hash(),'calibration_code_sha256':code_hash(),'tensor_bytes':size,
              'production_ready':False,'recognizers_validated':False,'normative_status':'unknown','human_approved_extra_labels':False}
    atomic_json(output/'bundle.json',metadata);print(json.dumps(metadata),flush=True)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('prepare')
    for name in ('parent','preregister','output'):a.add_argument('--'+name,type=Path,required=True)
    for name in ('run','export'):
        a=s.add_parser(name);a.add_argument('--experiment',type=Path,required=True)
        if name=='export':a.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv)
    if a.command=='prepare':prepare(a.parent,a.preregister,a.output)
    elif a.command=='run':run(a.experiment)
    else:export(a.experiment,a.output)

if __name__=='__main__':main()
