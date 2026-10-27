import pytest
from integrations.elmtree_gateway_v20 import send_to_elmtree,IntegrationNotAuthorized,export_review_packet

def test_elmtree_write_disabled():
    with pytest.raises(IntegrationNotAuthorized):send_to_elmtree({'secret':'never'})

def test_review_packet_never_claims_elmtree_import():
    r=export_review_packet([{'x':1}]);assert r['mode']=='REVIEW_ONLY' and r['destination']=='NO_CONNECTED_DESTINATION'

def test_enforce_max_record_count():
    with pytest.raises(ValueError):export_review_packet([{}]*1001)
