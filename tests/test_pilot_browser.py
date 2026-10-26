"""Chromium UI integration with actual FastAPI TestClient backing requests.
Container Chrome prohibits localhost navigation, so fetch is bridged through TestClient.
This verifies browser UI behavior and server auth rules but NOT transport-level cookies or HTTPS.
"""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from server import pilot
from server.app import app

ROOT=Path(__file__).resolve().parents[1]
PWD='Strong-Local-Test-Password-2026!'

@pytest.fixture
def backend(tmp_path,monkeypatch):
    monkeypatch.setenv('CMT_PILOT_DB',str(tmp_path/'pilot.sqlite3'))
    pilot.create_user('fieldtech','technician',PWD)
    pilot.create_user('labengineer','engineer',PWD)
    return TestClient(app)


def browser_page(browser,client):
    page=browser.new_page(viewport={'width':1440,'height':930},device_scale_factor=1)
    def server_call(url,opts):
        try:
            method=opts.get('method','GET')
            headers=opts.get('headers') or {}
            body=opts.get('body')
            result=client.request(method,url,headers=headers,content=body)
            return {'status':result.status_code,'body':result.json()}
        except Exception as exc:
            return {'status':500,'body':{'detail':str(exc)}}
    page.expose_function('pilotTestBackend',server_call)
    page.set_content((ROOT/'index.html').read_text())
    page.evaluate('''() => {const orig=window.fetch.bind(window);
      window.fetch=async(url,opts={})=>{
       if(String(url).startsWith('/api/pilot/')){
         const r=await window.pilotTestBackend(String(url),{method:opts.method||'GET',headers:opts.headers||{},body:opts.body||null});
         return new Response(JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':'application/json'}});
       }
       return orig(url,opts);
      }
    }''')
    page.locator('[data-page="securepilot"]').click()
    return page


def test_authenticated_workflow_in_chromium_ui(backend):
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg=browser_page(browser,backend)
        errors=[];pg.on('pageerror',lambda error:errors.append(str(error)))
        pg.locator('#pilotUser').fill('fieldtech')
        pg.locator('#pilotPass').fill(PWD)
        pg.locator('#pilotLogin').click()
        expect(pg.locator('#pilotSession')).to_contain_text('Signed in as fieldtech',timeout=10000)
        pg.locator('#pilotAuthorized').check()
        pg.locator('#pilotCreate').click()
        expect(pg.locator('#pilotSelected')).to_contain_text('draft',timeout=10000)
        pg.locator('#pilotSubmit').click()
        expect(pg.locator('#pilotSelected')).to_contain_text('submitted',timeout=10000)
        rid=pg.locator('#pilotSelected').inner_text().split(' · ')[0]
        pg.locator('#pilotLogout').click()
        expect(pg.locator('#pilotSession')).to_contain_text('Signed out',timeout=10000)
        pg.locator('#pilotUser').fill('labengineer')
        pg.locator('#pilotPass').fill(PWD)
        pg.locator('#pilotLogin').click()
        expect(pg.locator('#pilotSession')).to_contain_text('Signed in as labengineer',timeout=10000)
        expect(pg.locator('#pilotRecords')).to_contain_text(rid)
        pg.locator('#pilotRecords button').first.click()
        pg.locator('#pilotDecision').select_option('reviewed')
        pg.locator('#pilotNote').fill('Source specifications checked independently; synthetic training only.')
        pg.locator('#pilotReview').click()
        expect(pg.locator('#pilotSelected')).to_contain_text('reviewed',timeout=10000)
        pg.locator('#pilotAudit').click()
        expect(pg.locator('#pilotIntegrity')).to_contain_text('"ok": true',timeout=10000)
        assert not errors,errors
        browser.close()


def test_capture_pilot_preview(backend):
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg=browser_page(browser,backend)
        pg.screenshot(path=str(ROOT/'preview_pilot.png'),full_page=True)
        browser.close()

# v1.0: E2E server-side data quality report is visible in existing role-based UI.
def test_quality_preflight_from_browser(backend):
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg=browser_page(browser,backend)
        pg.locator('#pilotUser').fill('fieldtech');pg.locator('#pilotPass').fill(PWD)
        pg.locator('#pilotLogin').click()
        expect(pg.locator('#pilotSession')).to_contain_text('Signed in as fieldtech',timeout=10000)
        pg.locator('#pilotAuthorized').check()
        pg.locator('#pilotMeasurements').fill('{"wet":-5,"moisture":11.8,"mdd":120}')
        pg.locator('#pilotPreviewQA').click()
        expect(pg.locator('#pilotQAStatus')).to_contain_text('NOT eligible to submit',timeout=10000)
        expect(pg.locator('#pilotQAReport')).to_contain_text('OUT_OF_DOMAIN')
        pg.locator('#pilotMeasurements').fill('{"wet":126,"moisture":11.8,"mdd":120,"minComp":95}')
        pg.locator('#pilotPreviewQA').click()
        expect(pg.locator('#pilotQAStatus')).to_contain_text('eligible for human review',timeout=10000)
        expect(pg.locator('#pilotQAReport')).to_contain_text('BELOW_USER_THRESHOLD')
        pg.locator('#pilotCreate').click()
        expect(pg.locator('#pilotSelected')).to_contain_text('draft',timeout=10000)
        pg.locator('#pilotCheckSelected').click()
        expect(pg.locator('#pilotQAReport')).to_contain_text('Illustrative calculations',timeout=10000)
        browser.close()
