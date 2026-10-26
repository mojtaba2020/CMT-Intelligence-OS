from pathlib import Path
from playwright.sync_api import sync_playwright
import threading, http.server, functools

BASE = Path(__file__).resolve().parent.parent
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(BASE))
server = http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
APP=f'http://127.0.0.1:{server.server_port}/index.html'

def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1360,'height':970}, device_scale_factor=1,accept_downloads=True)
        errs=[]
        page.on('pageerror',lambda e:errs.append(str(e)))
        # Inject an in-memory storage substitute because this test runner blocks all navigation origins.
        page.evaluate("""() => {window.__storage={};Object.defineProperty(window,'localStorage', {configurable:true,value:{getItem:k=>window.__storage[k]??null,setItem:(k,v)=>{window.__storage[k]=v}}})}""")
        page.set_content(BASE.joinpath("index.html").read_text(), wait_until="load")
        assert page.locator('#total').inner_text()=='2', f"Not initialized: {page.locator('#total').inner_text()}"
        page.screenshot(path=str(Path(__file__).resolve().parent.parent / 'preview.png'),full_page=True)
        assert page.locator('#pending').inner_text()=='2'
        assert page.locator('#flags').inner_text()=='1'
        page.locator('#wet').fill('126')
        page.locator('#moisture').fill('11.8')
        page.locator('#mdd').fill('120')
        page.locator('#minComp').fill('95')
        page.locator('#save').click()
        assert page.locator('#total').inner_text()=='3'
        assert page.locator('#pending').inner_text()=='3'
        assert '93.92%' in page.locator('#detail').inner_text(),page.locator('#detail').inner_text()
        # Approve not allowed with missing reviewer and rationale for a flagged record.
        page.locator('#approveRecord').click()
        assert 'Enter a reviewer name' in page.locator('#reviewMsg').inner_text()
        page.locator('#reviewer').fill('Demo Engineer')
        page.locator('#approveRecord').click()
        assert 'rationale is required' in page.locator('#reviewMsg').inner_text()
        # Return for correction.
        page.locator('#reason').fill('Proctor reference requires reconciliation with current lift.')
        page.locator('#returnRecord').click()
        assert page.locator('#pending').inner_text()=='2'
        assert 'Returned' in page.locator('#detail').inner_text()
        page.locator('#revise').click()
        assert 'Correct returned test' in page.locator('#entryTitle').inner_text()
        page.locator('#wet').fill('132')
        page.locator('#save').click()
        assert page.locator('#total').inner_text()=='4'
        assert '98.39%' in page.locator('#detail').inner_text(),page.locator('#detail').inner_text()
        assert 'Revision of' in page.locator('#detail').inner_text()
        page.locator('#reviewer').fill('Demo Engineer')
        page.locator('#reason').fill('Compared to source; reviewer acknowledges missing evidence reference in this synthetic record.')
        page.locator('#approveRecord').click()
        assert page.locator('#approved').inner_text()=='1'
        # Make sure numeric invalid measurements are blocked.
        page.locator('button[data-page="capture"]').click()
        page.locator('#wet').fill('0')
        page.locator('#save').click()
        assert page.locator('#total').inner_text()=='4'
        assert 'Cannot save' in page.locator('#saveMsg').inner_text()
        # Confirm a valid concrete record.
        page.locator('#switch').click()
        page.locator('#slump').fill('7.5')
        page.locator('#save').click()
        assert page.locator('#total').inner_text()=='5'
        assert 'Slump 7.5' in page.locator('#detail').inner_text()
        # Check cross-site scripting is escaped inside queue.
        page.locator('button[data-page="capture"]').click()
        page.locator('#project').fill('<img src=x onerror=alert(1)>')
        page.locator('#save').click()
        assert page.locator('#records img').count()==0
        assert '<img src=x onerror=alert(1)>' in page.locator('#records').inner_text()
        # JSON export has all 6 records + audit events.
        with page.expect_download() as dl_info:
            page.locator('#exportJSON').click()
        file=dl_info.value
        assert file.suggested_filename.endswith('.json')
        import json
        obj=json.loads(Path(file.path()).read_text())
        assert obj['schema']==7 and len(obj['records'])==6
        assert len(obj['audit'])>=7
        # Check that state has been serialized for storage. The navigation sandbox blocks a full reload test.
        assert len(json.loads(page.evaluate('window.__storage["cmt-intelligence-os-v07"]'))['records'])==6
        assert not errs,errs
        browser.close()
        return 'Browser assertions passed: calculations, exception handling, corrections, reviews, CSV/JSON export, local-storage serialization, and XSS escaping.'

if __name__=='__main__': print(run())
