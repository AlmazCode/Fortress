import copy
import numpy as np
import pytest
import torch
from ml import boundary_infer as inference
from ml.models.encoder import file_sha256
from ml.video_baseline import atomic_checkpoint


def state():
    net=inference.training.BoundaryNet();dim=52
    return {'model':net.state_dict(),'normalization':{'mean':torch.zeros(3503),'scale':torch.ones(3503)},
            'support':torch.tensor([True,True,False,True,True,True]),
            'readout':{'weight':torch.zeros(dim),'bias':torch.zeros(()),'normalization':{'mean':torch.zeros(dim),'scale':torch.ones(dim)}}}


def metadata(path):
    return {'weights_sha256':file_sha256(path),'protocol_sha256':'a'*64,
            'boundary_extension':{'version':inference.VERSION,'training_code_sha256':inference.training.code_hash(),
                                  'input_code_sha256':inference.data.code_hash(),'inference_code_sha256':inference.code_hash(),
                                  'taxonomy':list(inference.data.TAXONOMY),'dimension':3503,'arm':'boundary_ridge_blend',
                                  'human_approved':False,'recognizers_validated':False}}


def test_dataset_free_boundary_loader_real_head_and_source_feature_adapter(tmp_path,monkeypatch):
    torch.set_num_threads(2);s=state();atomic_checkpoint(tmp_path/'weights.pt',{'boundary_state':s});m=metadata(tmp_path/'weights.pt')
    def initialize(self,bundle,device):self.device=device;self.metadata=copy.deepcopy(m)
    def parent_maps(self,maps,priors,points,index,return_features=False):
        self._colors=None
        return {'frames':[{} for _ in points],'component_scores':{'gru':.4},'rule_template_status':{'rule':'unknown'},'production_ready':False}
    monkeypatch.setattr(inference.base.Predictor,'__init__',initialize);monkeypatch.setattr(inference.base.Predictor,'predict_maps',parent_maps)
    runtime=inference.Predictor(tmp_path,'cpu');maps=np.ones((4,576,14,14),np.float16);prior=np.zeros((4,14,14),np.float32)
    runtime._colors=torch.zeros(4,1372);index={'frames':[{'source_pts':n,'timestamp_sec':n*.5} for n in range(4)]}
    result=runtime.predict_maps(maps,prior,list(range(4)),index,True)
    assert result['score']==pytest.approx(.45) and result['selected_arm']=='boundary_ridge_blend'
    assert result['features'].shape==(4,3503) and result['source_pts']==list(range(4))
    assert all(f['boundary_state_scores']['bag_held_or_manipulated'] is None for f in result['frames'])
    assert result['production_ready'] is False and result['rule_template_status']=={'rule':'unknown'}
    assert result['boundary_events_are_normative_findings'] is False
    with pytest.raises(ValueError,match='source-bound'):runtime.predict_maps(maps,prior,list(range(4)),index)
    m['boundary_extension']['inference_code_sha256']='f'*64
    with pytest.raises(ValueError,match='boundary extension'):inference.Predictor(tmp_path,'cpu')


def test_all_fixed_arms_and_nonfinite_scores():
    expected=(.2,.6,.5,.7,.8)
    for arm,value in zip(inference.training.ARMS,expected):assert inference.select_score(arm,.2,.6,.8)==pytest.approx(value)
    with pytest.raises(ValueError):inference.select_score('boundary_tcn',float('nan'),.2,.3)


def test_constant_uncertainty_cannot_be_departure_or_unattended_bag():
    p=torch.ones(10,6)*.5;p[:,1]=p[:,3]=.99;points=list(range(10));timing={n:n*.5 for n in points};support=torch.ones(6,dtype=torch.bool)
    assert inference.bag_remains(p,support,points,timing)==[]
    p[:3,4]=.99;p[3:,4]=.01;events=inference.bag_remains(p,support,points,timing)
    assert len(events)==1 and events[0]['start_sec']==1.5 and events[0]['normative_status']=='unknown'
    support[3]=False;assert inference.bag_remains(p,support,points,timing)==[]


def test_boundary_state_fits_remaining_model_budget():
    s=state();compacted=inference.base.compact_state(s)
    assert inference.base.base.tensor_bytes(compacted)<600_000
    assert 11_243_478+inference.base.base.tensor_bytes(compacted)+50_000<inference.base.MAX_BYTES
