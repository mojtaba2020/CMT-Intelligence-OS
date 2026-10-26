"""v1.4 safety and chain of custody tests: no vendor writes."""
import csv
import io
import json
import zipfile
from pathlib import Path
from io import BytesIO
from copy import deepcopy
import pytest
from bridge.assurance import (
    preflight, handoff_bundle, verify_bundle, prepare_strict, reconcile_strict,
    record_issue, check_profile,
)
from bridge.cli import main

ROOT=Path(__file__).resolve().parents[1]

def fixture():
    ex=ROOT/'bridge'/'examples'
    return (json.loads((ex/'SYNTHETIC_CMT_RECORDS.json').read_text()),
            json.loads((ex/'SYNTHETIC_OPERATOR_PROFILE.json').read_text()))

def test_units_required_in_profile():
    data,p=fixture();del p['measurement_units']['measurements.wet']
    with pytest.raises(ValueError,match='explicit unit'):preflight(data,p,demo=True)

def test_unit_mismatch_is_quarantined():
    data,p=fixture();data['records'][0]['measurement_units']['measurements.wet']='kg/m3'
    g=preflight(data,p,demo=True)
    assert g['eligible_count']==1 and any('unit_mismatch' in v for v in g['quarantined'][0]['reasons'])

def test_missing_source_units_block_real_data():
    data,p=fixture();data['records'][0]['source']='authorized';del data['records'][0]['measurement_units']
    g=preflight(data,p)
    assert not g['eligible_count'] and 'TRAIN-1001' in str(g['quarantined'])

def test_undocumented_unit_rejected():
    data,p=fixture();p['measurement_units']['measurements.wet']='furlongs/fortnight'
    with pytest.raises(ValueError,match='Unknown'):preflight(data,p,demo=True)

def test_nonnumeric_measurement_blocks_export():
    data,p=fixture();data['records'][0]['measurements']['wet']='not measured'
    assert preflight(data,p,demo=True)['eligible_count']==1

def test_malicious_formula_is_not_numeric():
    data,p=fixture();data['records'][0]['measurements']['wet']='=HYPERLINK("evil")'
    _,_,gate=prepare_strict(data,p,demo=True)
    assert gate['eligible_count']==1

def test_duplicate_ids_quarantined_all_occurrences():
    data,p=fixture();data['records'][1]['id']=data['records'][0]['id']
    gate=preflight(data,p,demo=True)
    assert gate['eligible_count']==0 and gate['quarantined_count']==3

def test_duplicate_composite_match_keys_are_quarantined():
    data,p=fixture();p['match_on']=['project_code','test_type']
    gate=preflight(data,p,demo=True)
    assert gate['eligible_count']==0
    assert any('duplicate_match_key' in row['reasons'] for row in gate['quarantined'])

def test_independent_review_still_required():
    data,p=fixture();data['records'][0]['reviewer']=data['records'][0]['creator']
    assert preflight(data,p,demo=True)['eligible_count']==1

def test_bundle_includes_notice_and_integrity_check():
    data,p=fixture();bundle,meta=handoff_bundle(data,p,demo=True)
    check=verify_bundle(bundle)
    assert check['ok'] and check['prepared_rows']==2 and check['quarantined_rows']==1
    with zipfile.ZipFile(BytesIO(bundle)) as z:
        s=z.read('PREPARED_REVIEW_ONLY.csv').decode('utf-8-sig')
        assert 'REVIEW_ONLY_NOT_VENDOR_IMPORT_APPROVED' in s
        assert 'TRAIN-1003' not in s
        assert 'MAPPING.json' in z.namelist() and 'MANIFEST.json' in z.namelist()

def test_bundle_deterministic():
    data,p=fixture()
    assert handoff_bundle(data,p,demo=True)[0]==handoff_bundle(data,p,demo=True)[0]

def modified_zip(original,replacement,change):
    out=BytesIO()
    with zipfile.ZipFile(BytesIO(original)) as zin, zipfile.ZipFile(out,'w') as zout:
        for name in zin.namelist():
            v=zin.read(name)
            if name==replacement: v=change(v)
            zout.writestr(name,v)
    return out.getvalue()

def test_tampered_csv_rejected():
    data,p=fixture();b,_=handoff_bundle(data,p,demo=True)
    tampered=modified_zip(b,'PREPARED_REVIEW_ONLY.csv',lambda x:x.replace(b'TRAIN-1001',b'TRAIN-9999'))
    with pytest.raises(ValueError,match='SHA-256 mismatch'):verify_bundle(tampered)

def test_duplicated_zip_entry_rejected():
    data,p=fixture();b,_=handoff_bundle(data,p,demo=True)
    out=BytesIO()
    with zipfile.ZipFile(BytesIO(b)) as inp,zipfile.ZipFile(out,'w') as z:
        for name in inp.namelist():z.writestr(name,inp.read(name))
        z.writestr('MAPPING.json',b'{}')
    with pytest.raises(ValueError,match='duplicate'):verify_bundle(out.getvalue())

