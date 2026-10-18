import math
import numpy as np
import pytest
import torch
from ml import object_state_infer as inference
from ml.models.encoder import FrozenEncoder,file_sha256
from ml.video_baseline import atomic_checkpoint,atomic_json


def test_complete_local_roi_bundle_runs_without_dataset_and_ignores_prior_for_new_rules(tmp_path):
    torch.set_num_threads(2);base=inference.base;encoder=FrozenEncoder(test_only=True)
    spatial=inference.training.original.SpatialHeads();temporal=inference.training.original.Temporal()
    classifier=torch.nn.Sequential(torch.nn.Linear(576,512),torch.nn.Hardswish(),torch.nn.Linear(512,1000));rule=torch.nn.Linear(24,1)
    def model(dim,outputs,bias=None):
        return {'normalization':{'mean':torch.zeros(dim),'scale':torch.ones(dim)},'weight':torch.zeros(dim,outputs),
                'bias':torch.zeros(outputs) if bias is None else torch.tensor(bias),'support':torch.ones(outputs,dtype=torch.bool)}
    state={'bag':{**model(583,1),'median_size':torch.tensor([.15,.18]),'supported':True},'safe':{**model(1372,4,[.5,.3,.7,.7]),'supported':True},
           'laptop':{**model(1372,4,[.2,.4,.5,.7]),'supported':True},'safe_appearance':model(5247,1),'laptop_appearance':model(5247,2),'bag_appearance':model(5247,2)}
    state['laptop_appearance']['support'][1]=False
    payload={'format':base.VERSION,'encoder':dict(encoder.features.state_dict()),'cup_classifier':dict(classifier.state_dict()),
             'spatial':dict(spatial.state_dict()),'temporal':dict(temporal.state_dict()),'state_context':dict(spatial.state_dict()),
             'normalization':{'mean':torch.zeros(646),'std':torch.ones(646)},'cup_calibration':torch.tensor([math.log(1e-6),.25]),
             'rule_head':dict(rule.state_dict()),'rule_mean':torch.zeros(24),'rule_std':torch.ones(24),'roi_state':state,'roi_readout':None}
    assert base.tensor_bytes(payload)<inference.MAX_BYTES
    atomic_checkpoint(tmp_path/'weights.pt',payload)
    candidate={'name':'persistent_base','arm':'persistent','hard':False,'alpha':1.}
    metadata={'version':base.VERSION,'weights_sha256':file_sha256(tmp_path/'weights.pt'),'training_code_sha256':inference.training.original.code_hash(),
              'inference_code_sha256':base.code_hash(),'input_version':inference.data.parent.VERSION,'size':448,'rate':2.,
              'variants':list(inference.data.parent.VARIANTS),'roi':list(inference.data.parent.base.ROI),'taxonomy':list(inference.data.parent.TAXONOMY),
              'objects':list(inference.data.parent.OBJECTS),'cup_classes':['coffee mug','cup'],'arm':'hybrid_fixed','mode':'objects','threshold':.5,
              'production_ready':False,'protocol_sha256':'a'*64,'tensor_bytes':base.tensor_bytes(payload),'weights_file_bytes':(tmp_path/'weights.pt').stat().st_size,
              'roi_extension':{'version':inference.VERSION,'training_code_sha256':inference.training.code_hash(),'inference_code_sha256':inference.code_hash(),
                               'input_code_sha256':inference.data.code_hash(),'taxonomy':list(inference.data.TAXONOMY),'candidate':candidate}}
    atomic_json(tmp_path/'bundle.json',metadata);runtime=inference.Predictor(tmp_path,'cpu')
    maps=np.ones((3,576,14,14),np.float16);prior=np.zeros((3,14,14),np.float32)
    index={'video_id':'synthetic','width':464,'height':848,'rotation':0,'frames':[{'source_pts':n,'timestamp_sec':n/2} for n in range(3)]}
    runtime._colors=torch.zeros(3,1372);result=runtime.predict_maps(maps,prior,[0,1,2],index,True)
    assert result['features'].shape==(3,10588) and 0<=result['score']<=1
    assert result['frames'][0]['state_scores']['screen_bright_content'] is None
    assert result['rule_probes'][2]['score'] is None and set(result['rule_template_status'].values())=={'unknown'}
    runtime._colors=torch.zeros(3,1372);changed=runtime.predict_maps(maps,np.ones_like(prior),[0,1,2],index)
    assert changed['score']==result['score'] and changed['cup_prior_excluded_from_new_rules'] is True
    with pytest.raises(ValueError,match='source-bound colors'):runtime.predict_maps(maps,prior,[0,1,2],index)
    runtime.state['bag']['supported']=False;runtime._colors=torch.zeros(3,1372)
    unsupported=runtime.predict_maps(maps,prior,[0,1,2],index)
    assert unsupported['frames'][0]['state_scores']['green_bag_visible'] is None
    assert unsupported['frames'][0]['state_scores']['bag_on_desk'] is None
    assert unsupported['rule_probes'][0]['score'] is None
    assert 'bag' not in unsupported['frames'][0]['object_rois']
    extension={**metadata['roi_extension'],'pipeline_version':inference.ensemble.VERSION,'ensemble_code_sha256':inference.ensemble.code_hash(),
               'candidate':{'name':'policy_blend_base','arm':'policy_blend','hard':False,'alpha':1.}}
    combined={**metadata,'arm':'uniform_gru','mode':'uniform','roi_extension':extension};atomic_json(tmp_path/'bundle.json',combined)
    runtime2=inference.Predictor(tmp_path,'cpu');runtime2._colors=torch.zeros(3,1372)
    blended=runtime2.predict_maps(maps,prior,[0,1,2],index)
    fixed=max(p['score'] or 0 for p in blended['rule_probes'][:4])
    assert blended['score']==pytest.approx(.5*(fixed+blended['component_scores']['gru']))
    extension={**extension,'candidate':{'name':'legacy_uniform','arm':'legacy_uniform','hard':False,'alpha':1.}}
    atomic_json(tmp_path/'bundle.json',{**combined,'roi_extension':extension});runtime3=inference.Predictor(tmp_path,'cpu');runtime3._colors=torch.zeros(3,1372)
    legacy=runtime3.predict_maps(maps,prior,[0,1,2],index)
    assert legacy['score']==legacy['component_scores']['gru']
    import copy
    local_state=copy.deepcopy(state)
    for name in ('safe','laptop'):
        local_state[name].update(anchors=torch.zeros(1,1372),boxes=local_state[name]['bias'][None],distance_weight=torch.ones(1372))
    local_state['bag_presence']={'normalization':{'mean':torch.zeros(19),'scale':torch.ones(19)},'weight':torch.zeros(19),'bias':torch.zeros(()),'supported':True}
    local_state['door_state']={'normalization':{'mean':torch.zeros(10588),'scale':torch.ones(10588)},'weight':torch.zeros(10588),'bias':torch.zeros(()),'supported':True}
    local_payload={**payload,'roi_state':local_state};atomic_checkpoint(tmp_path/'weights.pt',local_payload)
    extension={**extension,'pipeline_version':inference.consensus.VERSION,'training_code_sha256':inference.local.code_hash(),
               'ensemble_code_sha256':inference.consensus.code_hash(),'candidate':{'name':'policy_blend_base','arm':'policy_blend','hard':False,'alpha':1.}}
    local_metadata={**combined,'weights_sha256':file_sha256(tmp_path/'weights.pt'),'tensor_bytes':base.tensor_bytes(local_payload),'weights_file_bytes':(tmp_path/'weights.pt').stat().st_size,'roi_extension':extension}
    atomic_json(tmp_path/'bundle.json',local_metadata);runtime4=inference.Predictor(tmp_path,'cpu');runtime4._colors=torch.zeros(3,1372)
    local_result=runtime4.predict_maps(maps,prior,[0,1,2],index)
    assert local_result['rule_probes'][0]['probe']=='visible_bag_after_departure'
    assert set(local_result['rule_template_status'].values())=={'unknown'}
    runtime4.state['bag_presence']['supported']=False;runtime4._colors=torch.zeros(3,1372)
    assert runtime4.predict_maps(maps,prior,[0,1,2],index)['frames'][0]['state_scores']['green_bag_visible'] is None
    transition_extension={**extension,'pipeline_version':inference.transitions.VERSION,'ensemble_code_sha256':inference.transitions.code_hash(),
                          'candidate':{'name':'transition','arm':'transition','hard':False,'alpha':1.}}
    atomic_json(tmp_path/'bundle.json',{**local_metadata,'roi_extension':transition_extension})
    runtime5=inference.Predictor(tmp_path,'cpu');runtime5._colors=torch.zeros(3,1372);stationary=runtime5.predict_maps(maps,prior,[0,1,2],index)
    assert stationary['score']==0 and stationary['rule_probes'][0]['probe']=='bag_after_observed_departure'
    transition_extension['candidate']={'name':'transition_blend','arm':'transition_blend','hard':False,'alpha':1.}
    atomic_json(tmp_path/'bundle.json',{**local_metadata,'roi_extension':transition_extension})
    runtime6=inference.Predictor(tmp_path,'cpu');runtime6._colors=torch.zeros(3,1372);blended=runtime6.predict_maps(maps,prior,[0,1,2],index)
    assert blended['score']==pytest.approx(.5*blended['component_scores']['gru'])
    atomic_checkpoint(tmp_path/'weights.pt',payload);metadata={**metadata,'weights_sha256':file_sha256(tmp_path/'weights.pt'),'weights_file_bytes':(tmp_path/'weights.pt').stat().st_size}
    bad={**metadata,'roi_extension':{**metadata['roi_extension'],'inference_code_sha256':'f'*64}}
    atomic_json(tmp_path/'bundle.json',bad)
    with pytest.raises(ValueError,match='ROI extension'):inference.Predictor(tmp_path,'cpu')
    atomic_json(tmp_path/'bundle.json',metadata)
    with (tmp_path/'weights.pt').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='SHA-256'):inference.Predictor(tmp_path,'cpu')


def test_compact_export_copies_tensor_views_without_serializing_unused_storage():
    backing=torch.arange(4000,dtype=torch.float32).reshape(200,20);view=backing[:,3]
    assert view.untyped_storage().nbytes()>view.numel()*view.element_size()
    compact=inference.compact_state({'head':view,'bias':backing[0,3],'support':torch.tensor([True]),'provenance':False})
    torch.testing.assert_close(compact['head'],view)
    assert compact['head'].untyped_storage().nbytes()==view.numel()*view.element_size()
    assert compact['bias'].untyped_storage().nbytes()==4 and compact['provenance'] is False
