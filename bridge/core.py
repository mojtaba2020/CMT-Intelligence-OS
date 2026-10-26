"""CMT data exchange for an *operator-supplied* layout, NOT a native ElmTree connector.

Fail closed on unknown columns, duplicate keys, ambiguous joins, missing data,
unauthorized source labels, and records not marked as human-reviewed.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_ROWS = 10000
MAX_CELL = 2000
MAX_FIELDS = 50
PATH_RE = re.compile(r'^(?:record_id|version|status|test_type|project_code|location|spec_reference|evidence_reference|source|creator|reviewer|reviewed_at|measurements\.[A-Za-z][\w-]{0,69})$')
BRIDGE_NOTICE = 'REVIEW_ONLY_NOT_VENDOR_IMPORT_APPROVED'
SAFE_COL = '__CMT_BRIDGE_NOTICE'
REQUIRED_KEYS = ('record_id','project_code','test_type')


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_mapping(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError('Mapping must be a JSON object')
    mapping = profile.get('columns')
    if not isinstance(mapping, dict) or not 3 <= len(mapping) <= MAX_FIELDS:
        raise ValueError('Mapping columns must contain 3–50 fields')
    if not isinstance(profile.get('profile_name'), str) or not 3 <= len(profile['profile_name']) <= 80:
        raise ValueError('Profile name required')
    if profile.get('vendor_import_verified') is not False:
        raise ValueError('Vendor import capability is NOT verified. vendor_import_verified must be false')
    seen = set()
    for field, col in mapping.items():
        if not isinstance(field,str) or not PATH_RE.fullmatch(field):
            raise ValueError(f'Unknown canonical field: {field!r}')
        if not isinstance(col,str) or not col or col.strip()!=col or len(col)>100 or any(x in col for x in '\r\n\0'):
            raise ValueError('Invalid destination column')
        if col == SAFE_COL or col.casefold() in seen:
            raise ValueError('Duplicate/reserved column')
        seen.add(col.casefold())
    if any(key not in mapping for key in REQUIRED_KEYS):
        raise ValueError('Required canonical keys: record_id, project_code, test_type')
    keys=profile.get('match_on',['record_id'])
    if not isinstance(keys,list) or not 1 <= len(keys) <= 4 or len(set(keys)) != len(keys):
        raise ValueError('match_on requires 1–4 distinct canonical keys')
    if not all(k in mapping and k in ('record_id','project_code','test_type','location','evidence_reference') for k in keys):
        raise ValueError('match_on must use stable mapped identifier fields')
    return profile


def value_at(record:dict, field: str):
    result = record
    for item in field.split('.'):
        if not isinstance(result,dict) or item not in result:
            return None
        result = result[item]
    if isinstance(result,(dict,list,bool)) or (isinstance(result,float) and not math.isfinite(result)):
        raise ValueError(f'Non-scalar mapped value: {field}')
    return result


def safe_csv_cell(value: Any) -> str:
    """Escape formula-like cells; no Excel formula evaluation or macros."""
    s = '' if value is None else str(value)
    if len(s)>MAX_CELL or '\0' in s:
        raise ValueError('Oversized or invalid CSV cell')
    if s.lstrip().startswith(('=', '+', '-', '@')) or s.startswith(('\t','\r','\n')):
        return "'" + s
    return s


def normalize(v: Any) -> str:
    """Compare exact values, but make numeric 126 and 126.00 equivalent.

    Never round scientific measurements or use approximate matching by default.
    """
    s = '' if v is None else str(v).strip()
    if re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',s):
        try:
            d=Decimal(s)
            if d.is_finite(): return str(d.normalize())
        except InvalidOperation: pass
    return s


def extract_records(data: Any) -> list[dict]:
    if isinstance(data,dict):
        records=data.get('records')
        if records is None and isinstance(data.get('record'),dict):
            records=[data['record']]
    else: records=data
    if not isinstance(records,list) or len(records)>MAX_ROWS:
        raise ValueError('Expected a list of at most 10,000 records')
    if not all(isinstance(r,dict) for r in records):
        raise ValueError('Every record must be an object')
    return records


def eligible_records(records:list[dict], demo:bool=False) -> tuple[list[dict],list[dict]]:
    allowed=[]; withheld=[]; seen=set()
    for index,r in enumerate(records):
        rid=str(r.get('id',r.get('record_id',''))).strip()
        if not rid or len(rid)>120 or rid in seen:
            withheld.append({'index':index,'reason':'missing_or_duplicate_record_id'});continue
        seen.add(rid)
        if r.get('status') != 'reviewed' or not r.get('reviewer') or r.get('reviewer') == r.get('creator'):
            withheld.append({'record_id':rid,'reason':'independent_human_review_missing'});continue
        if r.get('source') == 'synthetic' and demo:
            pass
        elif r.get('source') != 'authorized':
            withheld.append({'record_id':rid,'reason':'not_authorized_pilot_data'});continue
        if not all(str(r.get(k,'')).strip() for k in ('project_code','test_type')):
            withheld.append({'record_id':rid,'reason':'missing_project_or_test'});continue
        copied=dict(r);copied['record_id']=rid
        allowed.append(copied)
    return allowed,withheld


def mapped_rows(data: Any, profile:dict, *, demo:bool=False) -> tuple[list[dict],dict]:
    profile=validate_mapping(profile)
    records=extract_records(data)
    valid,withheld=eligible_records(records,demo=demo)
    mapping=profile['columns']; rows=[]
    for r in valid:
        try:
            vals={mapping[field]:value_at(r,field) for field in mapping}
            if any(vals[mapping[k]] is None or str(vals[mapping[k]]).strip()=='' for k in REQUIRED_KEYS):
                raise ValueError('missing_required_field')
            if any(vals[mapping[k]] is None or str(vals[mapping[k]]).strip()=='' for k in profile.get('match_on',['record_id'])):
                raise ValueError('missing_reconciliation_key')
            row={SAFE_COL:BRIDGE_NOTICE}
            row.update({col:safe_csv_cell(val) for col,val in vals.items()})
            rows.append(row)
        except ValueError as exc:
            withheld.append({'record_id':r['record_id'],'reason':str(exc)[:80]})
    headers=[SAFE_COL,*mapping.values()]
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=headers,lineterminator='\r\n')
    writer.writeheader();writer.writerows(rows)
    encoded=buffer.getvalue().encode('utf-8-sig')
    meta={'schema':'cmt-vendor-neutral-bridge-v1', 'profile_name':profile['profile_name'],
          'vendor_import_verified':False,'review_only':True,'demo':demo,
          'source_rows':len(records),'prepared_rows':len(rows),'withheld':withheld,
          'sha256_csv':sha256(encoded)}
    return rows,{'metadata':meta,'csv_bytes':encoded}


def export_csv(data:Any, profile:dict, *, demo:bool=False) -> tuple[bytes,dict]:
    _,res=mapped_rows(data,profile,demo=demo)
    return res['csv_bytes'],res['metadata']


def parse_export_csv(data:bytes) -> list[dict]:
    if len(data)>3_000_000:
        raise ValueError('Comparison CSV exceeds 3 MB')
    try:
        src=data.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('CSV requires UTF-8') from exc
    stream=io.StringIO(src,newline='')
    reader=csv.DictReader(stream)
    if reader.fieldnames is None or len(reader.fieldnames)>MAX_FIELDS+10 or len(set(reader.fieldnames))!=len(reader.fieldnames):
        raise ValueError('Invalid, missing or duplicate CSV columns')
    out=[]
    for row in reader:
        if len(out)>=MAX_ROWS or None in row:
            raise ValueError('Malformed or too many CSV rows')
        if any(len(str(v))>MAX_CELL for v in row.values()):
            raise ValueError('Oversized CSV cell')
        out.append(row)
    return out


def reconciliation(records:Any, external_csv:bytes, profile:dict, *,demo:bool=False) -> dict:
    """Compare allowed source records to operator-provided exported QA CSV.

    Match by exactly configured identifiers. Ambiguous keys are quarantined.
    NEVER infer that an exported file is ElmTree just because of its name.
    """
    profile=validate_mapping(profile)
    valid,withheld=eligible_records(extract_records(records),demo=demo)
    mapping=profile['columns']; external=parse_export_csv(external_csv)
    required=list(mapping.values()); missing=[h for h in required if h not in (external[0].keys() if external else [])]
    # CSV header is checked even for empty tables.
    if not external:
        text=external_csv.decode('utf-8-sig')
        header=next(csv.reader(io.StringIO(text)),[])
        missing=[h for h in required if h not in header]
    if missing:raise ValueError('Export missing mapped columns: '+', '.join(missing[:5]))
    keys=profile.get('match_on',['record_id'])
    def src_key(r):return tuple(normalize(value_at(r,k)) for k in keys)
    def ext_key(r):return tuple(normalize(r[mapping[k]]) for k in keys)
    source_keys=defaultdict(list);ext_keys=defaultdict(list)
    for r in valid:source_keys[src_key(r)].append(r)
    for i,r in enumerate(external):ext_keys[ext_key(r)].append((i,r))
    conflicts=[];missing_source=[];missing_external=[];matched=0;ambiguities=[]
    for key in sorted(set(source_keys)|set(ext_keys)):
        ours=source_keys.get(key,[]);theirs=ext_keys.get(key,[])
        if len(ours)>1 or len(theirs)>1 or '' in key:
            ambiguities.append({'match_key':list(key),'cmt_count':len(ours),'external_count':len(theirs)})
        elif ours and theirs:
            matched+=1
            a,b=ours[0],theirs[0][1]
            for field,col in mapping.items():
                original=value_at(a,field)
                outside=b[col]
                if normalize(original)!=normalize(outside):
                    conflicts.append({'match_key':list(key),'field':field,'external_column':col,
                                      'cmt_value': '' if original is None else str(original), 'external_value':outside})
        elif ours: missing_external.append({'match_key':list(key)})
        else: missing_source.append({'match_key':list(key),'external_row_index':theirs[0][0] if theirs else None})
    return {'schema':'cmt-reconciliation-v1','source':'operator_supplied_export_not_vendor_verified',
            'review_only':True,'compared_records':matched,'compared_columns':len(mapping),
            'field_conflicts':conflicts,'ambiguous_keys':ambiguities,
            'missing_in_external':missing_external,'missing_in_cmt':missing_source,
            'withheld_cmt':withheld,'source_csv_sha256':sha256(external_csv),
            'comparison_status':'NEEDS_HUMAN_REVIEW' if (conflicts or ambiguities or missing_external or missing_source or withheld) else 'NO_DIFFERENCES_FOUND_NOT_CERTIFIED'}
