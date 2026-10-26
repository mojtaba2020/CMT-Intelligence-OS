"""Offline verification of portable CMT review worksheets, not electronic signatures."""
from pathlib import Path
import argparse,hashlib,json
from .pilot import canonical

def verify_report(document):
    if not isinstance(document,dict) or set(('payload','payload_sha256'))-set(document):
        return {'ok':False,'reason':'Missing report payload/checksum'}
    try:
        checksum=hashlib.sha256(canonical(document['payload']).encode()).hexdigest()
        return {'ok':checksum==document['payload_sha256'],
                'actual_sha256':checksum,'claimed_sha256':document['payload_sha256'],
                'warning':'Checksum is not a signature, certification or external notarization.'}
    except (TypeError, ValueError, OverflowError):
        return {'ok':False,'reason':'Invalid report data'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Check integrity of exported review worksheet JSON')
    parser.add_argument('report_json')
    args=parser.parse_args()
    print(json.dumps(res:=verify_report(json.loads(Path(args.report_json).read_text())),indent=2))
    if not res['ok']:raise SystemExit(1)
