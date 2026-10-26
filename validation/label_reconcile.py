"""Offline, fail-closed double-transcription adjudication for CMT pilot labels.

This tool does not establish that a label is physically correct, does not call AI,
never uploads files, and does not infer material acceptance.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

FIELDS = ('case_id','source','test_type','field','labeler_a_id','labeler_a',
          'labeler_b_id','labeler_b','adjudicator_id','adjudicated','predicted',
          'tolerance','critical','manual_seconds','assisted_seconds','correction_seconds')
OUTPUT = ('case_id','source','test_type','field','gold','predicted','tolerance',
          'critical','manual_seconds','assisted_seconds','correction_seconds')


def normalize(value):
    return ' '.join((value or '').split())


def reconcile(rows):
    results=[]; conflicts=[]; ids=set()
    for line,row in enumerate(rows, start=2):
        if not set(FIELDS).issubset(row):
            raise ValueError('Missing required double-label columns')
        key=(row['source'].strip(),row['case_id'].strip(),row['field'].strip())
        if not all(key) or key in ids:
            raise ValueError(f'line {line}: missing or duplicate source/case/field')
        ids.add(key)
        a=row['labeler_a_id'].strip(); b=row['labeler_b_id'].strip()
        if not a or not b or a==b:
            raise ValueError(f'line {line}: two distinct labeler identities required')
        av=normalize(row['labeler_a']);bv=normalize(row['labeler_b'])
        if not av or not bv:
            raise ValueError(f'line {line}: both labelers must independently transcribe a value')
        if av==bv:
            if row['adjudicated'].strip():
                raise ValueError(f'line {line}: adjudication must be blank for agreed labels')
            gold=av
        else:
            judge=row['adjudicator_id'].strip(); gold=normalize(row['adjudicated'])
            if not judge or judge in (a,b) or not gold:
                conflicts.append({'line':line,'source':key[0],'case_id':key[1],'field':key[2],
                                  'reason':'Independent adjudicator and resolved label required'})
                continue
        results.append({k: (gold if k=='gold' else row[k].strip()) for k in OUTPUT})
    return results, conflicts


def run(infile:Path, outfile:Path, manifest:Path):
    raw=infile.read_bytes()
    with io.StringIO(raw.decode('utf-8-sig')) as f:
        resolved,conflicts=reconcile(csv.DictReader(f))
    info={'schema':'cmt-two-label-review-v1','input_sha256':hashlib.sha256(raw).hexdigest(),
          'resolved_fields':len(resolved),'unresolved_conflicts':conflicts,
          'gold_is_human_consensus_not_method_certification':True}
    if conflicts:
        raise ValueError(json.dumps(info, ensure_ascii=False))
    # Fail before writing anything when no valid labels were present.
    if not resolved:raise ValueError('No resolved labels')
    if outfile.resolve()==infile.resolve() or manifest.resolve() in (outfile.resolve(),infile.resolve()):
        raise ValueError('Output paths must be distinct from input and each other')
    with outfile.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=OUTPUT);w.writeheader();w.writerows(resolved)
    manifest.write_text(json.dumps(info,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return info


if __name__=='__main__':
    p=argparse.ArgumentParser(description='Offline independent two-label reconciliation')
    p.add_argument('input',type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--manifest',required=True,type=Path)
    a=p.parse_args();print(json.dumps(run(a.input,a.out,a.manifest),indent=2))
