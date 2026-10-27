"""Offline, human-in-the-loop CMT field capture staging (v1.8).

Never performs OCR or uses vendor/private systems. Accepts a candidate JSON envelope
from synthetic data or specifically authorized transcription, requires per-value
human checking, and only then promotes to v1.7's conservative cross-form screening.
It does not attest that a human actually checked; it enforces the recorded workflow.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
from math import isfinite
import json
from pathlib import Path
from typing import Any
from forms.form_engine import inspect_packet

HERE=Path(__file__).parent
DICT=json.loads((HERE/'field_dictionary_v18.json').read_text(encoding='utf-8'))
KINDS=DICT['forms']
VERSION='cmt-capture-v1.8'
NUMERIC={'reported_density_tests','cylinders_cast','cylinders_picked_up','page_number','page_count',
         'field_moisture_percent','field_wet_density_pcf','field_dry_density_pcf','max_dry_density_pcf',
         'reported_compaction_percent','slump_in','air_percent','ambient_temp_f','concrete_temp_f',
         'accumulated_yards','water_added_gal','design_strength_psi','test_age_days','load_lbf',
         'area_in2','unit_load_psi','bar_count','spacing_in','cover_in','element_width_in','element_height_in','total_hours'}
INTS={'reported_density_tests','cylinders_cast','cylinders_picked_up','page_number','page_count','test_age_days','bar_count'}
ALIASES={'cylinders_cast':'reported_concrete_cylinders_cast',
         'cylinders_picked_up':'reported_concrete_cylinders_picked_up'}
MAX_BYTES=1_000_000
MAX_DOCS=250
MAX_ITEMS=4000


def _number(value, key):
    if isinstance(value,bool):raise ValueError('boolean is not a valid number')
    if not isinstance(value,(str,int,float)) or str(value).strip()=='':raise ValueError('missing numeric value')
    v=float(value)
    from math import isfinite
    if not isfinite(v):raise ValueError('non-finite numeric value')
    if abs(v)>1_000_000_000:raise ValueError('numeric magnitude exceeds safety cap')
    if key in INTS:
        if not v.is_integer() or v<0:raise ValueError('must be a nonnegative integer')
        if key in ('page_number','page_count') and not 1<=v<=250:
            raise ValueError('page number/count outside 1..250')
        return int(v)
    return v


def _s(v):
    if not isinstance(v,str) or len(v)>220:raise ValueError('expected short text')
    return v.strip()


def stage(envelope:dict) -> dict:
    """Review summary and sanitized, v1.7-compatible packet only when every field reviewed."""
    if not isinstance(envelope,dict) or envelope.get('schema')!=VERSION:
        raise ValueError('expected cmt-capture-v1.8 schema')
    if envelope.get('data_mode') not in ('synthetic','authorized'):
        raise ValueError('data_mode must explicitly be synthetic or authorized')
    if envelope['data_mode']=='authorized' and envelope.get('authorization_attested') is not True:
        raise ValueError('authorized mode requires affirmative authorization attestation')
    docs=envelope.get('documents')
    if not isinstance(docs,list) or not 1<=len(docs)<=MAX_DOCS:
        raise ValueError('documents must be an array of 1..250 items')
    project=_s(envelope.get('project_key',''))
    work_day=_s(envelope.get('work_date',''))
    if not project or not work_day:raise ValueError('packet project_key and work_date are required')
    try: date.fromisoformat(work_day)
    except ValueError as e:raise ValueError('work_date must be ISO YYYY-MM-DD') from e
    issues=[]; converted=[]; counts=Counter(); used_docs=set(); item_count=0
    def issue(code,doc,field='',detail='',priority='BLOCK'):
        issues.append({'code':code,'document':doc,'field':field,'detail':detail,'priority':priority})
    for doc in docs:
        if not isinstance(doc,dict): raise ValueError('each document must be an object')
        did=_s(doc.get('source_id',''))
        if not did:issue('SOURCE_ID_REQUIRED','unknown')
        if did in used_docs:issue('DUPLICATE_SOURCE_ID',did)
        used_docs.add(did)
        kind=doc.get('form_type')
        if kind not in KINDS:
            issue('UNSUPPORTED_FORM_TYPE',did,str(kind));continue
        definition=KINDS[kind]
        allowed=set(definition['headers']) | set(definition.get('activities',[]))
        row_allowed=set(definition.get('columns',[]))
        converted_doc={'form_id':did,'form_type':kind,'project_key':project,
                       'work_date':work_day,'human_verified':False}
        raw=doc.get('fields',[])
        if not isinstance(raw,list):raise ValueError('fields must be array')
        if len(raw)>MAX_ITEMS:raise ValueError('exceeds max captured items')
        rows=doc.get('rows',[])
        if not isinstance(rows,list) or len(rows)>300:raise ValueError('rows must be array <=300')
        complete=True
        def scan(fields,allowed_keys,scope):
            nonlocal complete,item_count
            values={}
            if not isinstance(fields,list):raise ValueError('row.fields must be array')
            for item in fields:
                item_count+=1
                if item_count>MAX_ITEMS:raise ValueError('exceeds max captured items')
                if not isinstance(item,dict):raise ValueError('field entry must be object')
                key=_s(item.get('key',''))
                pointer=f'{scope}.{key}'
                if not key or key not in allowed_keys:
                    issue('UNKNOWN_FIELD',did,pointer);complete=False;continue
                if key in values:
                    issue('DUPLICATE_FIELD',did,pointer);complete=False;continue
                origin=item.get('origin')
                if origin not in ('model','manual'):
                    issue('ORIGIN_REQUIRED',did,pointer);complete=False
                evidence=item.get('evidence_ref')
                if not isinstance(evidence,str) or not evidence.strip() or len(evidence)>160:
                    issue('EVIDENCE_REF_REQUIRED',did,pointer);complete=False
                value=item.get('value')
                conf=item.get('confidence')
                conf_ok=conf is None or (not isinstance(conf,bool) and isinstance(conf,(int,float))
                                         and isfinite(conf) and 0<=conf<=1)
                if not conf_ok:
                    issue('CONFIDENCE_INVALID',did,pointer);complete=False
                counts['captured']+=1
                if conf_ok and conf is not None and conf<0.90:
                    counts['low_confidence']+=1
                    issue('LOW_CONFIDENCE',did,pointer,'Candidate should be checked against original', 'REVIEW')
                if item.get('reviewed') is not True or not isinstance(item.get('reviewer_ref'),str) or not item['reviewer_ref'].strip():
                    issue('FIELD_NEEDS_HUMAN_REVIEW',did,pointer)
                    counts['pending']+=1;complete=False
                else:counts['reviewed']+=1
                try:
                    if key in NUMERIC: normalized=_number(value,key)
                    else:
                        normalized=_s(value)
                        if not normalized:raise ValueError('blank field; omit it if not observed')
                except (ValueError,OverflowError):
                    issue('VALUE_INVALID',did,pointer);complete=False;continue
                values[key]=normalized
            return values
        flat=scan(raw,allowed,'header')
        for required in definition['required']:
            if required not in flat:
                issue('REQUIRED_FIELD_MISSING',did,required);complete=False
        if 'project_key' in flat and flat['project_key']!=project:
            issue('PROJECT_KEY_MISMATCH',did,'project_key');complete=False
        if 'work_date' in flat and flat['work_date']!=work_day:
            issue('WORK_DATE_MISMATCH',did,'work_date');complete=False
        for k,v in flat.items():
            converted_doc[ALIASES.get(k,k)]=v
        group=definition.get('repeat_group')
        if not group and rows:
            issue('ROWS_NOT_ALLOWED',did);complete=False
        if group:
            out=[]; used_rows=set()
            for idx,entry in enumerate(rows):
                if not isinstance(entry,dict):raise ValueError('row must be an object')
                row_id=_s(entry.get('row_id',''))
                if not row_id or row_id in used_rows:
                    issue('ROW_ID_MISSING_OR_DUPLICATE',did,f'row[{idx}]');complete=False
                used_rows.add(row_id)
                row_values=scan(entry.get('fields',[]),row_allowed,f'{group}[{idx}]')
                if kind=='density_sheet' and row_values:
                    for required in definition['row_required_for_arithmetic']:
                        if required not in row_values:
                            issue('REQUIRED_ROW_FIELD_MISSING',did,f'{group}[{idx}].{required}');complete=False
                if kind=='density_sheet' and row_values:
                    out.append(row_values)
                elif kind=='concrete_strength':
                    out.append(row_values)
                elif kind=='rebar_observation':out.append(row_values)
            converted_doc[group]=out
        converted_doc['human_verified']=complete
        converted.append(converted_doc)
        counts['documents']+=1
    any_block=any(x['priority']=='BLOCK' for x in issues)
    if any_block:
        return {'schema':VERSION, 'data_mode':envelope['data_mode'], 'ready_for_screening':False,
                'summary':dict(counts), 'issues':issues, 'screening':None,
                'notice':'No promotion. All mandatory values must be checked by an authorized human.'}
    sanitized={'synthetic':envelope['data_mode']=='synthetic',
               'project_key':project,'work_date':work_day,'forms':converted}
    screening=inspect_packet(sanitized)
    # A clean screening is NOT a professional approval.
    return {'schema':VERSION,'data_mode':envelope['data_mode'], 'ready_for_screening':True,
            'summary':dict(counts), 'issues':issues,'screening':screening,
            'notice':'Screening only; NOT accepted material, signed report, or an authorized ElmTree import.'}


def main():
    parser=argparse.ArgumentParser(description='CMT candidate field staging and cross-document QA (offline)')
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.input.stat().st_size>MAX_BYTES:raise SystemExit('Input exceeds 1MB')
    data=json.loads(args.input.read_text(encoding='utf-8'))
    result=stage(data)
    response=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.output:args.output.write_text(response,encoding='utf-8')
    else:print(response)

if __name__=='__main__':main()
