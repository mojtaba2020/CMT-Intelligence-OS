"""Synthetic-only testing: no employer photos or external OCR calls."""
import io
import json
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from forms.local_ocr_v19 import ocr_lines, open_image, infer_candidates, to_capture, MAX_IMAGE_BYTES
from forms.capture_v18 import stage
from server.app import app

SAMPLE=Path(__file__).resolve().parents[1]/'forms/examples/SYNTHETIC_PRINTED_CONCRETE_V19.png'
client=TestClient(app)
HEADER={'X-CMT-Local-OCR':'explicit-local-demo'}

def pixels(fmt='PNG',size=(300,200)):
    im=Image.new('RGB',size,'white');o=io.BytesIO();im.save(o,format=fmt);return o.getvalue()

def example_data():
    return {'text':['Project:','SYN-1','Slump:','4.5','Air','Content:','5.2','Wet','Density:','125'],
            'conf':['95']*10,'left':[1,81,1,82,1,47,170,1,65,170],'top':[1,1,45,45,85,85,85,125,125,125],
            'width':[72,80,70,75,42,113,70,60,100,70],'height':[18]*10,
            'block_num':[1]*10,'par_num':[1]*10,'line_num':[1,1,2,2,3,3,3,4,4,4]}

def test_ocr_engine_injected_no_network_with_real_boxes():
    p=ocr_lines(pixels(),engine=lambda im:example_data())
    assert len(p['lines'])==4
    assert p['lines'][0]['text']=='Project: SYN-1'
    assert p['engine']=='local-tesseract' and len(p['image_sha256'])==64
    assert all(len(x['box'])==4 for x in p['lines'])

def test_inference_is_conservative_and_table_is_not_guessed():
    p=ocr_lines(pixels(),engine=lambda im:example_data())
    con=infer_candidates(p,'concrete_strength')
    assert {x['key'] for x in con}=={'project_key','slump_in','air_percent'}
    density=infer_candidates(p,'density_sheet')
    # Wet density is not inferred from free text to a particular soil test row.
    assert len(density)==1 and density[0]['key']=='project_key'
    assert not density[0]['reviewed']

def test_bad_ambiguous_date_not_silently_resolved():
    p={'lines':[{'id':'line-1','text':'Date: 10/11/26','confidence':.99,'box':[0,0,100,20]}]}
    assert infer_candidates(p,'concrete_strength')==[]

def test_duplicate_field_values_do_not_masquer_as_two_observations():
    p={'lines':[{'id':'line-1','text':'Slump: 4.5','confidence':.9,'box':[0,0,10,10]},
                {'id':'line-2','text':'Slump: 5.0','confidence':.9,'box':[0,50,10,10]}]}
    c=infer_candidates(p,'concrete_strength')
    assert len(c)==1 and c[0]['value']=='4.5'

def test_capture_never_auto_reviews_or_runs_engineering_screen():
    p=ocr_lines(pixels(),engine=lambda im:example_data())
    cap=to_capture(p,form_type='concrete_strength',source_id='SYN-1',project_key='SYN-1',work_date='2026-10-26')
    f=cap['documents'][0]['fields']
    assert all(x['reviewed'] is False and not x['reviewer_ref'] for x in f)
    assert stage(cap)['ready_for_screening'] is False
    assert {x['key'] for x in f}>={'project_key','work_date'}

def test_authorized_without_permission_blocks():
    p={'lines':[]}
    with pytest.raises(ValueError,match='permission'):
        to_capture(p,form_type='concrete_strength',source_id='SYN',project_key='SYN',work_date='2026-10-26',data_mode='authorized')

def test_capture_duplicate_and_made_up_source_rejected():
    p={'lines':[{'id':'line-1','text':'Slump: 4.5','confidence':.9,'box':[0,0,10,10]}]}
    sel=[{'key':'slump_in','value':'4.5','line_id':'line-1'}]
    with pytest.raises(ValueError,match='Source line'):
        to_capture(p,form_type='concrete_strength',source_id='SYN',project_key='SYN',work_date='2026-10-26',selections=[{'key':'slump_in','value':'4.5','line_id':'invented'}])
    with pytest.raises(ValueError,match='duplicate'):
        to_capture(p,form_type='concrete_strength',source_id='SYN',project_key='SYN',work_date='2026-10-26',selections=sel*2)

