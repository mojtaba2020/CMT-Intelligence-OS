"""Vendor-neutral bridge: operational behavior, input hardening and no implied vendor API."""
import csv
import json
from io import BytesIO
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from server import pilot
from server.app import app
from bridge.core import export_csv, reconciliation, validate_mapping, parse_export_csv, SAFE_COL, mapped_rows

HERE=Path(__file__).resolve().parents[1]/'bridge'/'examples'

def fixture():
    records=json.loads((HERE/'SYNTHETIC_CMT_RECORDS.json').read_text())
    mapping=json.loads((HERE/'SYNTHETIC_OPERATOR_PROFILE.json').read_text())
    return records,mapping

def test_profile_explicitly_unverified():
    _,p=fixture();assert validate_mapping(p)
    p['vendor_import_verified']=True
    with pytest.raises(ValueError,match='NOT verified'):validate_mapping(p)

def test_duplicate_destination_columns_rejected():
    _,p=fixture();p['columns']['location']='Record ID'
    with pytest.raises(ValueError,match='Duplicate'):validate_mapping(p)

def test_unmapped_proprietary_fields_rejected():
    _,p=fixture();p['columns']['api_token']='Access Key'
    with pytest.raises(ValueError,match='Unknown'):validate_mapping(p)

def test_reconciliation_keys_must_be_mapped():
    _,p=fixture();p['match_on']=['reviewer']
    with pytest.raises(ValueError,match='stable'):validate_mapping(p)

def test_default_excludes_synthetic_and_unreviewed():
    source,p=fixture();out,meta=export_csv(source,p)
    assert meta['prepared_rows']==0 and len(meta['withheld'])==3
    assert 'TRAIN-1001' not in out.decode()

def test_explicit_demo_exports_reviewed_only_and_notice():
    source,p=fixture();content,meta=export_csv(source,p,demo=True)
    rows=parse_export_csv(content)
    assert len(rows)==2 and meta['prepared_rows']==2 and len(meta['withheld'])==1
    assert rows[0][SAFE_COL].startswith('REVIEW_ONLY')
    assert rows[0]['Wet Density (pcf)']=='126'
    assert 'TRAIN-1003' not in str(rows)
    assert len(meta['sha256_csv'])==64 and meta['demo']

def test_exact_numeric_equivalence_is_not_conflict():
    source,p=fixture();content,_=export_csv(source,p,demo=True)
    out=reconciliation(source,content,p,demo=True)
    assert out['field_conflicts']==[]
    assert out['compared_records']==2
    assert out['withheld_cmt']

def test_fixture_conflict_detected_precisely():
    source,p=fixture();csvfile=(HERE/'SYNTHETIC_OPERATOR_EXPORT_WITH_CONFLICT.csv').read_bytes()
    result=reconciliation(source,csvfile,p,demo=True)
    assert len(result['field_conflicts'])==1
    assert result['field_conflicts'][0]['field']=='measurements.wet'
    assert result['field_conflicts'][0]['match_key']==['TRAIN-1002']
    assert result['comparison_status']=='NEEDS_HUMAN_REVIEW'

