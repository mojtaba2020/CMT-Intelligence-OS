"""Validation lab is synthetic until permissioned human verified data exist."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright, expect

HTML=Path(__file__).resolve().parent.parent.joinpath('index.html').read_text()


def app_page(browser):
    pg=browser.new_page(viewport={'width':1440,'height':950}, accept_downloads=True)
    errors=[]
    pg.on('pageerror',lambda error: errors.append(str(error)))
    pg.set_content(HTML)
    pg.locator('[data-page="validation"]').click()
    return pg,errors


def test_all_independent_synthetic_calculator_fixtures():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg,errors=app_page(browser)
        assert pg.locator('#fixtureSummary').inner_text().startswith('18/18')
        assert pg.locator('#fixtureRows tr').count()==18
        assert 'FAIL' not in pg.locator('#fixtureRows').inner_text()
        assert 'NOT' in pg.locator('#fixtureSummary').inner_text()
        assert not errors, errors
        browser.close()


def test_human_verified_field_matching_and_abstention():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg,errors=app_page(browser)
        pg.locator('#valCase').fill('CASE-A')
        pg.locator('#valGold').fill('126.00')
        pg.locator('#valPred').fill('126')
        pg.locator('#addLabel').click()
        assert pg.evaluate('pilotLabelMetrics(vdb.labels).correct')==1
        pg.locator('#valField').select_option('moisture')
        pg.locator('#valGold').fill('11.8')
        pg.locator('#valPred').fill('18.8')
        pg.locator('#addLabel').click()
        pg.locator('#valField').select_option('proctor_id')
        pg.locator('#valGold').fill('PROCTOR-X-01')
        pg.locator('#valPred').fill('')
        pg.locator('#addLabel').click()
        stats=pg.evaluate('pilotLabelMetrics(vdb.labels)')
        assert stats['total']==3 and stats['correct']==1
        assert stats['mismatched']==1 and stats['abstained']==1
        assert stats['criticalErrors']==2 and stats['criticalTotal']==3
        assert '33.3%' in pg.locator('#pilotMetrics').inner_text()
        assert not errors, errors
        browser.close()


def test_dataset_separation_and_paired_negative_time_saving():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg,errors=app_page(browser)
        pg.locator('#loadPilotDemo').click()
        dialog=None
        # Browser default dismisses confirm in these synthetic tests; force explicit accept below.
        # Rather than assuming the default, verify separation using JS insertion of synthetic examples.
        pg.evaluate('''()=>{vdb.labels.push({id:'S1',caseId:'SYN-1',field:'wet',gold:'120',pred:'119',tolerance:0,unit:'pcf',source:'synthetic'});renderPilot()}''')
        assert 'Not measured' in pg.locator('#pilotMetrics').inner_text()
        pg.locator('#timeCase').fill('CASE-1')
        pg.locator('#timeManual').fill('6.5')
        pg.locator('#timeAssist').fill('3')
        pg.locator('#timeCorrection').fill('1')
        pg.locator('#addTime').click()
        pg.locator('#timeCase').fill('CASE-2')
        pg.locator('#timeManual').fill('5')
        pg.locator('#timeAssist').fill('4')
        pg.locator('#timeCorrection').fill('2')
        pg.locator('#addTime').click()
        s=pg.evaluate("pilotTimeMetrics(vdb.pairs.filter(x=>x.source==='authorized'))")
        assert s['n']==2 and s['totalSaved']==1.5 and s['medianSaved']==0.75 and s['slower']==1
        pg.locator('#valSourceFilter').select_option('synthetic')
        assert pg.locator('#pilotMetrics').inner_text().count('Not measured')>=1
        assert not errors, errors
        browser.close()


def test_invalid_reference_and_bad_minutes_never_stored():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg,errors=app_page(browser)
        pg.locator('#valCase').fill('CASE-A')
        pg.locator('#valGold').fill('twelve')
        pg.locator('#valPred').fill('12')
        pg.locator('#addLabel').click()
        assert pg.evaluate('vdb.labels.length')==0
        pg.locator('#timeCase').fill('CASE-A')
        pg.locator('#timeManual').fill('-1')
        pg.locator('#timeAssist').fill('2')
        pg.locator('#timeCorrection').fill('0')
        pg.locator('#addTime').click()
        assert pg.evaluate('vdb.pairs.length')==0
        assert not errors, errors
        browser.close()


def test_export_pilot_only_and_app_review_records_unchanged():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg,errors=app_page(browser)
        before=pg.evaluate('JSON.stringify(db.records)')
        pg.locator('#valSource').select_option('synthetic')
        pg.locator('#valCase').fill('CASE-X')
        pg.locator('#valGold').fill('126')
        pg.locator('#valPred').fill('126')
        pg.locator('#addLabel').click()
        with pg.expect_download() as event:
            pg.locator('#exportPilot').click()
        data=json.loads(Path(event.value.path()).read_text())
        assert data['schema']==1 and len(data['labels'])==1 and data['labels'][0]['source']=='synthetic'
        assert 'records' not in data and 'photos' not in data
        assert pg.evaluate('JSON.stringify(db.records)')==before
        assert not errors,errors
        browser.close()
