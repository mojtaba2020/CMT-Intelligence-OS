"""Scenario tests for laboratory workbenches with SYNTHETIC measurements only."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import math
import json
ROOT=Path(__file__).resolve().parent.parent
HTML=(ROOT/'index.html').read_text()

def get_page(browser):
    pg=browser.new_page(accept_downloads=True, viewport={'width':1440,'height':900})
    errs=[];pg.on('pageerror',lambda e:errs.append(str(e)))
    pg.set_content(HTML)
    pg.locator('[data-page="advanced"]').click()
    return pg,errs

def test_three_workbenches_end_to_end():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg,errs=get_page(browser)
        for t,expected in [('proctor_curve','123.89'),('sieve_stack','1000'),('cylinder_set','5066.42')]:
            pg.locator('#advType').select_option(t)
            assert expected in pg.locator('#advSummary').inner_text()
            assert pg.locator('#advChart svg').count()==1
            before=int(pg.locator('#total').inner_text())
            pg.locator('#advSave').click()
            expect(pg.locator('#total')).to_have_text(str(before+1))
            assert pg.evaluate("db.records[0].status")=='review'
            assert pg.evaluate("db.records[0].data.points.length")>=3
            expect(pg.locator('#approveRecord')).to_be_visible()
            pg.locator('[data-page="advanced"]').click()
        assert not errs, errs
        # All array measurements round-trip in JSON backups.
        with pg.expect_download() as dl:
            pg.locator('#exportJSON').click()
        js=json.loads(Path(dl.value.path()).read_text())
        assert js['schema']==7
        assert {r['type'] for r in js['records']}>=set(['proctor_curve','sieve_stack','cylinder_set'])
        assert all(r['status']=='review' for r in js['records'] if r['type'] in ['proctor_curve','sieve_stack','cylinder_set'])
        browser.close()

def test_proctor_boundary_and_no_silent_estimate():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox']);pg,errs=get_page(browser)
        ans=pg.evaluate('''()=>{
           let d=advTemplate('proctor_curve');
           d.points=[{moisture:5,wet:140},{moisture:7,wet:139},{moisture:9,wet:136},{moisture:11,wet:130}];
           return calcAdvanced('proctor_curve',d);
        }''')
        assert 'illustrativePeakMdd' not in ans['results']
        assert any('end point' in f for f in ans['flags'])
        pg.locator('#advRows tr').first.locator('[data-field="wet"]').fill('-5')
        expect(pg.locator('#advSummary')).to_contain_text('Fix before saving')
        count=int(pg.locator('#total').inner_text())
        pg.locator('#advSave').click()
        assert int(pg.locator('#total').inner_text())==count
        assert not errs, errs
        browser.close()

def test_sieve_mass_balance_and_strict_gradation_limit():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox']);pg,errs=get_page(browser)
        d=pg.evaluate('''()=>{
           const d=advTemplate('sieve_stack');
           d.points[1].min=74.1; // actual passing is exactly 74.00%, strictly below 74.1
           d.points[d.points.length-1].mass=45; // loss of 15 g = 1.5% (>0.5%)
           return calcAdvanced('sieve_stack',d);
        }''')
        assert d['results']['massDifferencePct']==1.5
        assert len([f for f in d['flags'] if 'outside entered' in f])==1
        assert any('Mass-balance' in f for f in d['flags'])
        pg.locator('#advType').select_option('sieve_stack')
        pg.locator('#advRows tr').nth(1).locator('[data-field="mm"]').fill('25')
        expect(pg.locator('#advSummary')).to_contain_text('strictly descending')
        assert not errs,errs
        browser.close()

def test_cylinder_age_and_specimen_count_review():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox']);pg,errs=get_page(browser)
        ans=pg.evaluate('''()=>{
           const d=advTemplate('cylinder_set'); d.points.pop();
           d.points[1].age=7;
           return calcAdvanced('cylinder_set',d);
        }''')
        assert ans['results']['setMeanPsi'] is None
        assert any('differing ages' in f for f in ans['flags'])
        assert any('≥3' in f for f in ans['flags'])
        good=pg.evaluate('''()=>{
           const d=advTemplate('cylinder_set');return calcAdvanced('cylinder_set',d).results;
        }''')
        assert 5000<good['setMeanPsi']<5200
        assert not errs,errs
        browser.close()

def test_return_revision_and_export_csv():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox']);pg,errs=get_page(browser)
        pg.locator('#advType').select_option('sieve_stack');pg.locator('#advSave').click()
        original=pg.evaluate('db.records[0].id')
        pg.locator('#reviewer').fill('Demo Reviewer');pg.locator('#reason').fill('Sample sheet needs corroboration.');pg.locator('#returnRecord').click()
        pg.locator('#revise').click()
        assert 'Correction v2' in pg.locator('#advRevision').inner_text()
        pg.locator('#advEvidence').fill('DEMO-WEIGHING-LOG')
        pg.locator('#advSpecRef').fill('DEMO-SPEC-REV-B')
        pg.locator('#advSave').click()
        record=pg.evaluate('db.records[0]')
        assert record['version']==2 and record['parentId']==original
        assert pg.evaluate('db.records.find(r=>r.id==='+json.dumps(original)+').replacedBy')==record['id']
        assert record['status']=='review'
        with pg.expect_download() as dl:pg.locator('#exportCSV').click()
        csv=Path(dl.value.path()).read_text()
        assert 'advancedPointsJSON' in csv and 'DEMO-AGG-01' not in csv # sample metadata stored in backup JSON only
        assert 'sieve_stack' in csv
        assert not errs,errs
        browser.close()

def test_corrupted_advanced_backup_rejected():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox']);pg,errs=get_page(browser)
        pg.locator('#advSave').click()
        record=pg.evaluate('JSON.parse(JSON.stringify(db.records[0]))')
        record['data']['points']=[{'moisture':9,'wet':120}] # invalid one-point curve
        assert pg.evaluate('(r)=>isRecord(r)',record) is False
        record['data']['points']=None
        assert pg.evaluate('(r)=>isRecord(r)',record) is False
        assert not errs,errs
        browser.close()
