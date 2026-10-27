"""Synthetic-only cross-document regression checks for photographed form *structures*."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from forms.form_engine import inspect_packet, render_review_html

EXAMPLE=Path(__file__).resolve().parents[1]/'forms/examples/SYNTHETIC_PACKET.json'


def data():
    return json.loads(EXAMPLE.read_text(encoding='utf8'))


def codes(result):
    return {f['code'] for f in result['findings']}


def test_synthetic_human_verified_packet_flags_intentional_density_mismatch():
    r=inspect_packet(data())
    assert r['forms_count']==5 and r['density_detail_rows']==3
    assert 'DRY_DENSITY_RECHECK' in codes(r)
    assert 'COMPACTION_RECHECK' in codes(r)
    assert not r['automated_material_acceptance']
    assert not r['ready_for_elmtree_import']


def test_missing_page_blocks():
    d=data();d['forms'].pop(3)
    assert 'MISSING_DENSITY_PAGES' in codes(inspect_packet(d))


def test_duplicate_page_blocks():
    d=data();d['forms'][3]['page_number']=1
    assert 'DUPLICATE_PAGE' in codes(inspect_packet(d))


def test_inconsistent_page_count_blocks():
    d=data();d['forms'][3]['page_count']=3
    assert 'PAGE_TOTAL_INCONSISTENT' in codes(inspect_packet(d))


def test_duplicate_test_id_blocks():
    d=data();d['forms'][3]['rows'][0]['test_id']='D-001'
    assert 'DUPLICATE_TEST_ID' in codes(inspect_packet(d))


def test_wrong_project_blocks():
    d=data();d['forms'][2]['project_key']='DIFFERENT'
    assert 'PROJECT_ID_MISMATCH' in codes(inspect_packet(d))


def test_different_date_flags():
    d=data();d['forms'][2]['work_date']='2026-10-21'
    assert 'WORK_DATE_MISMATCH' in codes(inspect_packet(d))


def test_review_required_without_human_validation():
    d=data();d['forms'][0]['human_verified']=False
    assert 'HUMAN_VERIFICATION_REQUIRED' in codes(inspect_packet(d))


def test_count_discrepancy_found():
    d=data();d['forms'][0]['reported_density_tests']=7
    assert 'DENSITY_COUNT_RECHECK' in codes(inspect_packet(d))


def test_cylinder_discrepancy_found():
    d=data();d['forms'][0]['reported_concrete_cylinders_cast']=8
    assert 'CYLINDER_COUNT_RECHECK' in codes(inspect_packet(d))


def test_bad_moisture_value_blocks():
    d=data();d['forms'][2]['rows'][0]['field_moisture_percent']=-99
    assert 'DENSITY_MISSING_OR_INVALID' in codes(inspect_packet(d))


def test_nan_not_accepted():
    d=data();d['forms'][2]['rows'][0]['field_wet_density_pcf']=float('nan')
    assert 'DENSITY_MISSING_OR_INVALID' in codes(inspect_packet(d))


def test_missing_test_id_blocks():
    d=data();del d['forms'][2]['rows'][0]['test_id']
    assert 'TEST_ID_MISSING' in codes(inspect_packet(d))


def test_html_escapes_injected_text():
    d=data();d['forms'][0]['form_id']='<script>alert(1)</script>';d['forms'][0]['project_key']='wrong'
    html=render_review_html(inspect_packet(d))
    assert '<script>' not in html
    assert '&lt;script&gt;' in html


def test_unknown_form_type_blocks():
    d=data();d['forms'][0]['form_type']='mystery'
    assert 'UNKNOWN_FORM_TYPE' in codes(inspect_packet(d))


def test_no_forms_is_not_approved():
    d={'forms':[]}
    r=inspect_packet(d)
    assert r['review_required'] and not r['ready_for_elmtree_import']


def test_non_array_packet_fails_closed():
    with pytest.raises(ValueError): inspect_packet({'forms':{}})


def test_bool_is_not_numeric():
    d=data();d['forms'][2]['rows'][0]['field_moisture_percent']=True
    assert 'DENSITY_MISSING_OR_INVALID' in codes(inspect_packet(d))
