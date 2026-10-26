"""Run: python -m pytest -q tests/test_api.py (does not contact OpenAI)."""
import io
import json
from PIL import Image
from fastapi.testclient import TestClient
from server import app as api

client=TestClient(api.app)

def fake_png():
    im=Image.new('RGB',(100,80),'white');out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()

def test_status_without_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    response=client.get('/api/status')
    assert response.status_code==200 and response.json()['configured'] is False

def test_extraction_requires_explicit_consent(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','sample-test-key')
    response=client.post('/api/extract',data={'type_hint':'soil','consent':'false'},files={'file':('x.png',fake_png(),'image/png')})
    assert response.status_code==400

def test_extraction_requires_api_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    response=client.post('/api/extract',data={'type_hint':'soil','consent':'true'},files={'file':('x.png',fake_png(),'image/png')})
    assert response.status_code==503

def test_extraction_rejects_invalid_image(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','sample-test-key')
    response=client.post('/api/extract',data={'type_hint':'soil','consent':'true'},files={'file':('x.png',b'not an image','image/png')})
    assert response.status_code==400

def test_parse_response_sanitizes_unexpected_keys():
    parsed=api.extract_message_content({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'document_type':'soil','fields':[{'key':'wet_density','value':'126'},{'key':'invented_acceptance','value':'Passed'}],'uncertain_fields':['wet ink'],'notes':'Review'})}]}]})
    assert parsed['fields']==[{'key':'wet_density','value':'126'}]
    assert parsed['uncertain_fields']==['wet ink']

def test_image_is_forwarded_only_with_opt_in(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','sample-test-key')
    class FakeResponse:
        status_code=200
        def raise_for_status(self): pass
        def json(self):
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'document_type':'concrete','fields':[{'key':'slump','value':'5.25'}],'uncertain_fields':[],'notes':'Verified sample'})}]}]}
    class FakeClient:
        def __init__(self,timeout): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,headers,json):
            assert url=='https://api.openai.com/v1/responses'
            assert json['store'] is False
            assert json['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,')
            return FakeResponse()
    monkeypatch.setattr(api.httpx,'AsyncClient',FakeClient)
    result=client.post('/api/extract',data={'type_hint':'concrete','consent':'true'},files={'file':('x.png',fake_png(),'image/png')})
    assert result.status_code==200
    assert result.json()['fields']==[{'key':'slump','value':'5.25'}]
