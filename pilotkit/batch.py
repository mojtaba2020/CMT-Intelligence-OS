"""CMT Pilot Evidence Pack v1.6 — strictly offline and review-only.

Inputs are operator-transcribed readings from synthetic or expressly authorized
sources. There is NO OCR, live ElmTree integration, ASTM/PE acceptance, or server call.
The ZIP manifest detects accidental/ordinary post-creation changes but is NOT
an authenticated signature against a fully malicious re-packaging attacker.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import io
import json
from pathlib import Path
import re
import zipfile

from pydantic import ValidationError
from server.reconcile_v15 import Case, reconcile

VERSION = 'cmt-pilot-evidence-pack-v1.6'
MAX_CASES = 250
MAX_INPUT_BYTES = 1_000_000
MAX_BUNDLE_BYTES = 6_000_000
FILES = ('report.json', 'review_queue.csv', 'summary.html', 'NOTICE.txt')
SCREEN_ONLY = 'SCREENING_ONLY — no professional approval, ElmTree import, or official acceptance'


def json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _csv_safe(value: object) -> str:
    """Avoid spreadsheet formula injection in human-review worksheet."""
    s = '' if value is None else str(value)
    if s.lstrip().startswith(('=', '+', '-', '@')) or s.startswith(('\t', '\r', '\n')):
        return "'" + s
    return s


def _csv(rows: list[dict]) -> bytes:
    columns = ['case_no', 'project_id', 'test_id', 'test_type', 'review_status', 'issue_code',
               'field', 'details', 'engineer_approved', 'reviewer_note']
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator='\r\n')
    writer.writeheader()
    for r in rows:
        writer.writerow({k: _csv_safe(r.get(k)) for k in columns})
    return out.getvalue().encode('utf-8-sig')


def _dashboard(report: dict) -> bytes:
    rows = []
    for case in report['cases']:
        issue_items = ''.join('<li><strong>' + escape(i['code']) + '</strong> · ' +
                              escape(i.get('field', '')) + ' — ' +
                              escape(i['details']) + '</li>' for i in case['issues'])
        if not issue_items:
            issue_items = '<li>No discrepancies in checked fields; human review still required.</li>'
        status = escape(case['review_status'])
        cls = 'clear' if not case['issues'] else 'flagged'
        rows.append(f'<section class="case"><header><span class="count">CASE {case["case_no"]:03}</span>'
                    f'<span class="pill {cls}">{status}</span></header>'
                    f'<h2>{escape(case["test_type"].upper())}</h2>'
                    f'<p>Project: <strong>{escape(case["project_id"])}</strong> · Test: '
                    f'<strong>{escape(case["test_id"])}</strong></p>'
                    f'<details><summary>{len(case["issues"])} finding(s) · reviewer details</summary>'
                    f'<ul>{issue_items}</ul></details></section>')
    data = report['summary']
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CMT | Local Pilot Review</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#081526;color:#e8f4fa}
*{box-sizing:border-box}body{margin:0;padding:22px}main{max-width:1040px;margin:auto}
.eyebrow{letter-spacing:.2em;color:#6fd5ce;font-size:12px;font-weight:700}
h1{font-size:clamp(30px,5vw,52px);letter-spacing:-.05em;margin:12px 0}p{color:#b7cbd9;line-height:1.5}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:24px 0}
.stat,.case,.warning{background:#11263b;border:1px solid #28485b;border-radius:14px;padding:17px}
.stat strong{display:block;font-size:32px;color:#7be2d6}.stat span{color:#c2d5df;font-size:13px}
.warning{border-color:#bc8b43;background:#29251c;color:#ffe4aa;margin:20px 0}
.cases{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px}
.case h2{margin:15px 0 0;font-size:20px}.case header{display:flex;align-items:center;justify-content:space-between;gap:8px}
.count{color:#a1bdcb;font-size:12px}.pill{font-size:10px;letter-spacing:.04em;padding:7px;border-radius:999px}
.pill.flagged{background:#5a302b;color:#ffe1d8}.pill.clear{background:#214e49;color:#bbf3df}
details{border-top:1px solid #365064;margin-top:18px;padding-top:12px}summary{cursor:pointer;color:#9bdad8}
li{line-height:1.4;margin:9px 0;color:#d7e4ee}footer{margin:32px 0;color:#849faf;font-size:12px}
</style></head><body><main>
<div class="eyebrow">CMT INTELLIGENCE OS / FIELD EVIDENCE PILOT</div>
<h1>Review evidence, not assumptions.</h1>
<p>Offline screen of two independent transcriptions per NDG / fresh-concrete test. No external data transfer.</p>
<section class="stats">
<div class="stat"><strong>''' + str(data['cases']) + '''</strong><span>Cases screened</span></div>
<div class="stat"><strong>''' + str(data['with_findings']) + '''</strong><span>Cases with findings</span></div>
<div class="stat"><strong>''' + str(data['quarantined']) + '''</strong><span>Duplicate cases quarantined</span></div>
<div class="stat"><strong>''' + str(data['total_findings']) + '''</strong><span>Findings, not certifications</span></div>
</section><div class="warning">''' + escape(SCREEN_ONLY) + '''. Synthetic examples must never be presented as production performance. A clear screen is not test-method compliance.</div>
<div class="cases">''' + ''.join(rows) + '''</div>
<footer>Human engineer review required · Generated ''' + escape(report['generated_utc']) + ''' UTC · No connected ElmTree account</footer>
</main></body></html>'''
    return html.encode('utf-8')


def _read_cases(filename: Path, mode: str) -> list[Case]:
    if not filename.is_file() or filename.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError('Input is absent or exceeds 1 MB limit')
    try:
        raw = json.loads(filename.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError('Input must be valid UTF-8 JSON') from e
    if not isinstance(raw, dict) or set(raw) != {'cases'} or not isinstance(raw['cases'], list):
        raise ValueError('Input must be a JSON object with only a cases array')
    if not 1 <= len(raw['cases']) <= MAX_CASES:
        raise ValueError('Expected 1 to 250 cases')
    try:
        cases = [Case.model_validate(x) for x in raw['cases']]
    except (ValidationError, ValueError) as e:
        raise ValueError(f'One or more invalid case records: {e}') from e
    for case in cases:
        if case.synthetic is not (mode == 'synthetic'):
            raise ValueError('Input source flags do not match explicitly requested mode')
    return cases


def compile_report(cases: list[Case], mode: str) -> tuple[dict, bytes]:
    if mode not in ('synthetic', 'authorized'):
        raise ValueError('Explicit data origin required')
    results = []; rows = []; used_tests = set(); used_source_ids = set()
    for i, case in enumerate(cases, 1):
        form = next(d for d in case.documents if d.source_type == 'field_form')
        key = (form.project_id, form.test_id)
        sources = {d.source_id for d in case.documents}
        duplicate = key in used_tests or bool(sources & used_source_ids)
        used_tests.add(key); used_source_ids.update(sources)
        if duplicate:
            findings = [{'code':'DUPLICATE_CASE_OR_SOURCE', 'field':'identifiers',
                         'details':'Case/test identifier or source ID appears more than once in this batch'}]
            status = 'QUARANTINED_DUPLICATE'
            comparisons = []
            derived = []
        else:
            analysis = reconcile(case)
            findings = analysis['issues']; status = analysis['review_status']
            comparisons = analysis['comparisons']; derived = analysis['derived']
        item = {'case_no': i, 'project_id': form.project_id, 'test_id': form.test_id,
                'test_type': case.test_type, 'source_ids': [d.source_id for d in case.documents],
                'review_status': status, 'engineer_approved': False,
                'official_acceptance': None, 'issues': findings, 'comparisons': comparisons,
                'derived': derived}
        results.append(item)
        for finding in findings or [{'code': 'NO_DIFFERENCE_OBSERVED', 'field': '',
                                    'details': 'Checked values agree; human source verification required'}]:
            rows.append({'case_no': i, 'project_id':form.project_id, 'test_id':form.test_id,
                         'test_type':case.test_type, 'review_status':status,
                         'issue_code':finding['code'], 'field':finding.get('field',''),
                         'details':finding['details'], 'engineer_approved':'NO', 'reviewer_note':''})
    counts = {'cases':len(results), 'with_findings':sum(bool(x['issues']) for x in results),
              'quarantined':sum(x['review_status']=='QUARANTINED_DUPLICATE' for x in results),
              'total_findings':sum(len(x['issues']) for x in results)}
    report = {'schema':VERSION, 'data_mode':mode, 'review_only':True, 'vendor_import_verified':False,
              'official_acceptance':None, 'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'summary':counts, 'cases':results,
              'limitations':['Operator-supplied data; neither OCR nor genuine source authenticity is validated.',
                             'All checks are screening comparisons, not ASTM/AASHTO or engineering approval.',
                             'No live ElmTree connection and no original image files in this package.',
                             'Authorized mode only means the operator attested authorization; it is not independently verified.']}
    return report, _csv(rows)


def build(input_path: Path, destination: Path, *, mode: str) -> dict:
    cases = _read_cases(input_path, mode)
    report, queue = compile_report(cases, mode)
    payload = {'report.json':json_bytes(report), 'review_queue.csv':queue,
               'summary.html':_dashboard(report),
               'NOTICE.txt':(SCREEN_ONLY + '\nOriginal images are NOT contained in this ZIP.\n'
                             'Hashes are for change detection, NOT a trusted third-party signature.\n'
                             'No vendor-specific import file is authorized or created.\n').encode('utf-8')}
    manifest = {'schema':VERSION, 'data_mode':mode, 'items': {
        name: {'sha256':sha256(data).hexdigest(), 'bytes':len(data)} for name,data in payload.items()}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in payload.items(): z.writestr(name, data)
        z.writestr('manifest.json',json_bytes(manifest))
    return {'path':str(destination), 'summary':report['summary'], 'sha256':sha256(destination.read_bytes()).hexdigest()}


def verify(bundle: Path) -> dict:
    if not bundle.is_file() or bundle.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError('Bundle absent or exceeds 6 MB limit')
    with zipfile.ZipFile(bundle,'r') as z:
        names = z.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(FILES)|{'manifest.json'}:
            raise ValueError('Unexpected, duplicated, or missing archive member')
        if any(i.file_size > MAX_BUNDLE_BYTES or i.flag_bits & 1 for i in z.infolist()):
            raise ValueError('Oversized or encrypted archive member')
        manifest = json.loads(z.read('manifest.json'))
        if manifest.get('schema')!=VERSION or set(manifest.get('items',{})) != set(FILES):
            raise ValueError('Unknown or incomplete manifest')
        for name in FILES:
            b = z.read(name)
            if sha256(b).hexdigest()!=manifest['items'][name]['sha256'] or len(b)!=manifest['items'][name]['bytes']:
                raise ValueError(f'Bundle tampering or corruption: {name}')
        report = json.loads(z.read('report.json'))
        if report.get('schema')!=VERSION or report.get('data_mode')!=manifest.get('data_mode'):
            raise ValueError('Mismatch between report and manifest')
    return {'verified':True, 'file_count':len(FILES)+1, 'status':'CONTENT_INTEGRITY_ONLY_NOT_SIGNED',
            'data_mode':report['data_mode'], 'summary':report['summary']}


def main() -> None:
    ap=argparse.ArgumentParser(description='Offline, review-only NDG/concrete multi-case evidence pack')
    sp=ap.add_subparsers(dest='command',required=True)
    b=sp.add_parser('build'); b.add_argument('--input',type=Path,required=True); b.add_argument('--output',type=Path,required=True)
    mode=b.add_mutually_exclusive_group(required=True)
    mode.add_argument('--synthetic-demo',action='store_true')
    mode.add_argument('--authorized-data',action='store_true',help='Operator confirms data is authorized and sanitized')
    v=sp.add_parser('verify'); v.add_argument('--bundle',type=Path,required=True)
    args=ap.parse_args()
    try:
        result=build(args.input,args.output,mode='synthetic' if args.synthetic_demo else 'authorized') if args.command=='build' else verify(args.bundle)
    except (ValueError, OSError, zipfile.BadZipFile, KeyError) as exc:
        ap.exit(2, f'Error: {exc}\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__': main()
