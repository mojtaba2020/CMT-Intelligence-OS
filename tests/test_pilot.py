"""Local multiuser permission, version and audit tests. Only synthetic data."""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from server.app import app
from server import pilot

PWD='a-Very-Long-Local-Test-Password!2026'

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'sandbox.sqlite3'))
    pilot.create_user('techone','technician',PWD)
    pilot.create_user('techtwo','technician',PWD)
    pilot.create_user('engineerone','engineer',PWD)
    pilot.create_user('engineertwo','engineer',PWD)
    return lambda:TestClient(app)


def login(cli,username):
    result=cli.post('/api/pilot/login',json={'username':username,'password':PWD})
    assert result.status_code==200,result.text
    return result.json()['csrf']


def req(cli,method,path,csrf=None,body=None):
    head={'x-cmt-csrf':csrf} if csrf else {}
    return cli.request(method,'/api/pilot'+path,headers=head,json=body)


def draft(source='synthetic',authorized=False):
    return {'test_type':'soil','project_code':'DEMO-001','location':'A2',
            'spec_reference':'SPEC-REV-A','evidence_reference':'GAUGE-123',
            'source':source,'authorization_confirmed':authorized,
            'measurements':{'wet':126,'moisture':11.8,'mdd':120,'minComp':95}}


def test_auth_and_csrf_and_no_default_accounts(env):
    c=env()
    assert req(c,'GET','/records').status_code==401
    assert c.post('/api/pilot/login',json={'username':'techone','password':'wrong-password'}).status_code==401
    csrf=login(c,'techone')
    assert req(c,'POST','/records',body=draft()).status_code==403
    assert req(c,'POST','/records','bad-token',draft()).status_code==403
    assert req(c,'POST','/records',csrf,draft()).status_code==201
    assert req(c,'POST','/logout',csrf).status_code==200
    assert req(c,'GET','/records').status_code==401


def test_unauthorized_authorized_data_is_rejected_and_bad_inputs(env):
    c=env();token=login(c,'techone')
    assert req(c,'POST','/records',token,draft(source='authorized',authorized=False)).status_code==422
    assert req(c,'POST','/records',token,draft(source='authorized',authorized=True)).status_code==201
    x=draft();x['measurements']={'a':{'b':{'c':{'d':{'e':1}}}}}
    assert req(c,'POST','/records',token,x).status_code==422
    x=draft();x['measurements']={}
    assert req(c,'POST','/records',token,x).status_code==422
    x=draft();x['spec_reference']=' ';
    assert req(c,'POST','/records',token,x).status_code==422


def test_independent_review_and_locked_decision(env):
    tech=env();tcsrf=login(tech,'techone')
    eng=env();ec=login(eng,'engineerone')
    user2=env();u2=login(user2,'techtwo')
    created=req(tech,'POST','/records',tcsrf,draft()).json();rid=created['id'];assert created['status']=='draft'
    assert req(user2,'GET','/records/'+rid).status_code==404
    assert req(user2,'GET','/records').json()['records']==[]
    assert req(user2,'POST',f'/records/{rid}/submit',u2,{'expected_version':1}).status_code==404
    assert req(tech,'POST',f'/records/{rid}/review',tcsrf,{'expected_version':1,'decision':'reviewed','note':'All source checks done'}).status_code==403
    assert req(eng,'POST',f'/records/{rid}/review',ec,{'expected_version':1,'decision':'reviewed','note':'All source checks done'}).status_code==409
    assert req(tech,'POST',f'/records/{rid}/submit',tcsrf,{'expected_version':1}).status_code==200
    assert req(tech,'PUT',f'/records/{rid}',tcsrf,{**draft(),'expected_version':1}).status_code==409
    assert req(eng,'POST',f'/records/{rid}/review',ec,{'expected_version':1,'decision':'reviewed','note':'Confirmed references and observations'}).status_code==200
    assert req(eng,'POST',f'/records/{rid}/review',ec,{'expected_version':1,'decision':'reviewed','note':'Another attempt'}).status_code==409
    assert req(tech,'PUT',f'/records/{rid}',tcsrf,{**draft(),'expected_version':1}).status_code==409
    assert req(eng,'GET','/audit/check').json()['ok'] is True
    assert req(tech,'GET','/audit/check').status_code==403