def test_zip_traversal_entry_rejected():
    data,p=fixture();b,_=handoff_bundle(data,p,demo=True)
    out=BytesIO()
    with zipfile.ZipFile(BytesIO(b)) as inp,zipfile.ZipFile(out,'w') as z:
        for name in inp.namelist():z.writestr(name,inp.read(name))
        z.writestr('../../evil.txt',b'evil')
    with pytest.raises(ValueError,match='Unknown'):verify_bundle(out.getvalue())

def test_comparison_detects_actual_mismatch():
    data,p=fixture();ext=(ROOT/'bridge'/'examples'/'SYNTHETIC_OPERATOR_EXPORT_WITH_CONFLICT.csv').read_bytes()
    r=reconcile_strict(data,ext,p,demo=True)
    assert len(r['field_conflicts'])==1 and r['comparison_status']=='NEEDS_HUMAN_REVIEW'

def test_source_quarantine_prevents_false_clean_comparison():
    data,p=fixture();csv_data,_,_=prepare_strict(data,p,demo=True)
    r=reconcile_strict(data,csv_data,p,demo=True)
    assert r['comparison_status']=='NEEDS_HUMAN_REVIEW' and r['source_quarantine']

def test_external_formula_is_flagged():
    data,p=fixture();csv_data,_,_=prepare_strict(data,p,demo=True)
    dangerous=csv_data.replace(b'Lot 4, Lift 2',b'=HYPERLINK(""evil"")')
    r=reconcile_strict(data,dangerous,p,demo=True)
    assert r['external_csv_warnings'] and r['comparison_status']=='NEEDS_HUMAN_REVIEW'

def test_bundle_verify_cli(tmp_path):
    data,p=fixture();b,_=handoff_bundle(data,p,demo=True)
    archive=tmp_path/'bundle.zip';archive.write_bytes(b)
    report=tmp_path/'check.json'
    main(['verify',str(archive),'--output',str(report)])
    assert json.loads(report.read_text())['ok']
    with pytest.raises(ValueError,match='already exists'):
        main(['verify',str(archive),'--output',str(report)])

def test_cli_refuses_synthetic_without_explicit_demo(tmp_path):
    data,p=fixture();example=tmp_path/'source.json';mapping=tmp_path/'profile.json'
    example.write_text(json.dumps(data));mapping.write_text(json.dumps(p))
    target=tmp_path/'handoff.zip'
    with pytest.raises(ValueError,match='No eligible records'):
        main(['bundle',str(example),str(mapping),'--output',str(target)])
    assert not target.exists()

def test_rejected_record_never_appears_in_csv():
    data,p=fixture();data['records'][1]['measurement_units']['measurements.mdd']='kg/m3'
    bundle,_=handoff_bundle(data,p,demo=True)
    with zipfile.ZipFile(BytesIO(bundle)) as z:
        contents=z.read('PREPARED_REVIEW_ONLY.csv').decode('utf-8-sig')
        assert 'TRAIN-1002' not in contents and 'TRAIN-1001' in contents

def test_reviewed_authorized_pilot_to_v14_handoff(tmp_path,monkeypatch):
    """Server -> reviewer -> unit-aware bundle, no ElmTree connectivity."""
    from fastapi.testclient import TestClient
    from server import pilot
    from server.app import app
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'pilot.db'))
    pilot.create_user('techniciantest','technician','abcdefghijklmnop')
    pilot.create_user('engineertest','engineer','abcdefghijklmnop')
    tech=TestClient(app);eng=TestClient(app)
    ta=tech.post('/api/pilot/login',json={'username':'techniciantest','password':'abcdefghijklmnop'}).json()
    ea=eng.post('/api/pilot/login',json={'username':'engineertest','password':'abcdefghijklmnop'}).json()
    draft={'test_type':'soil','project_code':'FICTIONAL-PROJECT','location':'Demo only',
           'spec_reference':'DEMO-SPEC','evidence_reference':'DEMO-GAUGE',
           'source':'authorized','authorization_confirmed':True,
           'measurement_units':{'measurements.wet':'pcf','measurements.moisture':'percent','measurements.mdd':'pcf'},
           'measurements':{'wet':126,'moisture':11.8,'mdd':120}}
    created=tech.post('/api/pilot/records',json=draft,headers={'x-cmt-csrf':ta['csrf']})
    assert created.status_code==201,created.text
    rid=created.json()['id']
    assert tech.post(f'/api/pilot/records/{rid}/submit',json={'expected_version':1},headers={'x-cmt-csrf':ta['csrf']}).status_code==200
    rv=eng.post(f'/api/pilot/records/{rid}/review',json={'expected_version':1,'decision':'reviewed','note':'Demo independent review only.'},headers={'x-cmt-csrf':ea['csrf']})
    assert rv.status_code==200,rv.text
    handoff=eng.get('/api/pilot/export/bridge-candidates')
    assert handoff.status_code==200,handoff.text
    source=handoff.json()
    _,p=fixture()
    contents,man=handoff_bundle(source,p)
    assert verify_bundle(contents)['prepared_rows']==1
    assert source['records'][0]['measurement_units']['measurements.wet']=='pcf'
