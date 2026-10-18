import json
import pytest
from ml.vlm_operations import parse_response, classify


def test_response_is_bound_to_real_input_ordinals():
    rows={'frames':[{'index':1,'action':'other'},{'index':0,'action':'bag_handling'}]}
    assert parse_response(json.dumps(rows),2)==['bag_handling','other']
    for change in [ {'frames':[{'index':1,'action':'other'}]},
                    {'frames':[{'index':0,'action':'other'},{'index':0,'action':'other'}]},
                    {'frames':[{'index':0,'action':'verified_identity'},{'index':1,'action':'other'}]},
                    {'frames':[{'index':0,'action':'other','timestamp':22},{'index':1,'action':'other'}]} ]:
        with pytest.raises(ValueError):parse_response(json.dumps(change),2)


def test_external_endpoint_is_rejected_before_request():
    with pytest.raises(ValueError,match='loopback'):classify([b'fake'],endpoint='https://example.com')
