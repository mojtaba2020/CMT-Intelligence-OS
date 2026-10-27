from __future__ import annotations
import csv
import io
import json
from pathlib import Path
import zipfile
import pytest
from pydantic import ValidationError
from pilotkit.batch import build, verify, compile_report, _read_cases, _csv_safe, MAX_CASES
from server.reconcile_v15 import Case

BASE = Path(__file__).resolve().parents[1]
NDG = json.loads((BASE/'examples/v15/ndg_synthetic_conflict.json').read_text())
CONCRETE = json.loads((BASE/'examples/v15/concrete_synthetic_metric.json').read_text())


def _write(tmp_path, rows, filename='cases.json'):
    p=tmp_path/filename
    p.write_text(json.dumps({'cases':rows}),encoding='utf-8')
    return p


def _load_zip(p,name):
    with zipfile.ZipFile(p) as z:return z.read(name)


def test_build_and_verify_sample(tmp_path):
    p=_write(tmp_path,[NDG,CONCRETE]);dest=tmp_path/'proof.zip'
    out=build(p,dest,mode='synthetic')
    assert out['summary']=={'cases':2,'with_findings':1,'quarantined':0,'total_findings':1}
    assert verify(dest)['verified']
    report=json.loads(_load_zip(dest,'report.json'))
    assert report['review_only'] is True and report['vendor_import_verified'] is False
    assert all(item['engineer_approved'] is False and item['official_acceptance'] is None for item in report['cases'])
    assert all(item['review_status'] != 'APPROVED' for item in report['cases'])
    assert report['cases'][1]['issues']==[]


def test_denies_mixed_modes(tmp_path):
    valid=_write(tmp_path,[NDG,CONCRETE]); assert len(_read_cases(valid,'synthetic'))==2
    with pytest.raises(ValueError,match='source flags'): build(valid,tmp_path/'no.zip',mode='authorized')


def test_denies_implicitly_authorized(tmp_path):
    data=dict(NDG);data['synthetic']=False
    p=_write(tmp_path,[data]);
    with pytest.raises(ValueError,match='source flags'):build(p,tmp_path/'no.zip',mode='synthetic')
    assert build(p,tmp_path/'ok.zip',mode='authorized')['summary']['cases']==1


def test_required_case_data_fails_closed(tmp_path):
    bad=dict(NDG);bad.pop('synthetic')
    with pytest.raises(ValueError,match='invalid case'):build(_write(tmp_path,[bad]),tmp_path/'x.zip',mode='synthetic')


def test_duplicate_case_quarantined(tmp_path):
    p=_write(tmp_path,[NDG,NDG]);dest=tmp_path/'x.zip'
    build(p,dest,mode='synthetic')
    report=json.loads(_load_zip(dest,'report.json'))
    assert report['cases'][1]['review_status']=='QUARANTINED_DUPLICATE'
    assert report['summary']['quarantined']==1


def test_duplicate_source_quarantined(tmp_path):
    other=json.loads(json.dumps(NDG))
    other['documents'][0]['test_id']='NDG-NEW'
    other['documents'][1]['test_id']='NDG-NEW'
    report,_=compile_report([Case.model_validate(NDG),Case.model_validate(other)],'synthetic')
    assert report['summary']['quarantined']==1


def test_html_escape_and_csv_injection(tmp_path):
    evil=json.loads(json.dumps(NDG))
    evil['documents'][0]['project_id']="=HYPERLINK(\"evil\")"
    evil['documents'][1]['project_id']="=HYPERLINK(\"evil\")"
    # IDs containing quotes are allowable in local test cases, but CSV must still be safe
    p=_write(tmp_path,[evil]);z=tmp_path/'evil.zip';build(p,z,mode='synthetic')
    csvtext=_load_zip(z,'review_queue.csv').decode('utf-8-sig')
    line=list(csv.DictReader(io.StringIO(csvtext)))[0]
    assert line['project_id'].startswith("'=")
    assert b'<script' not in _load_zip(z,'summary.html')
    assert '&quot;' in _load_zip(z,'summary.html').decode('utf-8')


def test_html_escape_malicious_title(tmp_path):
    evil=json.loads(json.dumps(NDG))
    evil['documents'][0]['project_id']='<script>alert(1)</script>'
    evil['documents'][1]['project_id']='<script>alert(1)</script>'
    p=_write(tmp_path,[evil]);z=tmp_path/'x.zip';build(p,z,mode='synthetic')
    html=_load_zip(z,'summary.html').decode()
    assert '<script>' not in html and '&lt;script&gt;' in html


def test_modified_report_detected(tmp_path):
    p=_write(tmp_path,[NDG]);z=tmp_path/'a.zip';build(p,z,mode='synthetic')
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(z) as src, zipfile.ZipFile(bad,'w') as dest:
        for name in src.namelist():
            data=src.read(name)
            if name=='report.json':data=data.replace(b'REVIEW_REQUIRED',b'APPROVED_HACKED')
            dest.writestr(name,data)
    with pytest.raises(ValueError,match='tampering'):verify(bad)


def test_reject_unknown_archive_member(tmp_path):
    z=tmp_path/'x.zip';build(_write(tmp_path,[NDG]),z,mode='synthetic')
    with zipfile.ZipFile(z,'a') as f:f.writestr('../attack.txt',b'bad')
    with pytest.raises(ValueError,match='Unexpected'):verify(z)


def test_reject_duplicate_archive_member(tmp_path):
    z=tmp_path/'x.zip';build(_write(tmp_path,[NDG]),z,mode='synthetic')
    with zipfile.ZipFile(z,'a') as f:f.writestr('NOTICE.txt',b'bad')
    with pytest.raises(ValueError,match='Unexpected'):verify(z)


def test_reject_missing_cases(tmp_path):
    with pytest.raises(ValueError,match='1 to 250'):build(_write(tmp_path,[]),tmp_path/'x.zip',mode='synthetic')


def test_reject_unknown_case_fields(tmp_path):
    bad=dict(NDG);bad['unexpected']='yes'
    with pytest.raises(ValueError,match='invalid case'):build(_write(tmp_path,[bad]),tmp_path/'x.zip',mode='synthetic')


def test_both_source_conflicts_are_counted(tmp_path):
    bad=json.loads(json.dumps(NDG))
    bad['documents'][1]['project_id']='OTHER-PROJECT'
    bad['documents'][1]['observations'][1]['value']='13'
    report,_=compile_report([Case.model_validate(bad)],'synthetic')
    codes={f['code'] for f in report['cases'][0]['issues']}
    assert 'IDENTIFIER_MISMATCH' in codes and 'VALUE_MISMATCH' in codes


def test_safety_no_field_images_in_bundle(tmp_path):
    z=tmp_path/'x.zip';build(_write(tmp_path,[NDG]),z,mode='synthetic')
    with zipfile.ZipFile(z) as f:
        assert all(not name.endswith(('.png','.jpg','.webp','.jpeg')) for name in f.namelist())
        assert set(f.namelist())=={'manifest.json','report.json','review_queue.csv','summary.html','NOTICE.txt'}


def test_max_cases(tmp_path):
    rows=[json.loads(json.dumps(NDG)) for i in range(MAX_CASES+1)]
    with pytest.raises(ValueError,match='1 to 250'): build(_write(tmp_path,rows),tmp_path/'x.zip',mode='synthetic')


def test_scalar_formula_escape():
    for value in ('=1+2',' +A1','\t=1','@foo','-SUM(A1:A2)'):
        assert _csv_safe(value).startswith("'")
    assert _csv_safe('93.17')=='93.17'
