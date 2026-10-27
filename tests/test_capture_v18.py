"""Synthetic-only regression coverage for v1.8 field-by-field capture staging."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from forms.capture_v18 import stage, DICT, VERSION

BASE=Path(__file__).resolve().parents[1]/'forms/examples'

def sample(pending=False):
    suffix='PENDING' if pending else 'REVIEWED'
    return json.loads((BASE/f'SYNTHETIC_CAPTURE_{suffix}_V18.json').read_text(encoding='utf-8'))

def codes(r): return {i['code'] for i in r['issues']}

def first(d): return d['documents'][0]['fields'][0]

def doc(d,kind): return next(x for x in d['documents'] if x['form_type']==kind)


def test_fully_reviewed_candidates_screen_but_never_approve_material():
    r=stage(sample());assert r['ready_for_screening'];assert r['screening']
    assert not r['screening']['automated_material_acceptance']
    assert not r['screening']['ready_for_elmtree_import']
    assert r['summary']['captured']==r['summary']['reviewed']
    assert {'DRY_DENSITY_RECHECK','COMPACTION_RECHECK'} <= {i['code'] for i in r['screening']['findings']}

def test_pending_value_blocks_before_engine():
    r=stage(sample(pending=True));assert not r['ready_for_screening']
    assert r['screening'] is None and 'FIELD_NEEDS_HUMAN_REVIEW' in codes(r)
    assert r['summary']['low_confidence']==1

def test_pending_reviewer_ref_without_checked_not_enough():
    d=sample(pending=True);f=doc(d,'density_sheet')['fields'][0];f['reviewed']=False;f['reviewer_ref']='SYN-REVIEWER'
    assert 'FIELD_NEEDS_HUMAN_REVIEW' in codes(stage(d))

def test_missing_reviewer_reference_blocks():
    d=sample();first(d)['reviewer_ref']='';assert 'FIELD_NEEDS_HUMAN_REVIEW' in codes(stage(d))

def test_invalid_confidence_blocks():
    for val in [True,-0.1,1.2,'high',float('nan'),float('inf')]:
        d=sample();first(d)['confidence']=val
        assert 'CONFIDENCE_INVALID' in codes(stage(d))

def test_missing_confidence_permitted_when_human_checked():
    d=sample();first(d).pop('confidence');assert stage(d)['ready_for_screening']

def test_missing_evidence_ref_blocks():
    d=sample();first(d)['evidence_ref']='';assert 'EVIDENCE_REF_REQUIRED' in codes(stage(d))

def test_missing_origin_blocks():
    d=sample();first(d).pop('origin');assert 'ORIGIN_REQUIRED' in codes(stage(d))

def test_duplicate_source_rejected():
    d=sample();d['documents'][1]['source_id']=d['documents'][0]['source_id'];assert 'DUPLICATE_SOURCE_ID' in codes(stage(d))

def test_duplicate_field_rejected():
    d=sample();d['documents'][0]['fields'].append(deepcopy(first(d)))
    assert 'DUPLICATE_FIELD' in codes(stage(d))

def test_unrecognized_field_rejected():
    d=sample();first(d)['key']='super_sensitive_client_secret'
    assert 'UNKNOWN_FIELD' in codes(stage(d))

def test_missing_necessary_header_blocks():
    d=sample();d['documents'][0]['fields']=[x for x in d['documents'][0]['fields'] if x['key']!='project_key']
    assert 'REQUIRED_FIELD_MISSING' in codes(stage(d))

def test_packet_project_mismatch_blocks():
    d=sample();first(d)['value']='OTHER-PROJECT'
    assert 'PROJECT_KEY_MISMATCH' in codes(stage(d))

def test_bad_work_date_blocks():
    d=sample();d['work_date']='not-a-date'
    with pytest.raises(ValueError):stage(d)

def test_bad_project_date_in_form_blocks():
    d=sample();next(x for x in d['documents'][0]['fields'] if x['key']=='work_date')['value']='2026-11-11'
    assert 'WORK_DATE_MISMATCH' in codes(stage(d))

def test_non_numeric_moisture_blocks():
    d=sample();field=next(x for x in doc(d,'density_sheet')['rows'][0]['fields'] if x['key']=='field_moisture_percent');field['value']='N/A'
    assert 'VALUE_INVALID' in codes(stage(d))

def test_negative_count_blocks():
    d=sample();f=next(x for x in d['documents'][0]['fields'] if x['key']=='reported_density_tests');f['value']='-4'
    assert 'VALUE_INVALID' in codes(stage(d))

def test_blank_missing_row_required_blocks():
    d=sample();den=doc(d,'density_sheet'); den['rows'][0]['fields']=[x for x in den['rows'][0]['fields'] if x['key']!='max_dry_density_pcf']
    assert 'REQUIRED_ROW_FIELD_MISSING' in codes(stage(d))

def test_duplicate_row_ids_block():
    d=sample();den=doc(d,'density_sheet');den['rows'][1]['row_id']=den['rows'][0]['row_id']
    assert 'ROW_ID_MISSING_OR_DUPLICATE' in codes(stage(d))

def test_density_missing_page_after_review_blocks_in_engine():
    d=sample();d['documents']=[x for x in d['documents'] if x['source_id']!='DEMO-DENSITY-P2'];r=stage(d)
    assert r['ready_for_screening'];assert 'MISSING_DENSITY_PAGES' in {i['code'] for i in r['screening']['findings']}

def test_authorized_requires_attestation():
    d=sample();d['data_mode']='authorized';assert d.get('authorization_attested') is False
    with pytest.raises(ValueError):stage(d)

def test_unknown_schema_fails():
    d=sample();d['schema']='v0'
    with pytest.raises(ValueError):stage(d)

def test_limit_on_number_of_fields():
    d=sample();d['documents'][0]['fields']=d['documents'][0]['fields']*1200
    with pytest.raises(ValueError):stage(d)

def test_excessively_long_handwritten_field_text_rejected():
    d=sample();first(d)['value']='X'*221
    assert 'VALUE_INVALID' in codes(stage(d))

def test_form_dictionary_has_required_four_types():
    assert set(DICT['forms'])=={'general_report','concrete_strength','density_sheet','rebar_observation'}
    assert VERSION=='cmt-capture-v1.8'


def test_legacy_ai_adapter_creates_only_unreviewed_draft():
    from forms.legacy_ai_adapter_v18 import adapt
    raw={'document_type':'soil','fields':[{'key':'wet_density','value':'125.4'},{'key':'moisture','value':'12'}]}
    d=adapt(raw,form_type='density_sheet',source_id='SYN-P1',project_key='SYN-PROJECT',work_date='2026-10-20')
    assert all(not f['reviewed'] for f in d['documents'][0]['fields'])
    assert all(not f['reviewed'] for r in d['documents'][0]['rows'] for f in r['fields'])
    assert stage(d)['screening'] is None


def test_legacy_ai_adapter_rejects_duplicate_mapped_field():
    from forms.legacy_ai_adapter_v18 import adapt
    raw={'fields':[{'key':'air','value':'5'},{'key':'air','value':'6'}]}
    with pytest.raises(ValueError):adapt(raw,form_type='concrete_strength',source_id='SYN-C',project_key='SYN',work_date='2026-10-20')


def test_legacy_ai_adapter_rejects_unauthorized_real_mode():
    from forms.legacy_ai_adapter_v18 import adapt
    with pytest.raises(ValueError):adapt({'fields':[]},form_type='density_sheet',source_id='SYN-D',project_key='SYN',work_date='2026-10-20',data_mode='authorized')


def test_huge_page_count_rejected_before_page_scan():
    d=sample();f=next(x for x in doc(d,'density_sheet')['fields'] if x['key']=='page_count')
    f['value']='99999999999'
    assert 'VALUE_INVALID' in codes(stage(d))

def test_out_of_range_page_number_rejected():
    d=sample();f=next(x for x in doc(d,'density_sheet')['fields'] if x['key']=='page_number')
    f['value']='251'
    assert 'VALUE_INVALID' in codes(stage(d))
