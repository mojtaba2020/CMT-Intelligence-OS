from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parent.parent
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1450,'height':1080},device_scale_factor=1)
    errs=[]
    page.on('pageerror',lambda e:errs.append(str(e)))
    page.evaluate("""() => {window.__storage={};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>window.__storage[k]??null,setItem:(k,v)=>window.__storage[k]=v}})}""")
    page.set_content((BASE/'index.html').read_text(),wait_until='load')
    page.locator('button[data-page="reconcile"]').click()
    page.locator('#evDemoMismatch').click()
    page.locator('#evCompare').click()
    assert '1 discrepancy' in page.locator('#evMessage').inner_text()
    page.screenshot(path=str(BASE/'preview.png'),full_page=True)
    assert not errs,errs
    browser.close()
print('Preview generated')
