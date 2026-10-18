"""Dataset-free local inference for the frozen dense-boundary experiment."""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
import torch
from ml import boundary_temporal as training,boundary_inputs as data,object_state_infer as base
from ml.data.annotation_tasks import read_json
from ml.models.encoder import file_sha256,safe_torch_load
from ml.video_baseline import atomic_json,atomic_checkpoint

VERSION='dense-boundary-local-bundle-v1'

def code_hash():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()

def select_score(arm,tcn,ridge,gru):
    if arm not in training.ARMS or any(not math.isfinite(v) or not 0<=v<=1 for v in (tcn,ridge,gru)):raise ValueError('boundary score selection')
    return {'boundary_tcn':tcn,'boundary_ridge':ridge,'boundary_blend':.5*(tcn+gru),
            'boundary_ridge_blend':.5*(ridge+gru),'legacy_uniform':gru}[arm]

def bag_remains(probabilities,support,points,timing):
    """Physical observations with actual departure evidence; never legal status."""
    result=[]
    for actor,c in (('operator',4),('counter_person',5)):
        if not all(bool(support[k]) for k in (1,3,c)):continue
        present=False;run=[]
        def finish():
            if len(run)>=2:result.append({'observation':'bag_on_worktop_after_'+actor+'_departure','source_pts':run.copy(),
                                          'start_sec':timing[run[0]],'end_sec':timing[run[-1]],'validated':False,'normative_status':'unknown'})
        for n,point in enumerate(points):
            if probabilities[n,c]>=.65:present=True
            qualifies=present and probabilities[n,c]<=.35 and probabilities[n,1]>=.65 and probabilities[n,3]>=.65
            if qualifies:
                if run and timing[int(point)]-timing[run[-1]]>.75:finish();run=[]
                run.append(int(point))
            else:finish();run=[]
        finish()
    return result

def export(experiment,reference_bundle,output):
    out=Path(experiment);plan=read_json(out/'protocol.json');binding=read_json(out/'complete.json');choice=read_json(out/'frozen_decision.json')
    if (plan['version']!=training.VERSION or plan['code_sha256']!=training.code_hash()
        or plan['protocol_sha256']!=training.helpers.stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'})
        or file_sha256(out/'cv_report.json')!=binding['report_sha256'] or file_sha256(out/'frozen_decision.json')!=binding['decision_sha256']
        or choice['protocol_sha256']!=plan['protocol_sha256'] or choice['uses_reserved'] is not False):raise ValueError('frozen boundary decision changed')
    checkpoint=safe_torch_load(choice['fit'],expected_sha256=choice['fit_sha256'])
    if checkpoint['identity']['protocol']!=plan['protocol_sha256'] or checkpoint['identity']['ids']!=sorted(plan['development_ids']):raise ValueError('boundary training source identity')
    reference=Path(reference_bundle);base.Predictor(reference,'cpu');metadata=read_json(reference/'bundle.json')
    if metadata['original_fit_sha256']!=choice['reference_fit']['sha256'] or metadata['mode']!='uniform':raise ValueError('exact uniform GRU reference required')
    payload=safe_torch_load(reference/'weights.pt',expected_sha256=metadata['weights_sha256'],max_bytes=base.MAX_BYTES)
    state=checkpoint['state'];payload['boundary_state']={k:state[k] for k in ('model','normalization','support','readout')};payload=base.compact_state(payload)
    size=base.base.tensor_bytes(payload)
    if size>base.MAX_BYTES:raise ValueError('complete boundary model exceeds12MB')
    destination=Path(output);destination.mkdir(parents=True,exist_ok=False);atomic_checkpoint(destination/'weights.pt',payload);file_size=(destination/'weights.pt').stat().st_size
    if file_size>base.MAX_BYTES:raise ValueError('serialized boundary model exceeds12MB')
    metadata={**metadata,'weights_sha256':file_sha256(destination/'weights.pt'),'weights_file_bytes':file_size,'tensor_bytes':size,
              'reference_protocol_sha256':metadata['protocol_sha256'],'protocol_sha256':plan['protocol_sha256'],'threshold':choice['selected']['threshold'],
              'boundary_extension':{'version':VERSION,'training_code_sha256':training.code_hash(),'input_code_sha256':data.code_hash(),
                                    'inference_code_sha256':code_hash(),'taxonomy':list(data.TAXONOMY),'dimension':data.DIM,
                                    'arm':choice['selected']['arm'],'fit_sha256':choice['fit_sha256'],'review_sha256':plan['review_sha256'],
                                    'human_approved':False,'recognizers_validated':False,'scores_are_calibrated_probabilities':False,
                                    'event_confirmation_samples':2,'normative_status':'unknown'}}
    atomic_json(destination/'bundle.json',metadata);print(json.dumps(metadata),flush=True);return metadata