def test_malformed_images_rejected():
    with pytest.raises(ValueError):open_image(b'not a real image')
    with pytest.raises(ValueError):open_image(b'x'*(MAX_IMAGE_BYTES+1))
    with pytest.raises(ValueError):open_image(pixels('GIF'))
    with pytest.raises(ValueError):open_image(pixels(size=(20,20)))
    with pytest.raises(ValueError):open_image(pixels(size=(5000,4000)))

def test_ocr_unhelpful_or_out_of_bounds_words_discarded():
    data=example_data();data['left'][0]=-20;data['conf'][1]='nan';data['width'][2]=0
    res=ocr_lines(pixels(),engine=lambda im:data)
    assert len(res['lines'])==3  # invalid words are dropped, including the sole words on one line
    assert all(x['confidence']>=0 for x in res['lines'])

def test_request_requires_explicit_header_consent_and_local_origin():
    with SAMPLE.open('rb') as f:
        r=client.post('/api/local-ocr/extract',files={'file':('test.png',f,'image/png')},data={'consent':'true'})
    assert r.status_code==403
    with SAMPLE.open('rb') as f:
        r=client.post('/api/local-ocr/extract',files={'file':('test.png',f,'image/png')},headers=HEADER,data={'consent':'false'})
    assert r.status_code==400
    with SAMPLE.open('rb') as f:
        r=client.post('/api/local-ocr/extract',files={'file':('test.png',f,'image/png')},headers={**HEADER,'Origin':'https://evil.example'},data={'consent':'true'})
    assert r.status_code==403

def test_authorized_mode_requires_permission():
    with SAMPLE.open('rb') as f:
        r=client.post('/api/local-ocr/extract',files={'file':('test.png',f,'image/png')},headers=HEADER,
                      data={'consent':'true','data_mode':'authorized','authorization_attested':'false'})
    assert r.status_code==403

def test_real_local_tesseract_printed_synthetic_sample():
    pytest.importorskip('pytesseract')
    import shutil
    if not shutil.which('tesseract'):pytest.skip('Local Tesseract binary not installed in CI')
    output=ocr_lines(SAMPLE.read_bytes())
    found={x['key']:x['value'] for x in infer_candidates(output,'concrete_strength')}
    assert found=={'project_key':'SYNTHETIC-001','work_date':'2026-10-26',
                   'slump_in':'4.5','air_percent':'5.2','concrete_temp_f':'76'}

def test_screen_endpoint_fails_closed_until_reviewed():
    p=ocr_lines(pixels(),engine=lambda im:example_data())
    cap=to_capture(p,form_type='concrete_strength',source_id='SYN',project_key='SYN',work_date='2026-10-26')
    bad=client.post('/api/local-ocr/screen',headers=HEADER,json={'packet':cap})
    assert bad.status_code==200 and bad.json()['ready_for_screening'] is False
    cap['data_mode']='authorized';cap['authorization_attested']=True
    assert client.post('/api/local-ocr/screen',headers=HEADER,json={'packet':cap}).status_code==403

def test_local_workbench_and_image_route():
    assert client.get('/ocr-lab').status_code==200
    assert client.get('/api/local-ocr/example').status_code==200
    assert client.get('/api/local-ocr/example',headers={'host':'malicious.example'}).status_code==403

def test_same_origin_custom_local_port_is_allowed():
    same=TestClient(app,base_url='http://127.0.0.1:8185')
    with SAMPLE.open('rb') as f:
        r=same.post('/api/local-ocr/extract',files={'file':('synthetic.png',f,'image/png')},
                    headers={**HEADER,'Origin':'http://127.0.0.1:8185'},data={'consent':'true','form_type':'concrete_strength'})
    assert r.status_code==200
    assert len(r.json()['candidates'])==5
