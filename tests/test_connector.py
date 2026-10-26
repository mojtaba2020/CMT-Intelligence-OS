"""Browser regression for the vendor-neutral CSV intake workflow (no external service)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import csv, io, json

BASE = Path(__file__).resolve().parents[1]
HTML = (BASE / 'index.html').read_text()


def test_csv_adapter():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1280,'height':900},accept_downloads=True)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.evaluate("""() => {window.__storage={};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>window.__storage[k]??null,setItem:(k,v)=>window.__storage[k]=v}})}""")
        page.set_content(HTML, wait_until='load')
        assert page.locator('#total').inner_text()=='2'
        assert page.locator('#specRef').input_value()==''
        # Exact-value acceptance check, not rounded threshold comparison.
        boundary=page.evaluate("() => evaluate('soil',{wet:94.996,moisture:0,mdd:100,minComp:95,proctor:'P1'})")
        assert boundary['results']['compaction']==95 and any('below' in f for f in boundary['flags'])
        validation=page.evaluate("() => inputErrors('soil',{wet:1e308,moisture:0,mdd:1,minComp:95,proctor:'P1'})")
        assert validation
        page.locator('button[data-page="connector"]').click()
        # The neutral template is downloadable and includes correctly identified units/fields.
        with page.expect_download() as info:
            page.locator('#templateCSV').click()
        template=list(csv.DictReader(io.StringIO(Path(info.value.path()).read_text())))
        assert len(template)==2 and template[0]['type']=='soil' and template[1]['type']=='concrete'
        assert 'specRef' in template[0] and 'minComp' in template[0]
        headers=['Test Type','Job Number','Inspector','Station','Test Date','Evidence','Spec Reference',
            'Wet Density pcf','Water Content','Max Dry Density','Required Compaction','Proctor Report',
            'Slump Inches','Min Slump','Max Slump','Air Content','Min Air','Max Air',
            'Concrete Temperature','Max Temp','Mix Number']
        soil=['soil','=2+2','Field Inspector','Lift A','2026-10-25T08:30','PHOTO-NDG-01','',
            '126','11.8','120','95','P-1','','','','','','','','','']
        # Duplicate in same file is advisory; never silently merged.
        repeated=soil.copy()
        concrete=['concrete','CMT-100','Field Inspector','Pour <img src=x onerror=alert(1)>',
            '2026-10-25T08:45','PHOTO-CONCRETE-01','C-REV-B','','','','','',
            '5.25','4','6','5.2','4','7','78','95','TR-12']
        invalid=soil.copy();invalid[1]='BAD';invalid[7]='0'
        buf=io.StringIO(newline='');writer=csv.writer(buf);writer.writerow(headers)
        for line in [soil,repeated,concrete,invalid]: writer.writerow(line)
        payload=buf.getvalue().encode('utf-8')
        page.locator('#csvFile').set_input_files({'name':'synthetic.csv','mimeType':'text/csv','buffer':payload})
        page.locator('#previewCSV').click()
        page.wait_for_function("document.querySelector('#csvMsg').textContent.includes('3 valid draft(s), 1 rejected')")
        assert page.locator('#total').inner_text()=='2', 'Preview must not mutate state'
        assert page.locator('#csvPreview img').count()==0
        assert '=2+2' in page.locator('#csvPreview').inner_text()
        assert page.locator('#commitCSV').is_enabled()
        page.on('dialog',lambda d:d.accept())
        page.locator('#commitCSV').click()
        assert page.locator('#total').inner_text()=='5'
        assert page.locator('#pending').inner_text()=='5'
        assert page.locator('#approved').inner_text()=='0'
        assert page.locator('#flags').inner_text()=='4' # 1 original failed demo + 3 imported drafts
        assert page.locator('#records img').count()==0
        assert 'NOT SUPPLIED' in page.locator('#detail').inner_text()
        # Import never changes acceptance statuses; all imports are drafts requiring review.
        with page.expect_download() as info:
            page.locator('#exportJSON').click()
        backup=json.loads(Path(info.value.path()).read_text())
        assert backup['schema']==7 and len(backup['records'])==5
        drafts=[r for r in backup['records'] if r['source']=='Mapped CSV draft (unverified)']
        assert len(drafts)==3 and all(r['status']=='review' for r in drafts)
        assert any('Pour <img src=x onerror=alert(1)>'==r['location'] for r in drafts)
        assert sum(any('duplicate' in f.lower() for f in r['flags']) for r in drafts)>=1
        assert sum(any('specification/revision reference is missing' in f for f in r['flags']) for r in drafts)==2
        # Spreadsheet-injection-safe CSV export: formula-like cell values are prefixed with an apostrophe.
        with page.expect_download() as info:
            page.locator('#exportCSV').click()
        exported=Path(info.value.path()).read_text()
        assert "'=2+2" in exported
        assert len([a for a in backup['audit'] if a['event']=='IMPORTED DRAFT'])==3
        assert not errors,errors
        browser.close()


def test_backup_migration():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page()
        # Seed v0.2 state in a minimal real browser localStorage substitute.
        legacy={'schema':2,'records':[{'id':'OLD-S','type':'soil','project':'LEGACY','tech':'Tech','location':'Lift 4','date':'2026-10-24T12:00',
            'source':'Manual entry','evidence':'FORM','data':{'wet':126,'moisture':11.8,'mdd':120,'minComp':95,'proctor':'P-1'},
            'results':{'dryDensity':112.7,'compaction':93.92},'flags':['Below required compaction'],'status':'review','reviewer':'','note':'','version':1,'parentId':None}],
            'audit':[]}
        page.evaluate("""() => {window.__storage={};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>window.__storage[k]??null,setItem:(k,v)=>window.__storage[k]=v}})}""")
        page.evaluate('(v)=>{window.__storage["cmt-intelligence-os-v02"]=JSON.stringify(v)}',legacy)
        page.set_content(HTML, wait_until='load')
        assert page.locator('#total').inner_text()=='1'
        page.locator('button[data-page="queue"]').click()
        assert 'NOT SUPPLIED' in page.locator('#detail').inner_text()
        assert 'specification/revision reference is missing' in page.locator('#detail').inner_text()
        with page.expect_download() as info: page.locator('#exportJSON').click()
        data=json.loads(Path(info.value.path()).read_text())
        assert data['schema']==7 and any(x['event']=='BACKUP MIGRATED' for x in data['audit'])
        assert data['records'][0]['id']=='OLD-S'
        browser.close()

if __name__=='__main__':
    test_csv_adapter();test_backup_migration();print('CSV adapter tests passed (mapped aliases, validation, preview, import, duplicates, XSS, migration, injection-safe export).')
