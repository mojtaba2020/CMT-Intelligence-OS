"""Local pilot and non-normative QA release gates; synthetic inputs only."""
import json, sqlite3, hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from server.app import app
from server import pilot
from server.quality import audit_quality
from server.backup import backup,verify_file,restore_to_new_file
from server.report_verify import verify_report

PASS='Local-Test-Password-2026!'

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'test.sqlite3'))
    pilot.create_user('techa','technician',PASS)
    pilot.create_user('techb','technician',PASS)
    pilot.create_user('reviewa','engineer',PASS)
    return TestClient(app)

def log(c,user='techa'):
    r=c.post('/api/pilot/login',json={'username':user,'password':PASS})
    assert r.status_code==200,r.text
    return r.json()['csrf']

def send(c,url,csrf,body):
    return c.post('/api/pilot'+url,json=body,headers={'x-cmt-csrf':csrf})

def base(name, measurements):
    return {'test_type':name,'project_code':'SYN-11','location':'ZONE-A','source':'synthetic',
           'spec_reference':'SYN-SPEC-A','evidence_reference':'SYN-EVID-B','measurements':measurements}

@pytest.mark.parametrize('name,m,formula',[
 ('soil',{'wet':126,'moisture':11.8,'mdd':120},'illustrative_compaction_pct'),
 ('proctor',{'maxDry':121,'optMoist':12,'proctorMethod':'D698'},'entered_reference_mdd_pcf'),
 ('sand_cone',{'excavatedMass':7.8,'holeVolume':0.0625,'sandMoist':10,'refMdd':115},'illustrative_compaction_pct'),
 ('unit_weight',{'fullMass':56,'emptyMass':20.8,'calVolume':0.25},'illustrative_fresh_unit_weight_pcf'),
 ('asphalt_core',{'dryCore':1160,'ssdCore':1165,'underCore':674,'gmmCore':2.5},'illustrative_bulk_sg'),
 ('asphalt_voids',{'gmb':2.35,'gmm':2.5},'illustrative_air_voids_pct'),
 ('rebar_cover',{'cover':1.8,'coverMin':1.5},None),
])
def test_profiles_submit_gate_and_illustrations(name,m,formula):
    ok=audit_quality(name,base(name,m))
    assert ok['can_submit'],ok
    if formula:assert formula in ok['derived_illustrations']
    incomplete=m.copy();incomplete.pop(next(iter(m)))
    bad=audit_quality(name,base(name,incomplete))
    assert not bad['can_submit'] and any(x['code']=='INCOMPLETE_PROFILE' for x in bad['items'])

@pytest.mark.parametrize('name,measurements',[
 ('proctor',{'maxDry':121,'optMoist':12,'proctorMethod':'UNKNOWN'}),
 ('sand_cone',{'excavatedMass':-1,'holeVolume':0.0625,'sandMoist':10,'refMdd':115}),
 ('unit_weight',{'fullMass':20,'emptyMass':21,'calVolume':0.25}),
 ('asphalt_core',{'dryCore':1180,'ssdCore':1165,'underCore':674,'gmmCore':2.5}),
 ('asphalt_voids',{'gmb':2.6,'gmm':2.5}),
 ('rebar_cover',{'cover':1.8,'coverMin':2.5,'coverMax':1.5}),
])
def test_bad_physical_data_blocked(name,measurements):
    assert not audit_quality(name,base(name,measurements))['can_submit']


def test_no_profile_passes_silently():
    r=audit_quality('made_up_type',base('made_up_type',{'some':123}))
    assert not r['can_submit']


def test_login_lockout_persists_and_expires(client,monkeypatch):
    for i in range(5):
        assert client.post('/api/pilot/login',json={'username':'techa','password':'wrong'}).status_code==401
    assert client.post('/api/pilot/login',json={'username':'techa','password':PASS}).status_code==429
    with sqlite3.connect(str(pilot.db_path())) as conn:
        count=conn.execute("SELECT failures FROM login_attempts WHERE username='techa'").fetchone()[0]
        assert count==5
        conn.execute("UPDATE login_attempts SET blocked_until=0 WHERE username='techa'")
    assert log(client)
    with sqlite3.connect(str(pilot.db_path())) as conn:
        assert conn.execute("SELECT count(*) FROM login_attempts WHERE username='techa'").fetchone()[0]==0