def test_duplicate_keys_are_quarantined_not_guessed():
    source,p=fixture();data=(HERE/'SYNTHETIC_OPERATOR_EXPORT_WITH_CONFLICT.csv').read_bytes()
    rows=parse_export_csv(data);rows.append(dict(rows[0]))
    import io
    dest=io.StringIO();w=csv.DictWriter(dest,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    result=reconciliation(source,dest.getvalue().encode(),p,demo=True)
    assert any(x['match_key']==['TRAIN-1001'] for x in result['ambiguous_keys'])
    assert result['compared_records']==1

def test_unknown_columns_do_not_pass_silently():
    source,p=fixture();src=b'Record ID,Test Type,Project Code\nX,soil,A\n'
    with pytest.raises(ValueError,match='Export missing mapped columns'):
        reconciliation(source,src,p,demo=True)

def test_csv_spreadsheet_formula_injection_escaped():
    source,p=fixture();source['records'][0]['location']='=HYPERLINK("evil")'
    content,_=export_csv(source,p,demo=True)
    assert parse_export_csv(content)[0]['Location'].startswith("'=")

def test_header_duplicates_and_ragged_csv_rejected():
    with pytest.raises(ValueError,match='duplicate'):parse_export_csv(b'a,a\n1,2\n')
    with pytest.raises(ValueError,match='Malformed'):parse_export_csv(b'a,b\n1,2,3\n')

def test_missing_required_field_withheld():
    source,p=fixture();source['records'][0]['project_code']=''
    _,meta=export_csv(source,p,demo=True)
    assert meta['prepared_rows']==1
    assert len(meta['withheld'])==2

def test_requires_independent_reviewer_even_if_reviewed():
    source,p=fixture();source['records'][0]['reviewer']='fake_technician'
    _,meta=export_csv(source,p,demo=True)
    assert meta['prepared_rows']==1

def test_reconciliation_reports_unmatched_records():
    source,p=fixture();sample=(HERE/'SYNTHETIC_OPERATOR_EXPORT_WITH_CONFLICT.csv').read_bytes()
    source['records'][1]['id']='TRAIN-NEW'
    out=reconciliation(source,sample,p,demo=True)
    assert len(out['missing_in_external'])==1
    assert len(out['missing_in_cmt'])==1

def test_safe_cmt_json_flat_and_strict():
    source,p=fixture();source['records'][0]['measurements']['wet']={'unexpected':'nested'}
    _,meta=export_csv(source,p,demo=True)
    assert meta['prepared_rows']==1
    assert any('Non-scalar' in r['reason'] for r in meta['withheld'])

# Server handoff endpoint must be engineer-only, deidentified and never include synthetic as authorized.
def test_reviewed_candidate_endpoint_roles(tmp_path,monkeypatch):
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'pilot.db'))
    pilot.create_user('fieldtech','technician','abcdefghijklmnop')
    pilot.create_user('chiefengineer','engineer','abcdefghijklmnop')
    client=TestClient(app)
    assert client.get('/api/pilot/export/bridge-candidates').status_code==401
    r=client.post('/api/pilot/login',json={'username':'fieldtech','password':'abcdefghijklmnop'})
    assert r.status_code==200
    assert client.get('/api/pilot/export/bridge-candidates').status_code==403
    client.post('/api/pilot/logout',headers={'x-cmt-csrf':r.json()['csrf']})
    r=client.post('/api/pilot/login',json={'username':'chiefengineer','password':'abcdefghijklmnop'})
    assert r.status_code==200
    ok=client.get('/api/pilot/export/bridge-candidates')
    assert ok.status_code==200 and ok.json()['records']==[]
    assert ok.json()['vendor_import_verified'] is False

def test_server_bridge_only_authorized_independently_reviewed(tmp_path,monkeypatch):
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'pilot2.db'))
    pilot.create_user('techpilot','technician','abcdefghijklmnop')
    pilot.create_user('engineerpilot','engineer','abcdefghijklmnop')
    tech=TestClient(app);eng=TestClient(app)
    a=tech.post('/api/pilot/login',json={'username':'techpilot','password':'abcdefghijklmnop'}).json()
    b=eng.post('/api/pilot/login',json={'username':'engineerpilot','password':'abcdefghijklmnop'}).json()
    draft={'test_type':'soil','project_code':'FAKE-A','location':'FICTIONAL',
           'spec_reference':'FAKE-SPEC','evidence_reference':'FAKE-PRINT',
           'source':'authorized','authorization_confirmed':True,
           'measurements':{'wet':126,'moisture':11.8,'mdd':120}}
    created=tech.post('/api/pilot/records',json=draft,headers={'x-cmt-csrf':a['csrf']})
    assert created.status_code==201,created.text
    rid=created.json()['id']
    # A draft is NEVER available for bridge candidates.
    assert eng.get('/api/pilot/export/bridge-candidates').json()['records']==[]
    assert tech.post(f'/api/pilot/records/{rid}/submit',json={'expected_version':1},headers={'x-cmt-csrf':a['csrf']}).status_code==200
    assert eng.get('/api/pilot/export/bridge-candidates').json()['records']==[]
    rv=eng.post(f'/api/pilot/records/{rid}/review',json={'expected_version':1,'decision':'reviewed','note':'Test-only review, noncertified.'},headers={'x-cmt-csrf':b['csrf']})
    assert rv.status_code==200,rv.text
    res=eng.get('/api/pilot/export/bridge-candidates')
    assert res.status_code==200 and len(res.json()['records'])==1
    assert res.json()['records'][0]['id']==rid
    # A second, synthetic reviewed record is not exposed as authorized data.
    draft['source']='synthetic';draft['authorization_confirmed']=False
    record=tech.post('/api/pilot/records',json=draft,headers={'x-cmt-csrf':a['csrf']}).json()
    tid=record['id']
    tech.post(f'/api/pilot/records/{tid}/submit',json={'expected_version':1},headers={'x-cmt-csrf':a['csrf']})
    eng.post(f'/api/pilot/records/{tid}/review',json={'expected_version':1,'decision':'reviewed','note':'Synthetic demo review only.'},headers={'x-cmt-csrf':b['csrf']})
    final=eng.get('/api/pilot/export/bridge-candidates').json()
    assert len(final['records'])==1 and final['withheld_count']==1
