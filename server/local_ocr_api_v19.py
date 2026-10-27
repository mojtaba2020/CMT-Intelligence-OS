"""Loopback-only local OCR laboratory. No persistence or third-party calls."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from forms.local_ocr_v19 import MAX_IMAGE_BYTES, ocr_lines, infer_candidates
from forms.capture_v18 import stage

router=APIRouter(tags=['local-ocr-v19'])
ROOT=Path(__file__).resolve().parents[1]


def local_request(request:Request,token:str|None):
    if request.client and request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(403,'Local loopback access only; do not deploy publicly')
    origin=request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Cross-origin requests are not permitted')
    if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'Cross-site request rejected')
    if token!='explicit-local-demo':raise HTTPException(403,'Explicit local OCR request header required')

@router.get('/ocr-lab')
def local_workbench(request:Request):
    if request.client and request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(403,'Local only')
    return FileResponse(ROOT/'forms'/'OCR_Review_v19.html',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'"})

@router.get('/api/local-ocr/example')
def sample_photo(request:Request):
    if request.client and request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(403,'Local only')
    return FileResponse(ROOT/'forms/examples/SYNTHETIC_PRINTED_CONCRETE_V19.png',headers={'Cache-Control':'no-store'})

@router.post('/api/local-ocr/extract')
async def local_extract(request:Request,file:UploadFile=File(...),form_type:str=Form('concrete_strength'),
                        data_mode:str=Form('synthetic'),authorization_attested:str=Form('false'),
                        consent:str=Form('false'), x_cmt_local_ocr:str|None=Header(None)):
    local_request(request,x_cmt_local_ocr)
    if consent!='true':raise HTTPException(400,'Explicit local OCR consent required')
    if data_mode not in ('synthetic','authorized'):raise HTTPException(400,'Invalid data mode')
    if data_mode=='authorized' and authorization_attested!='true':
        raise HTTPException(403,'Permission from data owner required; no unauthorized employer material')
    try:
        # Check form before image processing
        if form_type not in ('density_sheet','concrete_strength','general_report','rebar_observation'):
            raise ValueError('Unknown form type')
        data=await file.read(MAX_IMAGE_BYTES+1)
        result=ocr_lines(data)
        result['candidates']=infer_candidates(result,form_type)
        result['form_type']=form_type
        result['data_mode']=data_mode
        result['notice']='Transcription proposals only. Human comparison against each original mandatory.'
        return result
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc

class CapturePayload(BaseModel):
    packet:dict

@router.post('/api/local-ocr/screen')
def local_screen(request:Request, body:CapturePayload,x_cmt_local_ocr:str|None=Header(None)):
    local_request(request,x_cmt_local_ocr)
    # This public/demo route can never process confidential real case data.
    if body.packet.get('data_mode')!='synthetic':raise HTTPException(403,'Screening lab accepts synthetic packets only')
    try:return stage(body.packet)
    except (ValueError,OverflowError,TypeError) as exc:raise HTTPException(400,str(exc)) from exc
