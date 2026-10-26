"""End-to-end synthetic photo workflow: explicit verification, no autonomous acceptance."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def test_photo_workbench_evidence_chain():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1400,'height':900},accept_downloads=True)
        issues=[]
        page.on('pageerror',lambda error:issues.append(str(error)))
        page.evaluate("""() => {window.__storage={};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>window.__storage[k]??null,setItem:(k,v)=>{window.__storage[k]=v}}})}""")
        page.set_content(ROOT.joinpath('index.html').read_text(),wait_until='load')
        page.locator('button[data-page="photo"]').click()
        assert 'DEMO-S-001' in page.locator('#photoRecord').inner_text()
        # Loaded fictional data is NOT read from image and requires confirmation.
        page.locator('#photoDemoGauge').click()
        assert 'SYNTHETIC DEMO' in page.locator('#photoSourceNote').inner_text()
        page.locator('#photoApply').click()
        assert 'independently check' in page.locator('#photoApplyStatus').inner_text()
        assert page.locator('#evDensity').input_value()==''
        for checkbox in page.locator('#photoRows input[type=checkbox]').all(): checkbox.check()
        page.locator('#photoApply').click()
        assert page.locator('#evDensity').input_value()=='132'
        assert 'DEMO' in page.locator('#photoApplyStatus').inner_text()
        # Altered draft field clears verification.
        page.locator('#photoDemoSpec').click()
        page.locator('#photoRows tr[data-key="mdd"] input:not([type=checkbox])').fill('121')
        assert not page.locator('#photoRows tr[data-key="mdd"] input[type=checkbox]').is_checked()
        page.locator('#photoApply').click()
        assert 'independently check' in page.locator('#photoApplyStatus').inner_text()
        # Reload correctly matched synthetic specification, verify manually.
        page.locator('#photoDemoSpec').click()
        for checkbox in page.locator('#photoRows input[type=checkbox]').all(): checkbox.check()
        page.locator('#photoApply').click()
        assert page.locator('#evMDD').input_value()=='120'
        assert 'gauge_printout:' in page.locator('#photoApplied').inner_text()
        assert 'proctor_spec:' in page.locator('#photoApplied').inner_text()
        page.locator('button[data-page="reconcile"]').click()
        page.locator('#evCompare').click()
        assert '1 discrepancy(s)' in page.locator('#evMessage').inner_text()
        assert 'Synthetic training source' in page.locator('#evResults').inner_text()
        page.locator('#evAttach').click()
        assert page.locator('#approved').inner_text()=='0'
        page.locator('button[data-page="queue"]').click()
        page.locator('#records article').filter(has_text='DEMO-S-001').locator('button').click()
        assert 'Photo provenance: gauge_printout' in page.locator('#detail').inner_text()
        assert 'Synthetic training source' in page.locator('#detail').inner_text() or 'Evidence reconciliation' in page.locator('#detail').inner_text()
        with page.expect_download() as info: page.locator('#exportJSON').click()
        backup=json.loads(Path(info.value.path()).read_text())
        test=next(r for r in backup['records'] if r['id']=='DEMO-S-001')
        assert test['status']=='review' and test['data']['wet']==126
        assert len(test['evidenceChecks'][-1]['provenance'])==2
        assert all(x['mode']=='synthetic' and x['source_sha256'] is None for x in test['evidenceChecks'][-1]['provenance'])
        # Modification after human check MUST invalidate the photo provenance.
        page.locator('button[data-page="reconcile"]').click()
        page.locator('#evDensity').fill('126')
        page.locator('#evCompare').click()
        assert 'changed after verification' in page.locator('#evResults').inner_text()
        assert not issues,issues
        browser.close()