class Predictor(base.Predictor):
    def __init__(self,bundle,device='cuda'):
        super().__init__(bundle,device);extension=self.metadata.get('boundary_extension',{})
        if (extension.get('version')!=VERSION or extension.get('training_code_sha256')!=training.code_hash()
            or extension.get('input_code_sha256')!=data.code_hash() or extension.get('inference_code_sha256')!=code_hash()
            or extension.get('taxonomy')!=list(data.TAXONOMY) or extension.get('dimension')!=data.DIM
            or extension.get('arm') not in training.ARMS or extension.get('human_approved') is not False
            or extension.get('recognizers_validated') is not False):raise ValueError('unsupported boundary extension')
        state=safe_torch_load(Path(bundle)/'weights.pt',expected_sha256=self.metadata['weights_sha256'],max_bytes=base.MAX_BYTES)['boundary_state']
        norm=state['normalization']
        if norm['mean'].shape!=(data.DIM,) or norm['scale'].shape!=(data.DIM,) or not bool((norm['scale']>0).all()) or state['support'].shape!=(6,) or state['support'].dtype!=torch.bool:raise ValueError('boundary normalization/support')
        self.boundary_state=state;self.boundary_net=training.BoundaryNet(hidden=training.CONFIG['hidden'],dropout=training.CONFIG['dropout']).to(device)
        self.boundary_net.load_state_dict(state['model'],strict=True);self.boundary_net.eval();self.boundary_arm=extension['arm']

    def predict_boundary(self,features,gru):
        if features.ndim!=2 or features.shape[1]!=data.DIM or not 1<=len(features)<=360 or not torch.isfinite(features).all():raise ValueError('boundary source features')
        state=self.boundary_state;x=(features-state['normalization']['mean'])/state['normalization']['scale']
        with torch.inference_mode():logits,states=self.boundary_net(x[None].to(self.device),torch.tensor([len(x)],device=self.device),state['support'].to(self.device))
        p=states[0].sigmoid().cpu()*state['support'];tcn=float(logits[0].sigmoid());ridge=float(training.helpers.readout_predict(state['readout'],training.boundary_summary(p)))
        return select_score(self.boundary_arm,tcn,ridge,gru),p,{'boundary_tcn':tcn,'boundary_ridge':ridge,'uniform_gru':gru}

    def predict_maps(self,maps,priors,points,index,return_features=False):
        colors=self._colors
        if colors is None:raise ValueError('source-bound boundary colors required')
        features=data.features(torch.from_numpy(np.array(maps,dtype=np.float32)),colors)
        result=super().predict_maps(maps,priors,points,index,False)
        score,states,components=self.predict_boundary(features,result['component_scores']['gru']);support=self.boundary_state['support']
        for n,frame in enumerate(result['frames']):
            frame['boundary_state_scores']={name:float(states[n,c]) if bool(support[c]) else None for c,name in enumerate(data.TAXONOMY)}
            frame['boundary_recognizers_validated']=False;frame['state_scores_reference_only']=True;frame['objects_reference_only']=True
        timing={r['source_pts']:r['timestamp_sec'] for r in index['frames']}
        events=training.observed_events(states,support,points,timing)
        result.update(score=score,selected_arm=self.boundary_arm,boundary_components=components,
                      boundary_events=[{**e,'validated':False} for e in events],bag_remains_observations=bag_remains(states,support,points,timing),
                      classifier_protocol_sha256=self.metadata['protocol_sha256'],boundary_scores_are_calibrated_probabilities=False,
                      boundary_events_are_normative_findings=False)
        if return_features:result['features']=features.numpy().copy();result['source_pts']=points
        return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True);a=s.add_parser('export')
    for name in ('experiment','reference-bundle','output'):a.add_argument('--'+name,type=Path,required=True)
    a=s.add_parser('infer');a.add_argument('--bundle',type=Path,required=True);a.add_argument('--video',type=Path,required=True);a.add_argument('--device',choices=('cuda','cpu'),default='cuda');args=p.parse_args()
    if args.command=='export':export(args.experiment,args.reference_bundle,args.output)
    else:print(json.dumps(Predictor(args.bundle,args.device).analyze(args.video)),flush=True)
