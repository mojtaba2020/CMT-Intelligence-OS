"""Generate a clearly synthetic, unsigned reviewed test worksheet using the actual local API."""
import os,json,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from server.app import app
from server import pilot
from server.report_verify import verify_report

with tempfile.TemporaryDirectory(prefix='cmt-v11-synthetic-') as td:
    os.environ['CMT_PILOT_DB']=str(Path(td)/'synthetic.sqlite3')
    pw='Synthetic-Sample-Password-Do-Not-Use!'
    pilot.create_user('demotech','technician',pw)
    pilot.create_user('demoreviewer','engineer',pw)
    tech=TestClient(app);eng=TestClient(app)
    def sign(c,user):
        r=c.post('/api/pilot/login',json={'username':user,'password':pw});r.raise_for_status()
        return r.json()['csrf']
    tc=sign(tech,'demotech');ec=sign(eng,'demoreviewer')
    headers=lambda csrf: {'X-CMT-CSRF':csrf}
    raw={'test_type':'soil','project_code':'SYNTHETIC-ONLY','location':'FICTIONAL-LIFT-01',
         'spec_reference':'DEMO-NOT-A-REAL-SPEC','evidence_reference':'FAKE-GAUGE-PRINT-002',
         'source':'synthetic','measurements':{'wet':126,'moisture':11.8,'mdd':120,'minComp':95,
                                             'density_unit':'pcf','mdd_unit':'pcf'}}
    created=tech.post('/api/pilot/records',json=raw,headers=headers(tc));created.raise_for_status()
    rid=created.json()['id']
    submitted=tech.post(f'/api/pilot/records/{rid}/submit',json={'expected_version':1},headers=headers(tc));submitted.raise_for_status()
    reviewed=eng.post(f'/api/pilot/records/{rid}/review',json={'expected_version':1,'decision':'reviewed',
       'note':'SYNTHETIC DEMONSTRATION: arithmetic and provenance references inspected. No real test or PE certification.'},headers=headers(ec));reviewed.raise_for_status()
    report=eng.get(f'/api/pilot/records/{rid}/report.json');report.raise_for_status()
    assert verify_report(report.json())['ok']
    output=Path(__file__).with_name('SYNTHETIC_REVIEW_WORKSHEET_UNCERTIFIED.json')
    output.write_text(json.dumps(report.json(),indent=2,ensure_ascii=False)+'\n')
    print('Generated',output.name,'status',report.json()['payload']['record']['status'],'checksum verified')
