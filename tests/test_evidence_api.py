"""No API calls are made; fake provider responses test refusal, scoping, and image integrity."""
import io, json, hashlib
from PIL import Image
from fastapi.testclient import TestClient
from server import app as api

client=TestClient(api.app)

def png():
    im=Image.new('RGB',(70,80),'white'); out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()

def test_parsing_scopes_and_normalizes():
    sample={"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":json.dumps({
        "source_type":"gauge_printout", "fields":[
            {"key":"density","value":"132"},{"key":"density","value":"126"},
            {"key":"minComp","value":"95"},{"key":"density_unit","value":"tbd"},
            {"key":"ticket","value":"NDG-41"}], "uncertain_fields":["print fuzzy"],"notes":"Check image"})}]}]}
    x=api.parse_evidence_response(sample,'gauge_printout')
    assert x['fields']==[{"key":"density","value":"132"},{"key":"ticket","value":"NDG-41"}]
    assert len(x['uncertain_fields'])==1
    try:
        api.parse_evidence_response(sample,'proctor_spec')
        assert False,'must fail if provider relabels document source'
    except ValueError: pass

def test_evidence_upload_consent_and_key(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','fake')
    b=png()
    assert client.post('/api/evidence/extract',data={'source_kind':'gauge_printout','consent':'false'},files={'file':('test.png',b,'image/png')}).status_code==400
    assert client.post('/api/evidence/extract',data={'source_kind':'unknown','consent':'true'},files={'file':('test.png',b,'image/png')}).status_code==400
    assert client.post('/api/evidence/extract',headers={'Origin':'https://untrusted.example','Host':'testserver'},data={'source_kind':'gauge_printout','consent':'true'},files={'file':('test.png',b,'image/png')}).status_code==403
    monkeypatch.delenv('OPENAI_API_KEY')
    assert client.post('/api/evidence/extract',data={'source_kind':'gauge_printout','consent':'true'},files={'file':('test.png',b,'image/png')}).status_code==503

def test_evidence_no_file_storage_and_sha256(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','fake-test-key')
    image_bytes=png()
    class FakeResponse:
        status_code=200
        def raise_for_status(self): pass
        def json(self):
            return {"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":json.dumps({
                "source_type":"proctor_spec","fields":[{"key":"mdd","value":"120"},{"key":"minComp","value":"95"},{"key":"proctor","value":"P-42"},{"key":"spec","value":"S-1"}],
                "uncertain_fields":[],"notes":"Draft only"})}]}]}
    class FakeClient:
        def __init__(self,timeout): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,headers,json):
            assert url=='https://api.openai.com/v1/responses'
            assert json['store'] is False
            assert 'minComp' in json['input'][0]['content'][0]['text']
            assert json['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,')
            return FakeResponse()
    monkeypatch.setattr(api.httpx,'AsyncClient',FakeClient)
    ans=client.post('/api/evidence/extract',data={'source_kind':'proctor_spec','consent':'true'},files={'file':('test.png',image_bytes,'image/png')})
    assert ans.status_code==200,ans.text
    data=ans.json();assert data['approved'] is False and data['source_sha256']==hashlib.sha256(image_bytes).hexdigest()
    assert data['mode']=='live_ai_draft' and 'mdd' in [v['key'] for v in data['fields']]