def test_return_revise_optimistic_lock_and_full_history(env):
    tech=env();token=login(tech,'techone')
    eng=env();e=login(eng,'engineerone')
    rid=req(tech,'POST','/records',token,draft()).json()['id']
    req(tech,'POST',f'/records/{rid}/submit',token,{'expected_version':1})
    review=req(eng,'POST',f'/records/{rid}/review',e,{'expected_version':1,'decision':'needs_correction','note':'Incorrect moisture evidence source'})
    assert review.status_code==200
    changed=draft();changed['measurements']['moisture']=12
    rev=req(tech,'PUT',f'/records/{rid}',token,{**changed,'expected_version':1})
    assert rev.status_code==200 and rev.json()['version']==2 and rev.json()['status']=='draft'
    assert req(tech,'PUT',f'/records/{rid}',token,{**changed,'expected_version':1}).status_code==409
    hist=req(tech,'GET',f'/records/{rid}/history').json()['history']
    assert len(hist)==2 and hist[0]['body']['measurements']['moisture']==11.8
    assert hist[1]['body']['measurements']['moisture']==12
    assert req(tech,'POST',f'/records/{rid}/submit',token,{'expected_version':2}).status_code==200
    assert req(eng,'POST',f'/records/{rid}/review',e,{'expected_version':1,'decision':'reviewed','note':'Wrong version check'}).status_code==409
    assert req(eng,'POST',f'/records/{rid}/review',e,{'expected_version':2,'decision':'reviewed','note':'Updated source verified independently'}).status_code==200


def test_self_review_blocked_for_engineer_author(env):
    e1=env();t=login(e1,'engineerone')
    e2=env();t2=login(e2,'engineertwo')
    rid=req(e1,'POST','/records',t,draft()).json()['id']
    req(e1,'POST',f'/records/{rid}/submit',t,{'expected_version':1})
    assert req(e1,'POST',f'/records/{rid}/review',t,{'expected_version':1,'decision':'reviewed','note':'Self approval attempt'}).status_code==403
    assert req(e2,'POST',f'/records/{rid}/review',t2,{'expected_version':1,'decision':'reviewed','note':'Second engineer review comment'}).status_code==200


def test_audit_detects_direct_database_tampering(env):
    t=env();csrf=login(t,'techone')
    req(t,'POST','/records',csrf,draft())
    eng=env();e=login(eng,'engineerone')
    assert req(eng,'GET','/audit/check').json()['ok'] is True
    # Authorized test-only simulation of tampering with SQLite audit row.
    with sqlite3.connect(str(pilot.db_path())) as con:
        con.execute("UPDATE audit SET event='ALTERED' WHERE seq=1")
    result=req(eng,'GET','/audit/check').json()
    assert result['ok'] is False and result['first_bad_seq']==1


def test_no_remote_pilot_access(env):
    with TestClient(app,client=('192.0.2.10',50000)) as external:
        assert external.get('/api/pilot/records').status_code==403


def test_audit_detects_revision_body_and_status_tamper(env):
    tech=env();token=login(tech,'techone')
    rid=req(tech,'POST','/records',token,draft()).json()['id']
    eng=env();e=login(eng,'engineerone')
    assert req(eng,'GET','/audit/check').json()['ok'] is True
    with sqlite3.connect(str(pilot.db_path())) as con:
        con.execute("UPDATE revisions SET body=? WHERE record_id=? AND version=1",('{"injected":true}',rid))
    assert req(eng,'GET','/audit/check').json()['ok'] is False
    with sqlite3.connect(str(pilot.db_path())) as con:
        original=pilot.canonical({k:v for k,v in draft().items() if k!='authorization_confirmed'})
        con.execute('UPDATE revisions SET body=? WHERE record_id=? AND version=1',(original,rid))
        con.execute("UPDATE records SET status='reviewed' WHERE id=?",(rid,))
    a=req(eng,'GET','/audit/check').json()
    assert a['ok'] is False and 'diverges' in a['reason']


def test_external_origin_write_is_blocked(env):
    c=env();csrf=login(c,'techone')
    response=c.post('/api/pilot/records',headers={'origin':'https://untrusted.example','x-cmt-csrf':csrf},json=draft())
    assert response.status_code==403
