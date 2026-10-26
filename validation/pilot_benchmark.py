"""Auditable, offline CSV benchmark for human-labeled CMT extraction and paired time tasks.

A valid gold row is not proof that the underlying engineering record is correct.
All time observations include correction time. Synthetic and authorized data are
reported SEPARATELY and never silently combined. No network or AI call.
"""
from __future__ import annotations
import argparse
import csv
from collections import defaultdict
import json
from math import sqrt, isfinite
from pathlib import Path

FIELDS=('case_id','source','test_type','field','gold','predicted','tolerance','critical',
        'manual_seconds','assisted_seconds','correction_seconds')
SOURCES={'synthetic','authorized'}


def parse_number(s, label, *, nonnegative=False):
    try:
        v=float(s)
        if not isfinite(v) or (nonnegative and v<0):raise ValueError
        return v
    except (TypeError,ValueError,OverflowError):
        raise ValueError(f'{label} must be a finite numeric value') from None


def wilson(success,total,z=1.96):
    if not total:return None
    p=success/total;d=1+z*z/total
    return [round((p+z*z/(2*total)-z*sqrt((p*(1-p)+z*z/(4*total))/total))/d,4),
            round((p+z*z/(2*total)+z*sqrt((p*(1-p)+z*z/(4*total))/total))/d,4)]


def benchmark(rows):
    output={};by_source=defaultdict(list)
    used=set()
    for line,r in enumerate(rows,start=2):
        if not set(FIELDS).issubset(r):raise ValueError('CSV has missing columns')
        src=r['source'].strip().lower()
        if src not in SOURCES:raise ValueError(f'line {line}: unknown data origin')
        if not r['gold'].strip() or not r['case_id'].strip() or not r['field'].strip():
            raise ValueError(f'line {line}: missing gold/case ID/field')
        key=(src,r['case_id'].strip(),r['field'].strip())
        if key in used:raise ValueError(f'line {line}: duplicate labeled field')
        used.add(key)
        iscritical=r['critical'].strip().lower()
        if iscritical not in ('true','false','1','0'):raise ValueError(f'line {line}: invalid critical boolean')
        tol=parse_number(r['tolerance'],f'line {line} tolerance',nonnegative=True)
        pred=r['predicted'].strip();gold=r['gold'].strip()
        abstain=not bool(pred)
        if not abstain:
            # numeric fields use numeric tolerance. IDs compare normalized whitespace/case only.
            try:
                x=parse_number(gold,'gold');y=parse_number(pred,'pred')
                match=abs(x-y)<=tol+1e-12
            except ValueError:
                match=' '.join(gold.upper().split())==' '.join(pred.upper().split())
        else:match=False
        raw_times=[r['manual_seconds'].strip(),r['assisted_seconds'].strip(),r['correction_seconds'].strip()]
        if any(raw_times) and not all(raw_times):
            raise ValueError(f'line {line}: paired time fields must all be present or all empty')
        time_data=None
        if all(raw_times):
            manual,assisted,correct=(parse_number(x,f'line {line} time',nonnegative=True) for x in raw_times)
            if manual<=0:raise ValueError(f'line {line}: baseline time must be >0')
            time_data=(manual,assisted,correct)
        by_source[src].append({'critical':iscritical in ('true','1'),
                               'match':match,'abstain':abstain,'time':time_data,'type':r['test_type'].strip()})
    for src,items in sorted(by_source.items()):
        n=len(items);matches=sum(i['match'] for i in items)
        critical=[i for i in items if i['critical']]
        timed=[i['time'] for i in items if i['time']]
        baseline=sum(v[0] for v in timed)
        assisted=sum(v[1]+v[2] for v in timed)
        saved=baseline-assisted
        output[src]={'labeled_fields':n,'correct_fields':matches,
                     'field_accuracy':round(matches/n,4) if n else None,
                     'field_accuracy_95pct_wilson':wilson(matches,n),
                     'abstentions':sum(i['abstain'] for i in items),
                     'critical_fields':len(critical),'critical_errors_or_abstentions':sum(not i['match'] for i in critical),
                     'timed_observations':len(timed),
                     'baseline_total_seconds':round(baseline,3),'assisted_and_correction_total_seconds':round(assisted,3),
                     'net_seconds_saved':round(saved,3),
                     'net_percent_saved':round(100*saved/baseline,2) if baseline else None,
                     'slower_observations':sum(x[0]<(x[1]+x[2]) for x in timed),
                     'method_mix':dict(sorted({i['type']:sum(x['type']==i['type'] for x in items) for i in items}.items()))}
    return {'schema':'cmt-benchmark-v1','dataset_types_never_pooled':True,'by_source':output,
            'caveats':['Unverified external labels are not laboratory truth.',
                       'Small samples have wide confidence intervals.',
                       'No ASTM compliance or labor savings at GET implied.',
                       'Paired timing must reflect actual comparable tasks and all review/correction time.']}


def main():
    p=argparse.ArgumentParser(description='Offline CMT synthetic/authorized labeled benchmark; no uploads')
    p.add_argument('csv_path',type=Path)
    p.add_argument('--json-out',type=Path)
    args=p.parse_args()
    with args.csv_path.open(encoding='utf-8-sig',newline='') as f:
        result=benchmark(csv.DictReader(f))
    content=json.dumps(result,ensure_ascii=False,indent=2)
    if args.json_out:
        args.json_out.write_text(content+'\n',encoding='utf-8')
    print(content)

if __name__=='__main__':main()
