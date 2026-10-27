"""Local, opt-in, fail-closed OCR staging for neutral CMT form categories.

No network calls, no persistence, no auto approval, no official ElmTree output.
Tesseract confidence is a diagnostic signal, NOT calibrated extraction accuracy.
Dense handwritten tables are returned as spatially located OCR *lines* only.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from io import BytesIO
import hashlib
import math
import re
from typing import Any
from PIL import Image, ImageOps, UnidentifiedImageError

from forms.capture_v18 import VERSION, DICT

MAX_IMAGE_BYTES=4_000_000
MAX_PIXELS=16_000_000
MAX_LINES=350
ALLOWED_FORMATS={'PNG','JPEG','WEBP'}
ALLOWED_TYPES=set(DICT['forms'])

# Intentionally few high-precision SAME-LINE LABEL patterns: not broad handwriting guesses.
LABELS = {
    'project_key': re.compile(r'^\s*(?:project(?:\s+(?:name|no|number))?)\s*[:#=-]\s*(\S.*)$',re.I),
    'job_key': re.compile(r'^\s*(?:job\s*(?:no|number|#))\s*[:#=-]\s*(\S.*)$',re.I),
    'work_date': re.compile(r'^\s*(?:report\s+date|date)\s*[:#=-]\s*(\S.*)$',re.I),
    'slump_in': re.compile(r'^\s*(?:slump(?:\s*\(?in(?:ches)?\)?)?)\s*[:#=-]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:in\.?|inches|[\"])?\s*$',re.I),
    'air_percent': re.compile(r'^\s*(?:air\s*(?:content)?\s*(?:%|percent)?)\s*[:#=-]\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*$',re.I),
    'concrete_temp_f': re.compile(r'^\s*(?:concrete\s*(?:temperature|temp)(?:\s*\(?f\)?)?)\s*[:#=-]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:°?f)?\s*$',re.I),
    'field_moisture_percent': re.compile(r'^\s*(?:field\s+moisture(?:\s*%)?)\s*[:#=-]\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*$',re.I),
    'field_wet_density_pcf': re.compile(r'^\s*(?:wet\s+density(?:\s*\(?pcf\)?)?|field\s+wet\s+density)\s*[:#=-]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:pcf)?\s*$',re.I),
    'field_dry_density_pcf': re.compile(r'^\s*(?:dry\s+density(?:\s*\(?pcf\)?)?|field\s+dry\s+density)\s*[:#=-]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:pcf)?\s*$',re.I),
    'max_dry_density_pcf': re.compile(r'^\s*(?:max(?:imum)?\s+dry\s+density(?:\s*\(?pcf\)?)?)\s*[:#=-]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:pcf)?\s*$',re.I),
    'reported_compaction_percent': re.compile(r'^\s*(?:percent\s+(?:compaction|density)|compaction\s*%)\s*[:#=-]\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*$',re.I),
}
NUMERIC={'slump_in','air_percent','concrete_temp_f','field_moisture_percent','field_wet_density_pcf',
         'field_dry_density_pcf','max_dry_density_pcf','reported_compaction_percent'}
ROW_NUMERIC=NUMERIC-{'slump_in','air_percent','concrete_temp_f'}

def open_image(data:bytes):
    if not isinstance(data,bytes) or not data or len(data)>MAX_IMAGE_BYTES:
        raise ValueError('Image must be 1 byte to 4 MB')
    try:
        with Image.open(BytesIO(data)) as im:
            if im.format not in ALLOWED_FORMATS:raise ValueError('Only PNG, JPEG, WEBP accepted')
            if im.width*im.height>MAX_PIXELS:raise ValueError('Image exceeds pixel limit')
            if im.width<100 or im.height<100:raise ValueError('Image too small for reliable processing')
            # Force decode before returning, no EXIF metadata copied to output.
            return ImageOps.exif_transpose(im).convert('RGB')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as ex:
        raise ValueError('Invalid or unsafe image') from ex

def _clean(v:str)->str:
    return ''.join(ch for ch in v if ch.isprintable()).strip()[:260]

def ocr_lines(data:bytes, *, engine=None)->dict:
    """OCR token boxes with the local Tesseract binary, no outbound requests."""
    im=open_image(data)
    if engine is None:
        try:import pytesseract
        except ImportError as exc:raise RuntimeError('Install pytesseract and local Tesseract OCR') from exc
        try:
            result=pytesseract.image_to_data(im,lang='eng',config='--psm 6',output_type=pytesseract.Output.DICT,timeout=15)
        except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
            raise RuntimeError('Local Tesseract OCR unavailable or timed out') from exc
    else:result=engine(im)
    buckets=defaultdict(list)
    n=len(result.get('text',[]))
    if n>50000:raise ValueError('OCR output too large')
    for i in range(n):
        text=_clean(str(result['text'][i]))
        if not text:continue
        try:conf=float(result['conf'][i])
        except (ValueError,TypeError):conf=-1
        if not math.isfinite(conf) or conf<0:continue
        try:
            box=[int(result[k][i]) for k in ('left','top','width','height')]
            if min(box[2:])<=0 or box[0]<0 or box[1]<0 or box[0]+box[2]>im.width+2 or box[1]+box[3]>im.height+2:continue
            group=tuple(int(result[k][i]) for k in ('block_num','par_num','line_num'))
        except (TypeError,ValueError,KeyError,IndexError):continue
        buckets[group].append({'text':text,'confidence':round(max(0,min(100,conf))/100,3),'box':box})
    lines=[]
    for toks in buckets.values():
        toks.sort(key=lambda x:x['box'][0]); left=min(t['box'][0] for t in toks);top=min(t['box'][1] for t in toks)
        right=max(t['box'][0]+t['box'][2] for t in toks);bottom=max(t['box'][1]+t['box'][3] for t in toks)
        joined=' '.join(t['text'] for t in toks)[:320]
        score=round(sum(t['confidence'] for t in toks)/len(toks),3)
        lines.append({'text':joined,'confidence':score,'box':[left,top,right-left,bottom-top]})
    lines.sort(key=lambda x:(x['box'][1],x['box'][0]));lines=lines[:MAX_LINES]
    return {'schema':'cmt-local-ocr-v1.9','engine':'local-tesseract','image_sha256':hashlib.sha256(data).hexdigest(),
            'image_size':[im.width,im.height],'lines':[dict(line,id=f'line-{i+1}') for i,line in enumerate(lines)],
            'warnings':['OCR is unverified, especially handwriting and table rows. No material acceptance or ElmTree sync.',
                        'Confidence scores are not calibrated probabilities. Always compare against the original.']}

def infer_candidates(result:dict,form_type:str)->list[dict]:
    """Only deterministic clear label:value text; NO auto extraction of dense table cells."""
    if form_type not in ALLOWED_TYPES:raise ValueError('Unsupported form type')
    spec=DICT['forms'][form_type]
    allowed=set(spec['headers']) | set(spec.get('activities',[]))
    # Table fields cannot be assigned to the correct test without independently verified row boundaries.
    inferred=[]; seen=set()
    for line in result['lines']:
        for key,pattern in LABELS.items():
            if key not in allowed or key in seen:continue
            match=pattern.fullmatch(line['text'])
            if not match:continue
            v=_clean(match.group(1))
            if key=='work_date':
                # Never auto-normalize ambiguous dates like 10/11/26.
                try:date.fromisoformat(v)
                except ValueError:continue
            if key in NUMERIC:
                try:
                    num=float(v)
                    if not math.isfinite(num) or num<0 or num>100000:continue
                except (TypeError,ValueError):continue
            if not v:continue
            seen.add(key)
            inferred.append({'key':key,'value':v,'confidence':line['confidence'], 'line_id':line['id'],
                             'box':line['box'],'reviewed':False,'reviewer_ref':''})
            break
    return inferred

def to_capture(ocr:dict,*,form_type:str,source_id:str,project_key:str,work_date:str,
               data_mode:str='synthetic', authorization_attested:bool=False,
               selections:list|None=None)->dict:
    """Produce v1.8 stage-compatible, always-UNREVIEWED packet.

    Operator metadata is not evidence of document readings. Required headers are
    added as explicit unreviewed placeholders, never silently certified.
    """
    if data_mode not in ('synthetic','authorized'):raise ValueError('Invalid mode')
    if data_mode=='authorized' and authorization_attested is not True:
        raise ValueError('Explicit written permission is required for authorized material')
    if form_type not in ALLOWED_TYPES:raise ValueError('Unknown form type')
    if not isinstance(source_id,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,70}',source_id):
        raise ValueError('Source ID must be an opaque short identifier')
    if not isinstance(project_key,str) or not (1<=len(project_key)<=70):raise ValueError('Project key invalid')
    try:date.fromisoformat(work_date)
    except (ValueError,TypeError):raise ValueError('work date ISO YYYY-MM-DD required')
    selected=selections if selections is not None else infer_candidates(ocr,form_type)
    if not isinstance(selected,list) or len(selected)>80:raise ValueError('Too many proposals')
    allowed=set(DICT['forms'][form_type]['headers']) | set(DICT['forms'][form_type].get('activities',[]))
    refs={line['id']:line for line in ocr['lines']};headers=[];taken=set()
    for s in selected:
        if not isinstance(s,dict) or s.get('key') not in allowed or s.get('key') in taken:raise ValueError('Invalid/duplicate field mapping')
        if s.get('line_id') not in refs:raise ValueError('Source line not found')
        key=s['key'];value=s.get('value');
        if not isinstance(value,str) or not value.strip() or len(value)>220:raise ValueError('Invalid transcription')
        taken.add(key)
        confidence=refs[s['line_id']]['confidence']
        headers.append({'key':key,'value':value.strip(),'origin':'model','confidence':confidence,
                        'evidence_ref':f'{source_id}#{s["line_id"]}', 'reviewed':False,'reviewer_ref':''})
    # Explicit metadata placeholders; not recognized off the image.
    for key,val in (('project_key',project_key),('work_date',work_date)):
        if key not in taken:
            headers.append({'key':key,'value':val,'origin':'manual','confidence':None,
                            'evidence_ref':f'{source_id}#operator-metadata', 'reviewed':False,'reviewer_ref':''})
    return {'schema':VERSION,'data_mode':data_mode,'authorization_attested':authorization_attested,
            'project_key':project_key,'work_date':work_date,'documents':[
            {'source_id':source_id,'form_type':form_type,'fields':headers,'rows':[]}]}
