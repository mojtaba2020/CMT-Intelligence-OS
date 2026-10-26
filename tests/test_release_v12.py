"""Adversarial v1.2 tests for independent labels, fail-closed release checks, API hardening."""
from __future__ import annotations
import csv
import io
import json
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from server.app import app
from server import pilot
from server.preflight import preflight
from validation.label_reconcile import reconcile,run
from validation.release_gate import release_gate,SECURITY_CONTROLS

EXAMPLES=Path(__file__).resolve().parents[1]

def labels():
    with (EXAMPLES/'validation'/'SYNTHETIC_TWO_LABELERS.csv').open(newline='') as f:
        return list(csv.DictReader(f))

def matrix():
    with (EXAMPLES/'validation'/'METHOD_APPROVAL_MATRIX_PENDING.csv').open(newline='') as f:
        return list(csv.DictReader(f))

def benchmark():
    with (EXAMPLES/'examples'/'SYNTHETIC_LABELLED_BENCHMARK.csv').open(newline='') as f:
        return list(csv.DictReader(f))

def security():
    return json.loads((EXAMPLES/'validation'/'SECURITY_EVIDENCE_PENDING.json').read_text())

def test_double_label_agreement_and_adjudication():
    resolved,conflicts=reconcile(labels())
    assert len(resolved)==2 and not conflicts
    assert resolved[0]['gold']=='126' and resolved[1]['gold']=='11.8'

def test_unresolved_conflict_fails_closed():
    rows=labels();rows[1]['adjudicated']=''
    resolved,conflicts=reconcile(rows)
    assert len(resolved)==1 and len(conflicts)==1

def test_labelers_must_be_distinct():
    rows=labels();rows[0]['labeler_b_id']=rows[0]['labeler_a_id']
    with pytest.raises(ValueError,match='distinct'):reconcile(rows)

def test_third_reviewer_must_be_independent():
    rows=labels();rows[1]['adjudicator_id']=rows[1]['labeler_a_id']
    _,conflicts=reconcile(rows)
    assert conflicts

def test_duplicate_labels_rejected():
    rows=labels();rows.append(dict(rows[0]))
    with pytest.raises(ValueError,match='duplicate'):reconcile(rows)

def test_double_label_csv_cli_output(tmp_path):
    input=EXAMPLES/'validation'/'SYNTHETIC_TWO_LABELERS.csv'
    out=tmp_path/'gold.csv';meta=tmp_path/'manifest.json'
    info=run(input,out,meta)
    assert info['resolved_fields']==2
    assert all(row['source']=='synthetic' for row in csv.DictReader(out.open()))
    assert len(info['input_sha256'])==64

def test_double_label_does_not_emit_partial_on_dispute(tmp_path):
    rows=labels();rows[1]['adjudicator_id']='';source=tmp_path/'in.csv'
    with source.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    out=tmp_path/'out.csv';meta=tmp_path/'manifest.json'
    with pytest.raises(ValueError):run(source,out,meta)
    assert not out.exists() and not meta.exists()

def test_release_blocks_all_missing_evidence():
    report=release_gate(matrix(),benchmark(),security())
    assert report['release_decision']=='BLOCKED'
    assert report['checks']['method_count']==15
    assert any('method has no independently' in x for x in report['issues'])
    assert any('security/deployment' in x for x in report['issues'])
    assert any('authorized' in x for x in report['issues'])

def test_fake_synthetic_high_accuracy_never_passes():
    good=[dict(x) for x in benchmark()]
    for r in good:r['predicted']=r['gold']
    report=release_gate(matrix(),good,security(),min_fields=1,min_critical=1,min_accuracy=0)
    assert report['release_decision']=='BLOCKED'
    assert any('authorized' in x for x in report['issues'])

def test_missing_method_never_passes():
    rows=matrix();rows.pop()
    report=release_gate(rows,benchmark(),security())
    assert any('method approval missing' in x for x in report['issues'])

def test_malformed_benchmark_fails_closed():
    report=release_gate(matrix(),[{'foo':'bar'}],security())
    assert report['release_decision']=='BLOCKED'
    assert 'benchmark invalid' in report['issues']

def test_security_control_set_complete():
    assert len(SECURITY_CONTROLS)==10
    assert all(x in security() for x in SECURITY_CONTROLS)

def test_dns_rebinding_host_blocked():
    client=TestClient(app)
    r=client.get('/api/status',headers={'Host':'attacker.example'})
    assert r.status_code==403 and 'Untrusted Host' in r.text

def test_valid_local_host_allowed():
    assert TestClient(app).get('/api/status').status_code==200

def test_oversized_declared_request_blocked():
    r=TestClient(app).post('/api/extract',headers={'content-length':'6000000'},data={'consent':'false'})
    assert r.status_code==413

def test_preflight_never_claims_production(monkeypatch,tmp_path):
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'absent.sqlite3'))
    report=preflight()
    assert report['production_ready'] is False
    assert report['production_blockers']
    assert any('No initialized' in x for x in report['local_issues'])

def test_preflight_local_audit_with_users(monkeypatch,tmp_path):
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'test.sqlite3'))
    pilot.create_user('workerx','technician','PasswordForLocalTest!')
    pilot.create_user('reviewx','engineer','PasswordForLocalTest!')
    report=preflight()
    assert report['local_issue_count']==0
    assert report['observations']['audit_ok'] is True
    assert report['production_ready'] is False


def test_separate_signed_checkpoint_validates_and_detects_tamper(monkeypatch,tmp_path):
    from server.audit_anchor import create_keypair,make_checkpoint,verify_checkpoint
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'db.sqlite3'))
    pilot.create_user('labtech','technician','AnotherTestPassword!')
    pilot.create_user('labengineer','engineer','AnotherTestPassword!')
    key=tmp_path/'outside-db-key.pem';pub=tmp_path/'public.pem';attest=tmp_path/'checkpoint.json'
    create_keypair(key,pub,'long-passphrase-testing')
    if __import__('os').name=='posix':
        assert key.stat().st_mode & 0o077 == 0
    make_checkpoint(key,'long-passphrase-testing',attest)
    assert verify_checkpoint(pub,attest)['db_matches_signed_checkpoint'] is True
    # Even rewriting a whole audit chain cannot reproduce the already signed checkpoint.
    with pilot.transaction() as con:
        pilot.append_audit(con,'labtech','MANUAL_TEST_MARKER','-',{})
    assert verify_checkpoint(pub,attest)['db_matches_signed_checkpoint'] is False


def test_signed_checkpoint_payload_tamper_fails(monkeypatch,tmp_path):
    from server.audit_anchor import create_keypair,make_checkpoint,verify_checkpoint
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'db.sqlite3'))
    pilot.create_user('labtech','technician','AnotherTestPassword!')
    key=tmp_path/'key.pem';pub=tmp_path/'public.pem';attest=tmp_path/'checkpoint.json'
    create_keypair(key,pub,'long-passphrase-testing')
    make_checkpoint(key,'long-passphrase-testing',attest)
    obj=json.loads(attest.read_text());obj['payload']['record_count']+=1
    attest.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='signature invalid'):verify_checkpoint(pub,attest)


def test_signed_checkpoint_never_overwrites_existing_keys(tmp_path):
    from server.audit_anchor import create_keypair
    key=tmp_path/'key.pem';pub=tmp_path/'public.pem'
    create_keypair(key,pub,'long-passphrase-testing')
    with pytest.raises(FileExistsError):create_keypair(key,pub,'long-passphrase-testing')
