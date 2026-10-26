"""Local-only consistent SQLite backup + auditable integrity test.

No encrypted or offsite backup; do not use for confidential employer data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from .pilot import db_path, readonly, verify_audit


def hash_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def verify_file(path):
    p=Path(path).expanduser().resolve()
    if not p.is_file():raise FileNotFoundError(p)
    uri='file:'+str(p).replace('?','%3F').replace('#','%23')+'?mode=ro'
    con=sqlite3.connect(uri,uri=True)
    con.row_factory=sqlite3.Row
    try:
        check=con.execute('PRAGMA integrity_check').fetchone()[0]
        audit=verify_audit(con)
        return {'path':str(p),'sqlite_integrity':check,'audit':audit,'sha256':hash_file(p),
                'ok':check=='ok' and audit['ok'] is True}
    finally:con.close()


def backup(output):
    dst=Path(output).expanduser().resolve();src=db_path()
    if src==dst:raise ValueError('Backup target cannot be the original database')
    if not src.is_file():raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():raise FileExistsError('Refusing to overwrite an existing backup')
    temp=dst.with_name(dst.name+'.partial')
    if temp.exists():raise FileExistsError('Previous partial file exists')
    try:
        with sqlite3.connect(str(src)) as source,sqlite3.connect(str(temp)) as target:
            source.backup(target)
        result=verify_file(temp)
        if not result['ok']:
            raise ValueError('Backup verification failed; refusing to publish backup')
        temp.rename(dst)
        dst.chmod(0o600)
        result['path']=str(dst)
        return result
    finally:
        if temp.exists():temp.unlink()


def restore_to_new_file(backup_file, destination):
    """Recovery drill to a NEW file only. Never replaces the active database.

    Operations should additionally test a restart, user access and audit integrity.
    """
    src=Path(backup_file).expanduser().resolve()
    dst=Path(destination).expanduser().resolve()
    if not src.is_file():raise FileNotFoundError(src)
    if src==dst or dst==db_path():raise ValueError('Cannot restore over source or live database')
    if dst.exists():raise FileExistsError('Refusing to overwrite recovery destination')
    check=verify_file(src)
    if not check['ok']:raise ValueError('Backup is corrupt or audit verification failed')
    dst.parent.mkdir(parents=True,exist_ok=True)
    tmp=dst.with_name(dst.name+'.restore-partial')
    if tmp.exists():raise FileExistsError('Incomplete prior restore exists')
    try:
        # Consistent snapshot from an immutable backup using SQLite's native API.
        source=sqlite3.connect('file:'+str(src)+'?mode=ro',uri=True)
        try:
            with sqlite3.connect(str(tmp)) as target:source.backup(target)
        finally:source.close()
        verify=verify_file(tmp)
        if not verify['ok'] or verify['sha256'] != check['sha256']:
            raise ValueError('Restored database failed verification or changed checksum')
        tmp.rename(dst)
        dst.chmod(0o600)
        verify['path']=str(dst)
        verify['recovery_mode']='new_file_only; no active database replaced'
        return verify
    finally:
        if tmp.exists():tmp.unlink()


def main():
    p=argparse.ArgumentParser(description='Local SQLite snapshot and audit verification. No cloud upload.')
    p.add_argument('mode',choices=['backup','verify','restore-test']);p.add_argument('filename');p.add_argument('destination',nargs='?')
    args=p.parse_args()
    if args.mode=='restore-test' and not args.destination:
        p.error('restore-test needs backup filename and NEW destination file')
    result=(backup(args.filename) if args.mode=='backup' else
            restore_to_new_file(args.filename,args.destination) if args.mode=='restore-test' else
            verify_file(args.filename))
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if not result['ok']:raise SystemExit(1)

if __name__=='__main__':main()
