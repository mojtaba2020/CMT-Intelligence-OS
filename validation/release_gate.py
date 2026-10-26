"""Fail-closed evidence gate. Never a substitute for independent professional approvals.

Strongly prefer false negatives to a false 'production ready' signal.
Accepted evidence *metadata* is not proof of authenticity; external audit is required.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from pathlib import Path
from validation.pilot_benchmark import benchmark
from server.pilot import TEST_TYPES

SECURITY_CONTROLS=(
    'network_tls','identity_mfa','encryption_at_rest','backup_encryption',
    'restore_drill','penetration_review','external_audit_anchor',
    'tenant_isolation','vendor_contract_test','operations_monitoring',
)
SHA=re.compile(r'^[a-fA-F0-9]{64}$')


def release_gate(matrix_rows, benchmark_rows, security, *, min_fields=200,
                 min_critical=100, min_accuracy=0.98):
    issues=[]
    rows=list(matrix_rows)
    by_type={}
    for i,row in enumerate(rows, start=2):
        typ=row.get('test_type','').strip()
        if typ not in TEST_TYPES or typ in by_type:
            issues.append(f'method matrix row {i}: unknown/duplicate test type')
        else:by_type[typ]=row
    for typ in sorted(TEST_TYPES):
        r=by_type.get(typ)
        if not r:
            issues.append('method approval missing: '+typ);continue
        keys=('method_reference','method_edition','spec_policy_reference','reviewer','review_date','evidence_sha256')
        if r.get('state','').strip().lower()!='approved' or any(not r.get(k,'').strip() for k in keys) or not SHA.fullmatch(r.get('evidence_sha256','').strip()):
            issues.append('method has no independently documented lab approval: '+typ)
    if not isinstance(security,dict):
        security={};issues.append('security assessment missing/invalid')
    for name in SECURITY_CONTROLS:
        item=security.get(name)
        if not isinstance(item,dict) or item.get('state')!='verified' or not item.get('reviewer') or not SHA.fullmatch(item.get('evidence_sha256','')):
            issues.append('security/deployment control unverified: '+name)
    try:
        metrics=benchmark(benchmark_rows)
        if 'synthetic' in metrics['by_source']:
            # Synthetic benchmarks may coexist for development but are never scored for release.
            pass
        authorized=metrics['by_source'].get('authorized',{})
        if authorized.get('labeled_fields',0)<min_fields:
            issues.append('not enough authorized, independently labeled fields')
        if authorized.get('critical_fields',0)<min_critical:
            issues.append('not enough authorized critical fields')
        if authorized.get('critical_errors_or_abstentions',float('inf'))!=0:
            issues.append('critical extraction errors/abstentions present')
        if authorized.get('field_accuracy') is None or authorized['field_accuracy']<min_accuracy:
            issues.append('authorized field accuracy below configured pilot target')
        missing=TEST_TYPES - set(authorized.get('method_mix',{}))
        if missing:issues.append('missing authorized method coverage: '+', '.join(sorted(missing)))
        if authorized.get('timed_observations',0)==0:
            issues.append('no paired, measured manual vs assisted timing')
        elif authorized.get('net_seconds_saved',0)<=0:
            issues.append('no net time saving after corrections')
    except Exception as e:
        metrics={'error':str(e)}
        issues.append('benchmark invalid')
    return {'schema':'cmt-release-evidence-gate-v1','release_decision':'BLOCKED' if issues else 'EVIDENCE_REVIEW_REQUIRED',
            'checks':{'method_count':len(by_type),'expected_methods':len(TEST_TYPES),
                      'security_control_count':len(SECURITY_CONTROLS)},
            'issues':issues,'benchmark':metrics,
            'disclaimer':'Even a clear automated gate is NOT production approval: authenticity, method licensing, independent review, engineering responsibility, security review, legal review and vendor consent remain human obligations.'}


def main():
    p=argparse.ArgumentParser(description='CMT evidence release gate - offline and fail-closed')
    p.add_argument('--methods',type=Path,required=True)
    p.add_argument('--benchmark',type=Path,required=True)
    p.add_argument('--security',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    with a.methods.open(encoding='utf-8-sig',newline='') as f: method_rows=list(csv.DictReader(f))
    with a.benchmark.open(encoding='utf-8-sig',newline='') as f: benchmark_rows=list(csv.DictReader(f))
    result=release_gate(method_rows,benchmark_rows,json.loads(a.security.read_text(encoding='utf-8')))
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f"{result['release_decision']} / {len(result['issues'])} blockers (report: {a.out})")
    # any result is nonproduction and requires human review; exit !=0 on actual blockers
    return 2 if result['issues'] else 0

if __name__=='__main__':raise SystemExit(main())
