"""Expanded multi-discipline catalog tests: synthetic values only; not ASTM conformance tests."""
from pathlib import Path
import json
import re
from playwright.sync_api import sync_playwright, expect

BASE = Path(__file__).resolve().parent.parent

def test_catalog_form_and_eng_review():
    html = (BASE / 'index.html').read_text()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 960}, accept_downloads=True)
        page.evaluate("""() => { window.__storage={}; Object.defineProperty(window,'localStorage', {configurable:true,value:{getItem:k=>window.__storage[k]??null,setItem:(k,v)=>window.__storage[k]=v}}) }""")
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.set_content(html, wait_until='load')
        page.locator('[data-page="catalog"]').click()
        assert page.locator('#catalogRows tr').count() == 15
        page.screenshot(path=str(BASE/'preview.png'), full_page=True)
        assert page.locator('#catalogRows').get_by_text('Cylinder compressive strength').count() == 1
        categories = ['soil_moisture','atterberg','proctor','sand_cone','sieve','cylinder','unit_weight','asphalt_core','asphalt_voids','rebar_cover']
        for category in categories:
            page.locator('[data-page="capture"]').click()
            page.locator('#testType').select_option(category)
            assert page.locator('#catalogFields').is_visible()
            # Project limit fields must never be filled with invented starter values.
            fields = page.evaluate("(t) => CATALOG[t].fields.map(f=>({key:f[0],optional:f[5]==='optional'}))", category)
            for field in fields:
                if field['optional']:
                    assert page.locator('#'+field['key']).input_value()==''
            before = int(page.locator('#total').inner_text())
            page.locator('#save').click()
            assert int(page.locator('#total').inner_text()) == before+1, category+' '+page.locator('#saveMsg').inner_text()
            assert page.locator('#detail').get_by_text('Indicative test method').count() == 1
            assert 'Review' in page.locator('#detail').inner_text() or 'Pending' in page.locator('#detail').inner_text()
        assert int(page.locator('#total').inner_text()) == 12
        # Calculation checks with clearly synthetic measurements.
        results = page.evaluate('''() => ({
          moisture:catalogCalculate('soil_moisture',{massWet:210,massDry:190,tare:90}).results.waterContent,
          pi:catalogCalculate('atterberg',{ll:42,pl:23,piMax:null}).results.plasticityIndex,
          sand:catalogCalculate('sand_cone',{excavatedMass:7.8,holeVolume:.0625,sandMoist:10,refMdd:115,sandMinComp:95}).results.compaction,
          sieve:catalogCalculate('sieve',{sampleMass:1000,retainedMass:225,passMin:null,passMax:null}).results.percentPassing,
          cylinder:catalogCalculate('cylinder',{breakLoad:62831.85,diameter:4,age:28,designStrength:null}).results.strengthPsi,
          unit:catalogCalculate('unit_weight',{fullMass:56,emptyMass:20.8,calVolume:.25,uwMin:null,uwMax:null}).results.unitWeightPcf,
          asphalt:catalogCalculate('asphalt_core',{dryCore:1160,ssdCore:1165,underCore:674,gmmCore:2.5,rcMin:null,rcMax:null}).results.relativeGmm,
          voids:catalogCalculate('asphalt_voids',{gmb:2.35,gmm:2.50,voidMin:null,voidMax:null}).results.airVoidsPercent
        })''')
        assert results['moisture']==20
        assert results['pi']==19
        assert abs(results['sand']-98.66) < 0.02
        assert results['sieve']==77.5
        assert abs(results['cylinder']-5000)<.1
        assert results['unit']==140.8
        assert abs(results['asphalt']-94.5)<.05
        assert results['voids']==6
        # Invalid physical data are blocked, without silently storing a record.
        page.locator('[data-page="capture"]').click()
        page.locator('#testType').select_option('soil_moisture')
        page.locator('#massWet').fill('185')
        before=int(page.locator('#total').inner_text())
        page.locator('#save').click()
        assert 'Wet mass must exceed dry mass' in page.locator('#saveMsg').inner_text()
        assert int(page.locator('#total').inner_text())==before
        # No auto-review/auto-approve for new categories.
        page.locator('#massWet').fill('220')
        page.locator('#save').click()
        assert page.locator('#approveRecord').is_visible()
        page.locator('#approveRecord').click()
        assert 'Enter a reviewer name' in page.locator('#reviewMsg').inner_text()
        # Optional threshold must evaluate a strict boundary with unrounded result.
        data = page.evaluate("""() => catalogCalculate('sieve',{sampleMass:1000,retainedMass:250.049,passMin:75,passMax:null})""")
        assert data['results']['percentPassing']==75
        assert len(data['flags'])==1, 'A rounded 75.00 must not hide a 74.9951 actual under-threshold reading'
        # Verify v0.5 backup migration into v0.6 (without deleting the old local keys).
        payload = json.loads(page.evaluate('JSON.stringify(db)'))
        payload['schema']=5
        migrated=page.evaluate('(p)=>migrate(p)',payload)
        assert migrated['schema']==7
        assert not errors,errors
        browser.close()


def test_catalog_csv_adapter():
    html=(BASE/'index.html').read_text()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page(accept_downloads=True)
        page.set_content(html)
        page.locator('[data-page="connector"]').click()
        # No vendor software needed; neutral CSV is just a review draft.
        csv=("type,project,tech,location,date,evidence,specRef,massWet,massDry,tare\n"
             "soil_moisture,DEMO-01,Tech,Site A,2026-10-25T09:00,TICKET-1,SPEC-A,210,190,90\n"
             "soil_moisture,DEMO-01,Tech,Site B,2026-10-25T09:00,TICKET-2,SPEC-A,100,190,90\n")
        page.locator('#csvFile').set_input_files({'name':'synthetic_catalog.csv','mimeType':'text/csv','buffer':csv.encode()})
        page.locator('#previewCSV').click()
        expect(page.locator('#csvMsg')).to_contain_text('1 valid draft(s), 1 rejected')
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#commitCSV').click()
        assert int(page.locator('#total').inner_text())==3
        assert page.locator('#detail').count()==1
        assert not page.locator('#detail').get_by_text('Reviewed',exact=True).count()
        browser.close()

def test_synthetic_multidiscipline_csv_import():
    """Verify the bundled five-category intake file is accepted as *drafts*, not approved results."""
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        page=browser.new_page()
        page.set_content((BASE/'index.html').read_text())
        page.locator('[data-page="connector"]').click()
        page.locator('#csvFile').set_input_files(str(BASE/'examples'/'synthetic_multitest_intake.csv'))
        page.locator('#previewCSV').click()
        expect(page.locator('#csvMsg')).to_contain_text('5 valid draft(s), 0 rejected')
        page.once('dialog',lambda dialog:dialog.accept())
        page.locator('#commitCSV').click()
        expect(page.locator('#total')).to_have_text('7')
        expect(page.locator('#approved')).to_have_text('0')
        browser.close()
