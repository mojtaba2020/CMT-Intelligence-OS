"""Reproducible SYNTHETIC quality screen screenshot via in-process FastAPI test bridge."""
import os
from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from server import pilot
from server.app import app
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    os.environ['CMT_PILOT_DB']=str(Path(temp)/'synthetic_preview.sqlite3')
    import secrets
    password='Preview-'+secrets.token_urlsafe(24)
    pilot.create_user('techdemo','technician',password)
    client=TestClient(app)
    with sync_playwright() as play:
        b=play.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        p=b.new_page(viewport={'width':1300,'height':1000},device_scale_factor=1)
        def call(url,opts):
            res=client.request(opts.get('method','GET'),url,headers=opts.get('headers') or {},content=opts.get('body'))
            return {'status':res.status_code,'body':res.json()}
        p.expose_function('pilotTestBackend',call)
        p.set_content((ROOT/'index.html').read_text())
        p.evaluate('''() => {const original=window.fetch.bind(window);window.fetch=async(url,opts={})=>{if(String(url).startsWith('/api/pilot/')){const r=await window.pilotTestBackend(String(url),{method:opts.method||'GET',headers:opts.headers||{},body:opts.body||null});return new Response(JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':'application/json'}})}return original(url,opts)}}''')
        p.locator('[data-page="securepilot"]').click()
        p.locator('#pilotUser').fill('techdemo');p.locator('#pilotPass').fill(password);p.locator('#pilotLogin').click()
        p.locator('#pilotAuthorized').check()
        p.locator('#pilotPreviewQA').click()
        p.locator('#pilotQAReport').get_by_text('BELOW_USER_THRESHOLD').wait_for(timeout=5000)
        p.locator('#pilotQAReport').screenshot(path=str(ROOT/'preview_quality_report.png'))
        p.screenshot(path=str(ROOT/'preview_quality_full.png'),full_page=True)
        b.close()
