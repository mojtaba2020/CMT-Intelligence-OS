"""CMT v1.4 local handoff CLI. No network access and no ElmTree writes.

Examples:
 python -m bridge.cli bundle records.json profile.json --output handoff.zip --synthetic-demo
 python -m bridge.cli verify handoff.zip --output validation.json
 python -m bridge.cli audit-compare records.json profile.json exported.csv --output differences.json --synthetic-demo
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import tempfile
from .core import export_csv,reconciliation,sha256
from .assurance import handoff_bundle, verify_bundle, reconcile_strict, prepare_strict, preflight


def load_json(path:Path):
    if path.stat().st_size>5_000_000: raise ValueError('JSON file exceeds 5 MB')
    return json.loads(path.read_text(encoding='utf-8'))


def write_safely(path:Path,contents:bytes,*,force=False):
    if path.exists() and not force:
        raise ValueError(f'Output already exists: {path} (use --force to replace explicitly)')
    if not path.parent.is_dir():raise ValueError('Output directory does not exist')
    fd,name=tempfile.mkstemp(prefix='.cmt-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(contents);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def main(argv=None):
    p=argparse.ArgumentParser(description='CMT vendor-neutral exchange, NOT an ElmTree integration')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('prepare','compare','bundle','verify','audit-compare','preflight'):
        a=sub.add_parser(name)
        if name=='verify':
            a.add_argument('handoff_zip',type=Path)
        else:
            a.add_argument('cmt_json',type=Path)
            a.add_argument('mapping_json',type=Path)
            if name in ('compare','audit-compare'):
                a.add_argument('operator_csv',type=Path)
            a.add_argument('--synthetic-demo',action='store_true',help='Allow explicitly labeled fictional training records')
        a.add_argument('--output',required=True,type=Path)
        a.add_argument('--force',action='store_true',help='Explicitly replace output file (and manifest for prepare)')
    args=p.parse_args(argv)
    if args.command=='verify':
        result=verify_bundle(args.handoff_zip.read_bytes())
        raw=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
        write_safely(args.output,raw,force=args.force)
        print(json.dumps(result))
        return
    data=load_json(args.cmt_json);profile=load_json(args.mapping_json)
    demo=args.synthetic_demo
    if args.command=='bundle':
        content,manifest=handoff_bundle(data,profile,demo=demo)
        result=verify_bundle(content)
        write_safely(args.output,content,force=args.force)
        print(json.dumps({'output':str(args.output),'verification':result}))
    elif args.command=='preflight':
        result=preflight(data,profile,demo=demo)
        public={k:v for k,v in result.items() if k!='eligible_records'}
        write_safely(args.output,(json.dumps(public,ensure_ascii=False,indent=2)+'\n').encode(),force=args.force)
        print(json.dumps({'output':str(args.output),'eligible':result['eligible_count'],'quarantined':result['quarantined_count']}))
    elif args.command=='prepare':
        csv_data,meta,gate=prepare_strict(data,profile,demo=demo)
        manifest=args.output.with_suffix(args.output.suffix+'.manifest.json')
        if (args.output.exists() or manifest.exists()) and not args.force:
            raise ValueError('Output or manifest already exists; use --force to replace')
        write_safely(args.output,csv_data,force=args.force)
        write_safely(manifest,(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode(),force=args.force)
        print(json.dumps({'output':str(args.output),'manifest':str(manifest),'prepared_rows':meta['prepared_rows'],
                          'quarantined':gate['quarantined_count'],'sha256':sha256(csv_data)}))
    elif args.command in ('compare','audit-compare'):
        if args.operator_csv.stat().st_size>3_000_000:raise ValueError('External CSV exceeds 3 MB')
        # v1.4 strict comparison for both names; no permissive legacy bypass.
        report=reconcile_strict(data,args.operator_csv.read_bytes(),profile,demo=demo)
        write_safely(args.output,(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode(),force=args.force)
        print(json.dumps({'output':str(args.output),'comparison_status':report['comparison_status'],
                          'conflicts':len(report['field_conflicts']),
                          'source_quarantine':len(report['source_quarantine'])}))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:
        raise SystemExit('BLOCKED: '+str(exc))
