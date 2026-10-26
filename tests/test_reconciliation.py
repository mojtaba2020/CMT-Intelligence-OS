from pathlib import Path
from playwright.sync_api import sync_playwright
import json
BASE=Path(__file__).resolve().parent.parent

def test_reconciliation_browser():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1400,'height':1050},accept_downloads=True)
        errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.evaluate("""() => {window.__storage={};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>window.__storage[k]??null,setItem:(k,v)=>{window.__storage[k]=v},clear:()=>{window.__storage={}}}})}""")
        page.set_content(BASE.joinpath('index.html').read_text(),wait_until='load')
        assert page.locator('#total').inner_text()=='2'
        assert page.locator('#pending').inner_text()=='2'
        # deterministic test for normalized gauge values + matching independent specification
        page.locator('button[data-page="reconcile"]').click()
        assert 'DEMO-S-001' in page.locator('#evRecord').inner_text()
        page.locator('#evTicket').fill('GAUGE-DEMO-01')
        page.locator('#evSpec').fill('DEMO-SPEC-REV-A')
        page.locator('#evDensity').fill('126')
        page.locator('#evMoisture').fill('11.8')
        page.locator('#evMDD').fill('120')
        page.locator('#evMinComp').fill('95')
        page.locator('#evProctor').fill('DEMO-PROCTOR-01')
        page.locator('#evProject').fill('DEMO-001')
        page.locator('#evLocation').fill('Area A / lift 2')
        page.locator('#evCompare').click()
        assert '0 discrepancy(s)' in page.locator('#evMessage').inner_text()
        assert 'MATCHED' in page.locator('#evResults').inner_text()
        # missing references should never produce authenticated/accepted results
        assert 'below the separately transcribed' in page.locator('#evResults').inner_text()
        page.locator('#evAttach').click()
        assert page.locator('#pending').inner_text()=='2'
        assert page.locator('#approved').inner_text()=='0'
        assert 'remains PENDING' in page.locator('#evMessage').inner_text()
        page.locator('button[data-page="queue"]').click()
        # select DEMO-S-001 specifically
        page.locator('#records article').filter(has_text='DEMO-S-001').locator('button').click()
        assert 'NDG evidence comparison' in page.locator('#detail').inner_text()
        assert 'MATCHED_WITH_GAPS' in page.locator('#detail').inner_text()
        # cross-source wet density mismatches are flagged but do not rewrite field data
        page.locator('button[data-page="reconcile"]').click()
        page.locator('#evDensity').fill('132')
        page.locator('#evCompare').click()
        assert '1 discrepancy(s)' in page.locator('#evMessage').inner_text()
        assert 'CONFLICT' in page.locator('#evResults').inner_text()
        page.locator('#evAttach').click()
        page.locator('button[data-page="queue"]').click()
        page.locator('#records article').filter(has_text='DEMO-S-001').locator('button').click()
        detail=page.locator('#detail').inner_text()
        assert 'Evidence reconciliation: 1 conflicting field' in detail
        assert 'Wet density' in detail and '126 pcf' in detail
        # independently sourced dry-density reading must normalize to same wet source
        page.locator('button[data-page="reconcile"]').click()
        page.locator('#evDensityType').select_option('dry')
        page.locator('#evDensity').fill(str(126/1.118))
        page.locator('#evCompare').click()
        assert '0 discrepancy(s)' in page.locator('#evMessage').inner_text()
        # conversion kg/m3 to pcf yields same comparison
        page.locator('#evDensityType').select_option('wet')
        page.locator('#evUnit').select_option('kgm3')
        page.locator('#evDensity').fill(str(126/0.0624279606))
        page.locator('#evCompare').click()
        assert '0 discrepancy(s)' in page.locator('#evMessage').inner_text()
        # incorrect proctor ref always creates a conflict
        page.locator('#evProctor').fill('PROCTOR-OTHER')
        page.locator('#evCompare').click()
        assert '1 discrepancy(s)' in page.locator('#evMessage').inner_text()
        # empty readings are blocked
        page.locator('#evDensity').fill('')
        page.locator('#evCompare').click()
        assert 'Cannot compare' in page.locator('#evMessage').inner_text()
        assert page.locator('#evAttach').is_disabled()
        # json export saves evidence snapshots and schema
        with page.expect_download() as file_info: page.locator('#exportJSON').click()
        payload=json.loads(Path(file_info.value.path()).read_text())
        assert payload['schema']==7
        soil=next(r for r in payload['records'] if r['id']=='DEMO-S-001')
        assert len(soil['evidenceChecks'])==2
        assert soil['data']['wet']==126
        assert soil['status']=='review'
        assert not errors,errors
        browser.close()

def test_migration_v03():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page()
        # Emulate earlier v0.3 browser storage, then verify migration to schema 4
        data={'schema':3,'records':[{'id':'OLD01','parentId':None,'version':1,'type':'soil','project':'X','tech':'Y','location':'Z','date':'2026-10-25T10:00','source':'Manual entry','evidence':'PAPER-1','specRef':'SPEC-A','data':{'wet':126,'moisture':11.8,'mdd':120,'minComp':95,'proctor':'P-01'},'results':{'dryDensity':112.7,'compaction':93.92},'flags':[],'status':'review','reviewer':'','note':''}], 'audit':[]}
        page.evaluate("""v => {window.__storage={'cmt-intelligence-os-v03':JSON.stringify(v)};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>window.__storage[k]??null,setItem:(k,v)=>{window.__storage[k]=v},clear:()=>{window.__storage={}}}})}""",data)
        page.set_content(BASE.joinpath('index.html').read_text(),wait_until='load')
        assert page.locator('#total').inner_text()=='1'
        assert page.evaluate('JSON.parse(localStorage.getItem("cmt-intelligence-os-v07")).schema')==7
        assert page.locator('#pending').inner_text()=='1'
        browser.close()
