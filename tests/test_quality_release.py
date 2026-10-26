import csv
import io
import os
import sqlite3
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from server.app import app
from server import pilot
from server.quality import audit_quality
from server.backup import backup,verify_file
from validation.pilot_benchmark import benchmark

PASS='safe-Local-only-Test-Password-2026'

@pytest.fixture
def cli(tmp_path,monkeypatch):
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'demo.sqlite3'))
    pilot.create_user('labtech','technician',PASS)
    pilot.create_user('reviewer','engineer',PASS)
    return TestClient(app)

def login(client,name):
    r=client.post('/api/pilot/login',json={'username':name,'password':PASS})
    assert r.status_code==200,r.text
    return r.json()['csrf']

def post(client,path,csrf,obj,method='POST'):
    return client.request(method,'/api/pilot'+path,headers={'x-cmt-csrf':csrf},json=obj)

def record(typ='soil',m=None):
    return {'test_type':typ,'project_code':'D-01','location':'A2','source':'synthetic',
            'spec_reference':'SYN-REV-1','evidence_reference':'SYN-DEVICE-01',
            'measurements':m or {'wet':126,'moisture':11.8,'mdd':120,'minComp':95}}

def test_preflight_math_and_warning():
    qa=audit_quality('soil',record('soil'))
    assert qa['can_submit'] and qa['warnings']>=1
    assert round(qa['derived_illustrations']['illustrative_compaction_pct'],2)==93.92
    assert any(x['code']=='BELOW_USER_THRESHOLD' for x in qa['items'])
    assert 'certification' in qa['disclaimer']

def test_impossible_soil_prevents_submit_without_deleting_draft(cli):
    t=login(cli,'labtech')
    d=record();d['measurements']['wet']=-15
    qa=post(cli,'/qa/preview',t,d)
    assert qa.status_code==200 and not qa.json()['can_submit']
    create=post(cli,'/records',t,d)
    assert create.status_code==201
    rid=create.json()['id']
    submit=post(cli,f'/records/{rid}/submit',t,{'expected_version':1})
    assert submit.status_code==422
    assert cli.get(f'/api/pilot/records/{rid}').json()['status']=='draft'
    assert cli.get(f'/api/pilot/records/{rid}/qa').json()['blockers']>0
    repaired=record();repaired['expected_version']=1
    assert post(cli,f'/records/{rid}',t,repaired,method='PUT').status_code==200
    assert post(cli,f'/records/{rid}/submit',t,{'expected_version':2}).status_code==200

def test_preflight_roles_and_external_origin(cli):
    tech=login(cli,'labtech')
    rid=post(cli,'/records',tech,record()).json()['id']
    second=TestClient(app)
    eng=login(second,'reviewer')
    assert second.get(f'/api/pilot/records/{rid}/qa').status_code==200
    assert cli.get('/api/pilot/export/neutral.csv').status_code==403
    bad=cli.post('/api/pilot/qa/preview',json=record(),headers={'x-cmt-csrf':tech,'origin':'https://evil.example'})
    assert bad.status_code==403

def test_engineer_csv_export_sanitizes_formula_and_integrity(cli):
    tech=login(cli,'labtech')
    d=record();d['location']='  =1+1';d['project_code']='@danger';d['measurements']['raw']='=HYPERLINK("x")'
    rid=post(cli,'/records',tech,d).json()['id']
    eng_cli=TestClient(app);eng=login(eng_cli,'reviewer')
    result=eng_cli.get('/api/pilot/export/neutral.csv')
    assert result.status_code==200
    assert 'UNCERTIFIED' in result.headers['content-disposition']
    row=list(csv.reader(io.StringIO(result.text)))[1]
    assert row[5].startswith("'@") and row[6].startswith("'  =")
    assert '=HYPERLINK' in row[-1] and row[-1].startswith('{')
    with sqlite3.connect(str(pilot.db_path())) as con:
        con.execute("UPDATE records SET status='reviewed' WHERE id=?",(rid,))
    assert eng_cli.get('/api/pilot/export/neutral.csv').status_code==409

def test_sieve_curve_and_cylinder_data_qa():
    sieve=record('sieve_stack',{'sampleMass':1000,'balanceTol':1,
        'points':[{'mm':4.75,'mass':300},{'mm':2,'mass':300},{'mm':0,'mass':400}]})
    ok=audit_quality('sieve_stack',sieve)
    assert ok['can_submit'] and ok['derived_illustrations']['mass_balance_difference_pct']==0
    sieve['measurements']['points'][1]['mm']=4.75
    assert not audit_quality('sieve_stack',sieve)['can_submit']
    proctor=record('proctor_curve',{'points':[{'wet':130,'moisture':8},
            {'wet':145,'moisture':11},{'wet':131,'moisture':14}]})
    assert 'observed_peak_dry_density_pcf' in audit_quality('proctor_curve',proctor)['derived_illustrations']
    cyl=record('cylinder_set',{'points':[{'age':7,'diameter':4,'load':55000},{'age':28,'diameter':4,'load':75000}]})
    q=audit_quality('cylinder_set',cyl)
    assert q['can_submit'] and 'illustrative_set_mean_psi' not in q['derived_illustrations']
    assert any(x['code']=='MIXED_AGES' for x in q['items'])

def test_backup_and_verify_plus_negative_tamper(cli,tmp_path):
    tech=login(cli,'labtech')
    post(cli,'/records',tech,record())
    dest=tmp_path/'snap.sqlite3'
    result=backup(dest)
    assert result['ok'] and dest.exists() and len(result['sha256'])==64
    assert verify_file(dest)['ok']
    with sqlite3.connect(str(dest)) as con:
        con.execute("UPDATE audit SET event='tampered' WHERE seq=1")
    assert verify_file(dest)['ok'] is False
    with pytest.raises(FileExistsError):backup(dest)

def test_benchmark_source_separation_and_negative_time():
    inp=Path(__file__).resolve().parents[1]/'examples'/'SYNTHETIC_LABELLED_BENCHMARK.csv'
    with inp.open() as f:metric=benchmark(csv.DictReader(f))
    synthetic=metric['by_source']['synthetic']
    assert synthetic['labeled_fields']==8
    assert synthetic['critical_errors_or_abstentions']==2
    assert synthetic['slower_observations']==2
    assert metric['dataset_types_never_pooled']
    data=[{'case_id':'A','source':'authorized','test_type':'soil','field':'wet','gold':'123','predicted':'123',
           'tolerance':'0','critical':'true','manual_seconds':'','assisted_seconds':'','correction_seconds':''}]
    assert set(benchmark(data)['by_source'])=={'authorized'}
    with pytest.raises(ValueError):benchmark(data+data)

def test_missing_critical_fields_and_mixed_units_fail_closed():
    missing=record('soil',{'wet':126,'moisture':11.8})
    qa=audit_quality('soil',missing)
    assert not qa['can_submit'] and any(i['code']=='INCOMPLETE_PROFILE' for i in qa['items'])
    mixed=record('soil',{'wet':126,'moisture':11.8,'mdd':120,'density_unit':'pcf','mdd_unit':'kg/m3'})
    assert not audit_quality('soil',mixed)['can_submit']
    aligned=record('soil',{'wet':2000,'moisture':10,'mdd':2100,'density_unit':'kg/m3','mdd_unit':'kg/m3'})
    values=audit_quality('soil',aligned)['derived_illustrations']
    assert 'estimated_dry_density_kg_m3' in values
    assert 'estimated_dry_density_pcf' not in values
