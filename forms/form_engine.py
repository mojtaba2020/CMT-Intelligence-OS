"""Conservative cross-form reviewer for manually verified data or human-reviewed AI drafts.

Not optical recognition, ASTM acceptance, or ElmTree integration. Never accept actual
employer/customer documents without explicit authorization and protection controls.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from math import isfinite
from pathlib import Path
import argparse
import json

TYPES = {'general_report', 'concrete_strength', 'density_sheet', 'rebar_observation'}


def _number(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v):
        return None
    return float(v)


def _add(findings, code, severity, message, record=None):
    findings.append({'code':code,'severity':severity,'message':message,
                     'record':record or 'packet'})


def inspect_packet(packet: dict, *, dry_pcf_tolerance=1.5, compaction_pct_tolerance=0.5) -> dict:
    """Fail-closed integrity/preflight checks, never an acceptance decision.

    Expected input is the neutral `forms/examples/SYNTHETIC_PACKET.json` schema.
    Tolerances are demonstration QA review flags, *not* ASTM/project thresholds.
    """
    if not isinstance(packet, dict) or not isinstance(packet.get('forms'), list):
        raise ValueError('packet.forms must be a list')
    if len(packet['forms']) > 500:
        raise ValueError('packet contains too many forms')
    findings = []; forms = packet['forms']
    counters = Counter(); type_counts = Counter()
    series = defaultdict(list); all_rows = []
    bytype = defaultdict(list); seen_ids = set()
    declared_project = packet.get('project_key'); declared_date = packet.get('work_date')
    for i,form in enumerate(forms):
        if not isinstance(form,dict): raise ValueError(f'form {i} must be an object')
        fid=form.get('form_id')
        if not isinstance(fid,str) or not fid.strip() or fid in seen_ids:
            _add(findings,'FORM_ID_MISSING_OR_DUPLICATE','BLOCK','Form identifier missing or repeated',str(fid or i))
        seen_ids.add(fid)
        kind=form.get('form_type'); type_counts[str(kind)] += 1
        if kind not in TYPES:
            _add(findings,'UNKNOWN_FORM_TYPE','BLOCK','Unknown form type',str(fid)); continue
        bytype[kind].append(form)
        project=form.get('project_key')
        if not project or (declared_project is not None and project != declared_project):
            _add(findings,'PROJECT_ID_MISMATCH','BLOCK','Missing/mismatched project identifier',fid)
        date=form.get('work_date')
        if not date or (declared_date is not None and date != declared_date):
            _add(findings,'WORK_DATE_MISMATCH','REVIEW','Missing or inconsistent work date',fid)
        if form.get('human_verified') is not True:
            _add(findings,'HUMAN_VERIFICATION_REQUIRED','BLOCK','Document values have not been verified by a human',fid)
        if kind != 'density_sheet': continue
        sid=form.get('series_id')
        pn=form.get('page_number'); pc=form.get('page_count')
        if not sid or not isinstance(pn,int) or isinstance(pn,bool) or not isinstance(pc,int) or isinstance(pc,bool) or pn<1 or pc<1 or pn>pc:
            _add(findings,'PAGE_METADATA_INVALID','BLOCK','Invalid/missing page sequence metadata',fid)
        else: series[sid].append((pn,pc,fid))
        rows=form.get('rows',[])
        if not isinstance(rows,list): raise ValueError(f'form {fid}: rows must be a list')
        if len(rows)>300:raise ValueError(f'form {fid}: too many rows')
        for rowidx,row in enumerate(rows):
            if not isinstance(row,dict):raise ValueError('density row must be an object')
            if not row.get('test_id'):
                _add(findings,'TEST_ID_MISSING','BLOCK','Density test ID is missing',f'{fid}/row-{rowidx+1}')
            all_rows.append((fid,sid,row))
    for sid,pages in series.items():
        seen=Counter(p[0] for p in pages)
        totals={p[1] for p in pages}
        if len(totals)>1:
            _add(findings,'PAGE_TOTAL_INCONSISTENT','BLOCK','Different declared page totals within one series',sid)
        if any(x>1 for x in seen.values()):
            _add(findings,'DUPLICATE_PAGE','BLOCK','Duplicate page number in same series',sid)
        if len(totals)==1:
            missing=sorted(set(range(1,next(iter(totals))+1))-set(seen))
            if missing: _add(findings,'MISSING_DENSITY_PAGES','BLOCK',f'Missing page(s): {missing}',sid)
    seen_test_ids=set()
    for fid,sid,row in all_rows:
        rid=str(row.get('test_id') or ''); ref=f'{fid}/{rid}'
        if rid and (sid,rid) in seen_test_ids:
            _add(findings,'DUPLICATE_TEST_ID','BLOCK','Repeated test ID in a single density series',ref)
        seen_test_ids.add((sid,rid))
        moisture=_number(row.get('field_moisture_percent'))
        wet=_number(row.get('field_wet_density_pcf'))
        dry=_number(row.get('field_dry_density_pcf'))
        mdd=_number(row.get('max_dry_density_pcf'))
        reported=_number(row.get('reported_compaction_percent'))
        if (moisture is None or wet is None or dry is None or mdd is None or
            not 0<=moisture<=100 or not 0<dry<=300 or not 0<wet<=350 or not 0<mdd<=300):
            _add(findings,'DENSITY_MISSING_OR_INVALID','BLOCK','Required density/moisture values missing or invalid',ref)
            continue
        calc_dry=wet/(1+moisture/100)
        if abs(dry-calc_dry)>dry_pcf_tolerance:
            _add(findings,'DRY_DENSITY_RECHECK','REVIEW',f'Reported dry density differs from wet/(1+moisture): {dry:.2f} versus {calc_dry:.2f} pcf',ref)
        calc_compaction=100*dry/mdd
        if reported is None or not 0<=reported<=200:
            _add(findings,'COMPACTION_MISSING_OR_INVALID','BLOCK','Reported compaction percent missing or invalid',ref)
        elif abs(reported-calc_compaction)>compaction_pct_tolerance:
            _add(findings,'COMPACTION_RECHECK','REVIEW',f'Reported compaction differs from dry/MDD: {reported:.2f} versus {calc_compaction:.2f}%',ref)
        if row.get('reported_pass_fail') not in ('P','F','Pass','Fail',None,''):
            _add(findings,'STATUS_NEEDS_REVIEW','REVIEW','Unrecognized handwritten Pass/Fail entry',ref)
        counters['density_detail_rows']+=1
    if bytype['general_report']:
        # Count comparison only if every density sheet has a well-defined sequence.
        for report in bytype['general_report']:
            if report.get('reported_density_tests') is not None:
                n=report['reported_density_tests']
                if not isinstance(n,int) or isinstance(n,bool) or n<0:
                    _add(findings,'SUMMARY_COUNT_INVALID','BLOCK','Daily density count is not a nonnegative integer',report['form_id'])
                elif n!=len(all_rows):
                    _add(findings,'DENSITY_COUNT_RECHECK','REVIEW',f'Daily report lists {n} density tests; detail pages include {len(all_rows)} rows (completeness not yet certified)',report['form_id'])
            if report.get('reported_concrete_cylinders_cast') is not None and bytype['concrete_strength']:
                recorded=report['reported_concrete_cylinders_cast']
                listed=sum(len(f.get('cylinders',[])) for f in bytype['concrete_strength'])
                if not isinstance(recorded,int) or isinstance(recorded,bool) or recorded<0:
                    _add(findings,'CYLINDER_COUNT_INVALID','BLOCK','Cylinder cast count invalid',report['form_id'])
                elif recorded!=listed:
                    _add(findings,'CYLINDER_COUNT_RECHECK','REVIEW',f'Daily cylinder count {recorded} versus {listed} cylinder entries; check casting versus lab/sample timing',report['form_id'])
    for concrete in bytype['concrete_strength']:
        if not isinstance(concrete.get('cylinders',[]),list):
            _add(findings,'CYLINDERS_FORMAT_INVALID','BLOCK','Cylinder entries not a list',concrete['form_id'])
    return {'source':'synthetic_or_authorized_human_verified_only',
            'automated_material_acceptance':False,
            'ready_for_elmtree_import':False,
            'forms_count':len(forms),'type_counts':dict(type_counts),
            'density_detail_rows':len(all_rows),
            'findings':findings,'finding_counts':dict(Counter(f['severity'] for f in findings)),
            'review_required':True,
            'note':'Screening QA only; an engineer/authorized reviewer must verify source forms, project specifications, and acceptance criteria.'}


def render_review_html(result:dict) -> str:
    """Self-contained, read-only HTML; escape all user-supplied values."""
    rows=''.join('<tr><td>'+escape(str(x['severity']))+'</td><td>'+escape(str(x['code']))+
                 '</td><td>'+escape(str(x['record']))+'</td><td>'+escape(str(x['message']))+'</td></tr>'
                 for x in result['findings'])
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>CMT Forms Review</title><style>
body{background:#0b1527;color:#e7eef7;font:16px system-ui;margin:0;padding:24px;line-height:1.5}
main{max-width:1050px;margin:auto}h1{color:#5be0c8}.notice{border:1px solid #6b7e96;border-radius:12px;padding:18px;background:#162940}
table{border-collapse:collapse;width:100%;margin-top:24px}td,th{border-bottom:1px solid #43566a;padding:11px;text-align:left;vertical-align:top}
.warning{color:#ffcb7c}small{color:#a9bbcf}</style></head><body><main><h1>CMT Intelligence OS · Field Forms Review</h1>
<p class="notice"><strong>SYNTHETIC REFERENCE DEMO — NOT A SIGNED ENGINEERING REPORT.</strong><br>
No ElmTree connection; all values require human verification. No automated material acceptance.</p>
<p>Forms: '''+str(result['forms_count'])+' · Density rows: '+str(result['density_detail_rows'])+
    ' · Findings: '+str(len(result['findings']))+'''</p><h2>Findings for human review</h2>
<table><thead><tr><th>Priority</th><th>Issue</th><th>Record</th><th>Detail</th></tr></thead><tbody>'''+rows+
    '''</tbody></table><p><small>Generated by an offline cross-form screening engine. Tolerances are demonstration QA flags, not project acceptance criteria.</small></p></main></body></html>''')


def main():
    p=argparse.ArgumentParser(description='Offline CMT cross-form preflight; no AI/ElmTree')
    p.add_argument('input',type=Path)
    p.add_argument('--json-output',type=Path)
    p.add_argument('--html-output',type=Path)
    args=p.parse_args()
    data=json.loads(args.input.read_text(encoding='utf8'))
    result=inspect_packet(data)
    if args.json_output:args.json_output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    if args.html_output:args.html_output.write_text(render_review_html(result),encoding='utf8')
    if not args.json_output: print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
