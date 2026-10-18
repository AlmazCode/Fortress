import math
import numpy as np
import pytest
import torch
from ml import object_events_infer as inference
from ml.models.encoder import FrozenEncoder,file_sha256
from ml.video_baseline import atomic_checkpoint,atomic_json


def test_box_coordinates_roundtrip_to_displayed_source():
    index={'width':464,'height':848,'rotation':0}
    roi=inference.data.box_to_roi([100,300,90,100],464,848)
    box=[(roi[0]+roi[2])/2,(roi[1]+roi[3])/2,roi[2]-roi[0],roi[3]-roi[1]]
    result=inference.displayed_box(box,index)
    assert result==pytest.approx([100,300,190,400])


def test_portable_spatial_bundle_runs_without_dataset_and_rejects_changed_weights(tmp_path):
    torch.set_num_threads(2);encoder=FrozenEncoder(test_only=True);spatial=inference.training.SpatialHeads();spatial.state_support[15]=False
    classifier=torch.nn.Sequential(torch.nn.Linear(576,512),torch.nn.Hardswish(),torch.nn.Linear(512,1000))
    temporal=inference.training.Temporal();rule=torch.nn.Linear(24,1)
    state={'format':inference.VERSION,'encoder':dict(encoder.features.state_dict()),'cup_classifier':dict(classifier.state_dict()),
           'spatial':dict(spatial.state_dict()),'temporal':dict(temporal.state_dict()),
           'normalization':{'mean':torch.zeros(646),'std':torch.ones(646)},'cup_calibration':torch.tensor([math.log(1e-6),.25]),
           'rule_head':dict(rule.state_dict()),'rule_mean':torch.zeros(24),'rule_std':torch.ones(24)}
    assert inference.tensor_bytes(state)<12*1024**2
    atomic_checkpoint(tmp_path/'weights.pt',state)
    metadata={'version':inference.VERSION,'training_code_sha256':inference.training.code_hash(),'inference_code_sha256':inference.code_hash(),
      'input_version':inference.data.VERSION,'size':448,'rate':2.,'variants':list(inference.data.VARIANTS),'roi':list(inference.data.base.ROI),
      'taxonomy':list(inference.data.TAXONOMY),'objects':list(inference.data.OBJECTS),'arm':'hybrid_fixed','mode':'objects',
      'production_ready':False,'threshold':.5,'cup_classes':['coffee mug','cup'],'weights_sha256':file_sha256(tmp_path/'weights.pt')}
    atomic_json(tmp_path/'bundle.json',metadata)
    runtime=inference.Predictor(tmp_path,'cpu')
    maps=np.ones((3,576,14,14),dtype=np.float16);prior=np.zeros((3,14,14),dtype=np.float32)
    index={'video_id':'synthetic','width':464,'height':848,'rotation':0,'frames':[{'source_pts':i,'timestamp_sec':i/2} for i in range(3)]}
    result=runtime.predict_maps(maps,prior,[0,1,2],index,True)
    assert 0<=result['score']<=1 and result['features'].shape==(3,646)
    assert result['frames'][0]['state_scores']['cup_visible'] is None
    assert result['normative_status']=='unknown' and set(result['rule_template_status'].values())=={'unknown'}
    assert all(set(e['source_pts'])<={0,1,2} for e in result['candidate_events'])
    with pytest.raises(ValueError,match='source-bound'):runtime.predict_maps(maps,prior,[0,1,3],index)
    from ml.object_rules import code_hash as calibration_hash
    corrected_state={**state,'log_weight_correction':torch.full((18,),math.log(2.))}
    atomic_checkpoint(tmp_path/'weights.pt',corrected_state)
    corrected_metadata={**metadata,'weights_sha256':file_sha256(tmp_path/'weights.pt'),
                        'calibration_code_sha256':calibration_hash(),'selection_arm':'posterior_hybrid_fixed'}
    atomic_json(tmp_path/'bundle.json',corrected_metadata)
    corrected=inference.Predictor(tmp_path,'cpu').predict_maps(maps,prior,[0,1,2],index,True)
    np.testing.assert_array_equal(corrected['features'],result['features'])
    assert corrected['component_scores']['gru']==pytest.approx(result['component_scores']['gru'])
    assert corrected['frames'][0]['state_scores']['flat_item_handling']<result['frames'][0]['state_scores']['flat_item_handling']
    assert corrected['frames'][0]['state_scores']['cup_visible'] is None
    assert corrected['selected_arm']=='posterior_hybrid_fixed' and corrected['rule_probability_correction'] is True
    atomic_checkpoint(tmp_path/'weights.pt',state)
    metadata={**metadata,'weights_sha256':file_sha256(tmp_path/'weights.pt')}
    import json
    (tmp_path/'bundle.json').write_text(json.dumps({**metadata,'threshold':float('nan')}),encoding='utf-8')
    with pytest.raises(ValueError,match='unsupported spatial bundle'):inference.Predictor(tmp_path,'cpu')
    atomic_json(tmp_path/'bundle.json',metadata)
    with (tmp_path/'weights.pt').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='SHA-256 mismatch'):inference.Predictor(tmp_path,'cpu')
