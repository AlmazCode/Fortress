import copy
import numpy as np
import pytest
import torch
from ml import boundary_roi_infer as inference
from ml.models.encoder import file_sha256
from ml.video_baseline import atomic_checkpoint


def test_portable_magnified_states_without_dataset_and_source_buffers_are_consumed(tmp_path,monkeypatch):
    torch.set_num_threads(2)
    heads=[{'normalization':{'mean':torch.zeros(d),'scale':torch.ones(d)},'weight':torch.zeros(d),'bias':torch.zeros(()),'supported':True} for d in (1920,19,989,989)]
    heads[2]['supported']=False
    readout={'weight':torch.zeros(52),'bias':torch.zeros(()),'normalization':{'mean':torch.zeros(52),'scale':torch.ones(52)}}
    atomic_checkpoint(tmp_path/'weights.pt',{'magnified_boundary_state':{'heads':heads,'readout':readout}})
    ext={'version':inference.VERSION,'training_code_sha256':inference.training.code_hash(),'input_code_sha256':inference.data.code_hash(),
         'inference_code_sha256':inference.code_hash(),'physical_code_sha256':inference.physical.code_hash(),
         'taxonomy':list(inference.training.parent.data.TAXONOMY),'regions':[list(r) for r in inference.data.REGIONS],
         'arm':'roi_blend','recognizers_validated':False,'human_approved':False}
    metadata={'weights_sha256':file_sha256(tmp_path/'weights.pt'),'protocol_sha256':'a'*64,'magnified_boundary_extension':ext}
    class Context(torch.nn.Module):
        state_support=torch.ones(18,dtype=torch.bool)
        def forward(self,x):return None,None,torch.zeros(len(x),18)
    def initialize(self,bundle,device):self.device=device;self.metadata=copy.deepcopy(metadata);self.context=Context()
    def parent_maps(self,maps,priors,points,index,return_features=False):
        self._colors=None
        return {'frames':[{} for _ in points],'component_scores':{'gru':.4},'rule_template_status':{'rule':'unknown'},'production_ready':False}
    monkeypatch.setattr(inference.base.Predictor,'__init__',initialize);monkeypatch.setattr(inference.base.Predictor,'predict_maps',parent_maps)
    runtime=inference.Predictor(tmp_path,'cpu');runtime._colors=torch.zeros(4,1372);runtime._magnified_crops=torch.zeros(4,2,960)
    maps=np.zeros((4,576,14,14),np.float16);prior=np.zeros((4,14,14),np.float32);points=list(range(4));index={'frames':[{'source_pts':n,'timestamp_sec':n*.5} for n in points]}
    result=runtime.predict_maps(maps,prior,points,index,True)
    assert result['score']==pytest.approx(.45) and result['features'].shape==(4,1949)
    assert result['frames'][0]['boundary_state_scores']['bag_held_or_manipulated'] is None
    assert result['rule_template_status']=={'rule':'unknown'} and result['boundary_events_are_normative_findings'] is False
    with pytest.raises(ValueError,match='source-bound'):runtime.predict_maps(maps,prior,points,index)
    ext['regions'][0][0]=.1
    with pytest.raises(ValueError,match='magnified extension'):inference.Predictor(tmp_path,'cpu')
