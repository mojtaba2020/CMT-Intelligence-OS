"""Read-only, local deployment security diagnostics; NOT a penetration test."""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
from .pilot import db_path, readonly, verify_audit


def preflight():
    issues=[];observations={}
    db=db_path()
    observations['database_exists']=db.is_file()
    observations['database_location']=str(db)
    if not db.is_file():
        issues.append('No initialized pilot database')
    else:
        try:
            if os.name=='posix':
                mode=stat.S_IMODE(db.stat().st_mode)
                observations['db_permissions_octal']=oct(mode)
                if mode & 0o077:issues.append('Database is accessible to group or other users')
                parent_mode=stat.S_IMODE(db.parent.stat().st_mode)
                if parent_mode & 0o077:issues.append('Database directory too permissive')
            with readonly() as con:
                audit=verify_audit(con)
                observations['audit_ok']=audit['ok']
                if not audit['ok']:issues.append('Database audit consistency failed')
                count=con.execute('SELECT role,count(*) n FROM users WHERE active=1 GROUP BY role').fetchall()
                roles={r['role']:r['n'] for r in count}
                observations['active_roles']=roles
                if not roles.get('engineer') or not roles.get('technician'):
                    issues.append('Separate technician and engineer accounts are required')
        except Exception:
            issues.append('Could not safely read database integrity/roles')
    observations['model_api_key_configured']=bool(os.getenv('OPENAI_API_KEY'))
    # Unmet requirements are intentional; no certificate can be fabricated by this script.
    hard_stops=('No organization-managed MFA/SSO', 'No audited TLS deployment',
                'No managed encryption-at-rest and key rotation',
                'No production disaster recovery testing',
                'No independent penetration assessment or multi-tenant isolation validation',
                'No externally verifiable engineering signature or lab method validation')
    return {'schema':'cmt-local-preflight-v1','local_issue_count':len(issues),
            'local_issues':issues,'observations':observations,'production_blockers':list(hard_stops),
            'production_ready':False}

if __name__=='__main__':
    print(json.dumps(preflight(),indent=2,ensure_ascii=False))
