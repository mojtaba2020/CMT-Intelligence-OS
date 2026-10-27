"""v1.5 deterministic unit/identity/measurement reconciliation tests, no AI or network."""
import copy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from server.app import app
from server.reconcile_v15 import Case, reconcile

ROOT = Path(__file__).resolve().parents[1] / 'examples' / 'v15'

def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def test_ndg_detects_wet_density_difference():
    report = reconcile(Case.model_validate(load('ndg_synthetic_conflict.json')))
    assert report['review_status'] == 'REVIEW_REQUIRED'
    assert report['official_acceptance'] is None and not report['engineer_approved']
    assert report['synthetic'] is True
    assert any(x['code']=='VALUE_MISMATCH' and x['field']=='wet_density' for x in report['issues'])
    assert len(report['derived']) == 2
    assert report['derived'][0]['derived_dry_density_pcf'] == '114.2857'
    assert report['derived'][1]['derived_dry_density_pcf'] == '111.6071'


def test_concrete_normalizes_inch_mm_f_c_and_agrees():
    r = reconcile(Case.model_validate(load('concrete_synthetic_metric.json')))
    assert r['review_status'] == 'NO_DIFFERENCE_IN_CHECKED_FIELDS'
    assert [row['base_unit'] for row in r['comparisons']] == ['in', '%', 'F']
    assert all(not item['different'] for item in r['comparisons'])
    assert not r['engineer_approved']


def test_identity_mismatch_always_requires_review():
    r = reconcile(Case.model_validate(load('ndg_synthetic_identity_conflict.json')))
    assert r['review_status'] == 'REVIEW_REQUIRED'
    assert {i['field'] for i in r['issues'] if i['code']=='IDENTIFIER_MISMATCH'} == {'test_id','project_id'}


def test_missing_required_field_blocks_clean_report():
    case = load('ndg_synthetic_conflict.json')
    case['documents'][1]['observations'] = case['documents'][1]['observations'][:1]
    r = reconcile(Case.model_validate(case))
    assert any(i['code']=='MISSING_MEASUREMENT' and i['field']=='moisture' for i in r['issues'])


def test_duplicate_key_rejected():
    case = load('ndg_synthetic_conflict.json')
    case['documents'][0]['observations'].append(copy.deepcopy(case['documents'][0]['observations'][0]))
    with pytest.raises(ValidationError): Case.model_validate(case)


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '1e100', 'x', '', '1,24'])
def test_invalid_numeric_rejected(value):
    case = load('ndg_synthetic_conflict.json')
    case['documents'][0]['observations'][0]['value']=value
    with pytest.raises(ValidationError): Case.model_validate(case)


def test_ambiguous_or_unsupported_density_unit_rejected():
    case = load('ndg_synthetic_conflict.json')
    case['documents'][1]['observations'][0]['unit']='g/cc'
    with pytest.raises(ValidationError): Case.model_validate(case)


def test_negative_density_rejected():
    case = load('ndg_synthetic_conflict.json')
    case['documents'][0]['observations'][0]['value']='-2'
    with pytest.raises(ValidationError): Case.model_validate(case)


def test_wrong_evidence_pair_rejected():
    case = load('ndg_synthetic_conflict.json')
    case['documents'][1]['source_type']='concrete_ticket'
    with pytest.raises(ValidationError): Case.model_validate(case)


def test_reused_source_id_rejected():
    case=load('ndg_synthetic_conflict.json')
    case['documents'][1]['source_id'] = case['documents'][0]['source_id']
    with pytest.raises(ValidationError): Case.model_validate(case)


def test_explicit_screen_tolerance_changes_only_diff_flag():
    case=load('ndg_synthetic_conflict.json')
    case['screen_tolerances']['wet_density']='3.01'
    r=reconcile(Case.model_validate(case))
    assert not r['comparisons'][0]['different']
    assert not r['issues']
    assert r['official_acceptance'] is None


def test_negative_tolerance_rejected():
    case=load('ndg_synthetic_conflict.json')
    case['screen_tolerances']['wet_density']='-1'
    with pytest.raises(ValidationError): Case.model_validate(case)


def test_internal_dry_density_formula_conflict():
    case=load('ndg_synthetic_conflict.json')
    case['documents'][0]['observations'].append({'field':'dry_density','value':'90','unit':'pcf'})
    r=reconcile(Case.model_validate(case))
    assert any(i['code']=='INTERNAL_CALCULATION_MISMATCH' for i in r['issues'])


def test_consistent_result_has_no_formal_approval():
    case=load('ndg_synthetic_conflict.json')
    case['documents'][1]['observations'][0]['value']='128'
    r=reconcile(Case.model_validate(case))
    assert r['review_status']=='NO_DIFFERENCE_IN_CHECKED_FIELDS'
    assert r['engineer_approved'] is False and r['official_acceptance'] is None


def test_digest_deterministic_and_content_sensitive():
    case=load('ndg_synthetic_conflict.json')
    h1=reconcile(Case.model_validate(case))['sha256_for_local_change_detection_only']
    h2=reconcile(Case.model_validate(case))['sha256_for_local_change_detection_only']
    case['documents'][1]['observations'][0]['value']='124'
    h3=reconcile(Case.model_validate(case))['sha256_for_local_change_detection_only']
    assert h1==h2 and h1!=h3


def test_api_valid_reconciliation_and_cache_control():
    c=TestClient(app)
    response=c.post('/api/evidence/reconcile',json=load('ndg_synthetic_conflict.json'))
    assert response.status_code == 200
    assert response.json()['review_status']=='REVIEW_REQUIRED'
    assert response.headers['cache-control']=='no-store'


def test_api_rejects_untrusted_host():
    c=TestClient(app,base_url='http://untrusted.example')
    response=c.post('/api/evidence/reconcile',json=load('ndg_synthetic_conflict.json'))
    assert response.status_code==403


def test_api_rejects_unsanctioned_fields():
    case=load('ndg_synthetic_conflict.json')
    case['engineer_approved']=True
    response=TestClient(app).post('/api/evidence/reconcile',json=case)
    assert response.status_code==422


def test_api_rejects_missing_origin_classification():
    case=load('ndg_synthetic_conflict.json')
    del case['synthetic']
    response=TestClient(app).post('/api/evidence/reconcile',json=case)
    assert response.status_code==422


def test_api_rejects_cross_origin():
    response=TestClient(app).post('/api/evidence/reconcile',json=load('ndg_synthetic_conflict.json'),headers={'Origin':'https://evil.example'})
    assert response.status_code==403


def test_unexpected_field_is_rejected():
    case=load('ndg_synthetic_conflict.json')
    case['documents'][0]['observations'].append({'field':'temperature','value':'72','unit':'F'})
    with pytest.raises(ValidationError):Case.model_validate(case)


def test_concrete_detects_air_difference():
    case=load('concrete_synthetic_metric.json')
    case['documents'][1]['observations'][1]['value']='4.6'
    report=reconcile(Case.model_validate(case))
    assert any(x['field']=='air' and x['code']=='VALUE_MISMATCH' for x in report['issues'])


def test_demo_endpoint_displays_synthetic_disclaimer():
    r=TestClient(app).get('/reconcile-demo')
    assert r.status_code==200
    assert b'SYNTHETIC DEMO' in r.content
    assert b'NO LIVE ELMTREE CONNECTION' in r.content
