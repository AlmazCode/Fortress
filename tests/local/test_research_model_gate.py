import json
import pytest
from backend.local.inference import predictor,model_limitations
from ml.temporal_risk_infer import enabled


def test_regressing_joint_operation_model_cannot_be_accidentally_selected_for_jury_api(tmp_path):
    (tmp_path/'bundle.json').write_text(json.dumps({'version':'temporal-operations-local-bundle-v1','clip_promoted':False}))
    with pytest.raises(ValueError,match='not deployable'):predictor(tmp_path,'cpu')


def test_risk_package_with_both_quality_gates_closed_is_research_only(tmp_path):
    (tmp_path/'bundle.json').write_text(json.dumps({'risk_extension':{'clip_enabled':False,'localizer_enabled':False}}))
    with pytest.raises(ValueError,match='deployment gates'):predictor(tmp_path,'cpu')


def test_weak_risk_promotion_requires_the_fixed_clip_and_localization_checks():
    baseline={str(s):{'accuracy':.7,'balanced_accuracy':.7,'macro_f1':.7} for s in [42,137,2026]}
    report={'promoted':False,'nested_mean':{'accuracy':.8,'balanced_accuracy':.8,'macro_f1':.8},
            'comparisons':{'base_control':baseline},'localization':{'positive_videos_with_intervals':20,'peak_in_weak_interval':11,'weak_frame_f1':.7}}
    assert enabled(report)==(False,False)
    report['promoted']=True;report['localization']['peak_in_weak_interval']=15
    assert enabled(report)==(True,True)
    report['nested_mean']['balanced_accuracy']=.6
    assert enabled(report)==(False,True)


def test_model_limitations_take_accuracy_from_the_bound_model_evaluation():
    assert '71.30%' in model_limitations({})[0]
    assert '75.00%' in model_limitations({'clip_metrics':{'accuracy':.75}})[0]
    with pytest.raises(ValueError):model_limitations({'clip_metrics':{'accuracy':float('nan')}})
