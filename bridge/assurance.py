"""Offline, vendor-neutral CMT handoff validation: no ElmTree API or upload.

This is an additional gate around v1.3 bridge core, NOT a professional seal,
ASTM certification, authentication of external data, or a vendor-specific import.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import csv
import hashlib
import io
import json
import re
import zipfile

from .core import (
    BRIDGE_NOTICE, MAX_ROWS, SAFE_COL, canonical, eligible_records,
    export_csv, extract_records, normalize, parse_export_csv, reconciliation,
    sha256, validate_mapping, value_at,
)

FORMAT = 'cmt-neutral-handoff-v1.4'
FILES = frozenset({'MAPPING.json', 'PREPARED_REVIEW_ONLY.csv', 'PREFLIGHT.json', 'MANIFEST.json'})
UNITS = frozenset({'pcf', 'kg/m3', 'percent', 'psi', 'mpa', 'in', 'mm', 'f', 'c', 'g', 'lb', 'kg', 'unitless'})


def check_profile(profile:dict) -> dict:
    validate_mapping(profile)
    units = profile.get('measurement_units')
    measured = {key for key in profile['columns'] if key.startswith('measurements.')}
    if not isinstance(units, dict) or set(units) != measured:
        raise ValueError('Every mapped measurement needs an explicit unit in profile.measurement_units')
    if any(unit not in UNITS for unit in units.values()):
        raise ValueError('Unknown or ambiguous profile measurement unit')
    # Warning: Source units must also be attested before exchange (not deduced from names).
    return profile


def numeric_measurement(value) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value,(dict,list)):
        return False
    try:
        s=str(value).strip()
        if len(s)>50 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',s):
            return False
        return Decimal(s).is_finite()
    except (ValueError, InvalidOperation):
        return False


def record_issue(record:dict, profile:dict, demo:bool) -> list[str]:
    problems=[]
    if record.get('status') != 'reviewed' or not record.get('reviewer') or record.get('reviewer')==record.get('creator'):
        problems.append('independent_review_not_attested')
    if record.get('source') == 'synthetic':
        if not demo: problems.append('synthetic_not_allowed')
    elif record.get('source') != 'authorized':
        problems.append('unknown_source_authorization')
    for key in ('record_id','project_code','test_type'):
        value = record.get('id',record.get('record_id')) if key=='record_id' else record.get(key)
        if value is None or not str(value).strip():
            problems.append('missing_'+key)
    for path, expected_unit in profile['measurement_units'].items():
        unit_map = record.get('measurement_units')
        actual_unit = unit_map.get(path) if isinstance(unit_map, dict) else None
        if actual_unit != expected_unit:
            problems.append('unit_mismatch_or_missing:'+path)
        if not numeric_measurement(value_at(record,path)):
            problems.append('missing_or_nonnumeric_measurement:'+path)
    for path in profile.get('match_on',['record_id']):
        if path=='record_id':val=record.get('id',record.get('record_id'))
        else:val=value_at(record,path)
        if val is None or str(val).strip()=='':problems.append('missing_join_key:'+path)
    return problems


def preflight(data,profile,*,demo=False) -> dict:
    """Explain eligibility without mutating data; never silently coerce units."""
    check_profile(profile)
    records=extract_records(data)
    ids=Counter(str(x.get('id',x.get('record_id',''))).strip() for x in records)
    keys=profile.get('match_on',['record_id'])
    def k(r):
        return tuple(normalize((r.get('id',r.get('record_id')) if item=='record_id' else value_at(r,item))) for item in keys)
    counts=Counter(k(r) for r in records)
    passed=[]; quarantined=[]
    for r in records:
        rid=str(r.get('id',r.get('record_id',''))).strip()
        issues=record_issue(r,profile,demo)
        if ids[rid]>1:issues.append('duplicate_record_id')
        if counts[k(r)]>1:issues.append('duplicate_match_key')
        if issues:quarantined.append({'record_id':rid,'reasons':sorted(set(issues))})
        else:passed.append(r)
    return {'schema':'cmt-bridge-preflight-v1.4','review_only':True,
            'provenance_warning':'Labels and independent review are source attestations, NOT authenticated vendor approvals.',
            'measurement_policy':'Exact units required; no implied unit conversion or regulatory pass/fail.',
            'total_records':len(records),'eligible_count':len(passed),'quarantined_count':len(quarantined),
            'quarantined':quarantined,'eligible_records':passed}


def prepare_strict(data,profile,*,demo=False):
    gate=preflight(data,profile,demo=demo)
    # Core export is the only writer; filter all duplicates/missing-unit before export.
    csv_data,meta=export_csv({'records':gate['eligible_records']},profile,demo=demo)
    if meta['withheld']:
        raise ValueError('Unexpected withheld record after strict preflight')
    meta['original_total_records']=gate['total_records']
    meta['strict_quarantined_count']=gate['quarantined_count']
    meta['review_only']=True
    meta['unit_schema']=dict(profile['measurement_units'])
    return csv_data,meta,gate


def handoff_bundle(data,profile,*,demo=False) -> tuple[bytes,dict]:
    csv_bytes,meta,gate=prepare_strict(data,profile,demo=demo)
    if gate['eligible_count'] < 1:
        raise ValueError('No eligible records: handoff package blocked')
    mapping_bytes=(canonical(profile)+'\n').encode('utf-8')
    gate_public={k:v for k,v in gate.items() if k!='eligible_records'}
    gate_bytes=(canonical(gate_public)+'\n').encode('utf-8')
    files={'MAPPING.json':mapping_bytes,'PREFLIGHT.json':gate_bytes,'PREPARED_REVIEW_ONLY.csv':csv_bytes}
    manifest={'schema':FORMAT,'review_only':True,'vendor_import_verified':False,
              'synthetic_demo':bool(demo),'prepared_rows':meta['prepared_rows'],
              'quarantined_rows':gate['quarantined_count'],
              'warning':'NOT ElmTree import-ready. ZIP hashes are integrity checks, not digital signatures.',
              'sha256':{name:sha256(blob) for name,blob in sorted(files.items())}}
    files['MANIFEST.json']=(canonical(manifest)+'\n').encode('utf-8')
    output=BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,contents in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o600 <<16
            z.writestr(info,contents)
    return output.getvalue(),manifest


def verify_bundle(data:bytes) -> dict:
    if len(data)>7_000_000:
        raise ValueError('Handoff package too large')
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            infos=z.infolist()
            names=[i.filename for i in infos]
            if len(names)!=len(FILES) or set(names)!=FILES or len(names)!=len(set(names)):
                raise ValueError('Unknown, duplicate, or missing ZIP entry')
            if any(i.file_size>5_000_000 or i.is_dir() or i.flag_bits&1 for i in infos):
                raise ValueError('Unexpected encrypted/oversized ZIP entry')
            files={name:z.read(name) for name in FILES}
    except (zipfile.BadZipFile, EOFError) as exc:
        raise ValueError('Invalid ZIP package') from exc
    try:
        manifest=json.loads(files['MANIFEST.json'])
        profile=json.loads(files['MAPPING.json'])
        gate=json.loads(files['PREFLIGHT.json'])
        rows=parse_export_csv(files['PREPARED_REVIEW_ONLY.csv'])
    except (ValueError,UnicodeDecodeError) as exc:
        raise ValueError('Corrupt bundle content') from exc
    if manifest.get('schema')!=FORMAT or manifest.get('vendor_import_verified') is not False or manifest.get('review_only') is not True:
        raise ValueError('Invalid handoff manifest schema or safety status')
    if set(manifest.get('sha256',{})) != (FILES-{'MANIFEST.json'}):
        raise ValueError('Manifest file inventory mismatch')
    for name,expected in manifest['sha256'].items():
        if not isinstance(expected,str) or sha256(files[name])!=expected:
            raise ValueError('SHA-256 mismatch for '+name)
    check_profile(profile)
    if gate.get('schema')!='cmt-bridge-preflight-v1.4' or gate.get('review_only') is not True:
        raise ValueError('Invalid preflight summary')
    if not rows or len(rows)!=manifest.get('prepared_rows') or gate.get('eligible_count')!=len(rows) or gate.get('quarantined_count')!=manifest.get('quarantined_rows'):
        raise ValueError('Record inventory mismatch')
    if not all(r.get(SAFE_COL)==BRIDGE_NOTICE for r in rows):
        raise ValueError('Review-only marker missing from exported CSV')
    return {'ok':True,'schema':FORMAT,'review_only':True,'prepared_rows':len(rows),
            'quarantined_rows':manifest['quarantined_rows'],
            'sha256_bundle':sha256(data),
            'warning':'Self-contained integrity verification only; author identity/permissions not cryptographically proven.'}


def reconcile_strict(data,external_csv:bytes,profile,*,demo=False) -> dict:
    """Block comparisons where source unit or key ambiguity invalidates evidence."""
    gate=preflight(data,profile,demo=demo)
    if gate['quarantined_count']:
        # Keep output for inspection, but never report a clean reconciliation.
        blockers=[{'record_id':r['record_id'],'reasons':r['reasons']} for r in gate['quarantined']]
    else:blockers=[]
    # External CSV must have explicit mapped columns, with no unsafe formula payloads.
    outside=parse_export_csv(external_csv)
    external_warnings=[]
    for i,row in enumerate(outside):
        for col,v in row.items():
            if v and v.lstrip().startswith(('=','+','@')):
                external_warnings.append({'row':i+2,'column':col,'issue':'formula_like_external_cell'})
    report=reconciliation({'records':gate['eligible_records']},external_csv,profile,demo=demo)
    report['schema']='cmt-reconciliation-v1.4'
    report['source_quarantine']=blockers
    report['external_csv_warnings']=external_warnings[:100]
    report['unit_schema']=dict(profile['measurement_units'])
    report['comparison_status']='NEEDS_HUMAN_REVIEW' if (blockers or external_warnings) else report['comparison_status']
    report['not_vendor_certified']=True
    return report