def test_report_auth_integrity_digest_and_review_lifecycle(client):
    c=client; csrf=log(c)
    created=send(c,'/records',csrf,base('soil',{'wet':126,'moisture':11.8,'mdd':120}))
    assert created.status_code==201
    record_id=created.json()['id']
    unauth=TestClient(app)
    assert unauth.get(f'/api/pilot/records/{record_id}/report.json').status_code==401
    report=c.get(f'/api/pilot/records/{record_id}/report.json')
    assert report.status_code==200 and verify_report(report.json())['ok']
    assert report.json()['payload']['record']['status']=='draft'
    assert 'NOT CERTIFIED' in report.json()['payload']['label']
    data=report.json();data['payload']['record']['measurements']['wet']=-99
    assert not verify_report(data)['ok']
    assert send(c,f'/records/{record_id}/submit',csrf,{'expected_version':1}).status_code==200
    eng=TestClient(app);e=log(eng,'reviewa')
    assert send(eng,f'/records/{record_id}/review',e,{'expected_version':1,'decision':'reviewed',
                            'note':'Reviewed synthetic inputs and audit; not signed'}).status_code==200
    reviewed=eng.get(f'/api/pilot/records/{record_id}/report.json').json()
    assert reviewed['payload']['record']['reviewer']=='reviewa'
    assert reviewed['payload']['record']['status']=='reviewed'
    assert len(reviewed['payload']['audit_events'])==3
    assert verify_report(reviewed)['ok']
    with sqlite3.connect(str(pilot.db_path())) as conn:
        conn.execute("UPDATE audit SET event='INJECTED' WHERE record_id=? AND event='SUBMITTED'",(record_id,))
    assert eng.get(f'/api/pilot/records/{record_id}/report.json').status_code==409
    assert eng.get('/api/pilot/export').status_code==409
    assert eng.get('/api/pilot/export/neutral.csv').status_code==409


def test_recovery_drill_only_into_new_file(client,tmp_path):
    c=client;csrf=log(c)
    assert send(c,'/records',csrf,base('soil',{'wet':126,'moisture':11.8,'mdd':120})).status_code==201
    src=tmp_path/'snapshot.sqlite3';dst=tmp_path/'recovered.sqlite3'
    original=backup(src)
    recovered=restore_to_new_file(src,dst)
    assert recovered['ok'] and recovered['sha256']==original['sha256']
    assert verify_file(dst)['ok']
    with pytest.raises(FileExistsError):restore_to_new_file(src,dst)
    with pytest.raises(ValueError):restore_to_new_file(src,pilot.db_path())
    with sqlite3.connect(src) as conn:
        conn.execute("UPDATE audit SET event='CORRUPT' WHERE seq=1")
    with pytest.raises(ValueError):restore_to_new_file(src,tmp_path/'third.sqlite3')


def test_api_no_cache_headers(client):
    c=client
    r=c.get('/api/status')
    assert r.headers['cache-control']=='no-store'
    assert r.headers['x-frame-options']=='DENY'
    assert r.headers['x-content-type-options']=='nosniff'


def test_all_fifteen_synthetic_qa_workflows_fail_closed_on_missing_values():
    file=Path(__file__).resolve().parents[1]/'examples'/'SYNTHETIC_ALL_15_QA_PROFILES.json'
    cases=json.loads(file.read_text())['records']
    assert len(cases)==15
    assert len({case['test_type'] for case in cases})==15
    for case in cases:
        ok=audit_quality(case['test_type'],case)
        assert ok['can_submit'],(case['test_type'],ok)
        # Every workflow must reject a record containing no actual measurements.
        incomplete={**case,'measurements':{}}
        assert not audit_quality(case['test_type'],incomplete)['can_submit']


def test_report_button_in_offline_html_is_wired_to_server_route():
    file=Path(__file__).resolve().parents[1]/'index.html'
    html=file.read_text()
    assert 'id="pilotReport"' in html
    assert "$('pilotReport').onclick" in html
    assert '/report.json' in html


def test_boolean_cannot_masquerade_as_measurement():
    soil=base('soil',{'wet':True,'moisture':11.8,'mdd':120})
    flags=audit_quality('soil',soil)
    assert not flags['can_submit']
    assert any(i['code']=='INVALID_BOOLEAN' for i in flags['items'])
