"""LOCAL ONLY multiuser pilot sandbox: SQLite, role checks, immutable revisions and hash-chain audit.

Not a digital signature, regulatory approval, secure cloud deployment, or validation of CMT methods.
Run uvicorn with --host 127.0.0.1, NEVER 0.0.0.0. No confidential records.
"""
from __future__ import annotations
import argparse
import getpass
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Literal
from .quality import audit_quality
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix='/api/pilot', tags=['local-pilot'])
SESSION_SECONDS = 8 * 3600
USERNAME = re.compile(r'^[a-z][a-z0-9_.-]{2,31}$')
ROLE = ('technician', 'engineer')
TEST_TYPES = {'soil','concrete','soil_moisture','atterberg','proctor','sand_cone','sieve','cylinder',
              'unit_weight','asphalt_core','asphalt_voids','rebar_cover','proctor_curve','sieve_stack','cylinder_set'}
ZERO_HASH = '0' * 64


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def db_path() -> Path:
    return Path(os.environ.get('CMT_PILOT_DB', str(Path.home()/'.cmt_intelligence_os'/'pilot.sqlite3'))).expanduser().resolve()


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == 'posix':
        os.chmod(path.parent, 0o700)
    con = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    con.execute('PRAGMA busy_timeout = 10000')
    con.executescript('''
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('technician','engineer')),
        salt TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
      );
      CREATE TABLE IF NOT EXISTS login_attempts (
        username TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0,
        blocked_until INTEGER NOT NULL DEFAULT 0, last_failure INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        csrf_hash TEXT NOT NULL, expires INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS records (
        id TEXT PRIMARY KEY, creator INTEGER NOT NULL REFERENCES users(id),
        current_version INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL CHECK(status IN ('draft','submitted','needs_correction','reviewed','rejected')),
        created_at TEXT NOT NULL, reviewer INTEGER REFERENCES users(id), review_note TEXT,
        reviewed_at TEXT
      );
      CREATE TABLE IF NOT EXISTS revisions (
        record_id TEXT NOT NULL REFERENCES records(id), version INTEGER NOT NULL,
        actor INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, time TEXT NOT NULL,
        PRIMARY KEY (record_id,version)
      );
      CREATE TABLE IF NOT EXISTS audit (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
        event TEXT NOT NULL, record_id TEXT NOT NULL, details TEXT NOT NULL,
        prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL
      );
    ''')
    if os.name == 'posix':
        os.chmod(path, 0o600)
    return con


@contextmanager
def transaction():
    con = connect()
    try:
        con.execute('BEGIN IMMEDIATE')
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


@contextmanager
def readonly():
    con=connect()
    try:yield con
    finally:con.close()


def password_digest(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


def create_user(username: str, role: str, password: str) -> None:
    if not USERNAME.fullmatch(username) or role not in ROLE or len(password) < 12 or len(password) > 256:
        raise ValueError('Username 3-32 lowercase chars and password 12-256 characters required')
    salt = secrets.token_bytes(16)
    with transaction() as con:
        con.execute('INSERT INTO users (username,role,salt,password_hash) VALUES (?,?,?,?)',
                    (username,role,salt.hex(),password_digest(password,salt)))
        append_audit(con, username, 'USER_CREATED', '-', {'role':role})


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def append_audit(con: sqlite3.Connection, actor: str, event: str, record_id: str, details: dict):
    prior = con.execute('SELECT event_hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
    prev = prior['event_hash'] if prior else ZERO_HASH
    payload = {'at':utc(), 'actor':actor, 'event':event, 'record_id':record_id, 'details':details}
    digest=hashlib.sha256((prev+'\n'+canonical(payload)).encode()).hexdigest()
    con.execute('INSERT INTO audit (at,actor,event,record_id,details,prev_hash,event_hash) VALUES (?,?,?,?,?,?,?)',
                (payload['at'],actor,event,record_id,canonical(details),prev,digest))


def verify_audit(con: sqlite3.Connection):
    """Verify event hash chain AND immutable revision digests / current record states.

    Still not protection against an administrator who rewrites every hash and record.
    """
    prev=ZERO_HASH
    rows=con.execute('SELECT * FROM audit ORDER BY seq').fetchall()
    state={}
    for row in rows:
        try:
            details=json.loads(row['details'])
            payload={'at':row['at'],'actor':row['actor'],'event':row['event'],
                     'record_id':row['record_id'],'details':details}
            expected=hashlib.sha256((prev+'\n'+canonical(payload)).encode()).hexdigest()
        except (ValueError,TypeError,KeyError):
            return {'ok':False,'first_bad_seq':row['seq'],'reason':'Invalid audit event data'}
        if row['prev_hash']!=prev or row['event_hash']!=expected:
            return {'ok':False,'first_bad_seq':row['seq'],'reason':'Audit chain mismatch'}
        prev=expected
        rid=row['record_id']; event=row['event']; version=details.get('version')
        if event in ('CREATED','REVISED'):
            revision=con.execute('SELECT body FROM revisions WHERE record_id=? AND version=?',(rid,version)).fetchone()
            if (not revision or hashlib.sha256(revision['body'].encode()).hexdigest()!=details.get('content_sha256')):
                return {'ok':False,'first_bad_seq':row['seq'],'reason':'Stored revision digest mismatch'}
            if event=='CREATED' and (rid in state or version!=1):
                return {'ok':False,'first_bad_seq':row['seq'],'reason':'Invalid creation history'}
            if event=='REVISED' and (rid not in state or version!=state[rid]['version']+1 or state[rid]['status']!='needs_correction' and state[rid]['status']!='draft'):
                return {'ok':False,'first_bad_seq':row['seq'],'reason':'Invalid revision transition'}
            state[rid]={'version':version,'status':'draft','reviewer':None,'review_note':None}
        elif event=='SUBMITTED':
            if rid not in state or state[rid]['status']!='draft' or version!=state[rid]['version']:
                return {'ok':False,'first_bad_seq':row['seq'],'reason':'Invalid submit transition'}
            state[rid]['status']='submitted'
        elif event.startswith('REVIEW_'):
            outcome=event[len('REVIEW_'):].lower()
            if rid not in state or outcome not in ('reviewed','needs_correction','rejected') or state[rid]['status']!='submitted' or version!=state[rid]['version']:
                return {'ok':False,'first_bad_seq':row['seq'],'reason':'Invalid review transition'}
            state[rid].update(status=outcome,reviewer=row['actor'],review_note=details.get('note'))
    actual=con.execute('SELECT * FROM records').fetchall()
    if len(actual)!=len(state):
        return {'ok':False,'reason':'Audit-to-record inventory mismatch'}
    for record in actual:
        expected=state.get(record['id'])
        reviewer=con.execute('SELECT username FROM users WHERE id=?',(record['reviewer'],)).fetchone() if record['reviewer'] else None
        name=reviewer['username'] if reviewer else None
        if (expected is None or record['current_version']!=expected['version'] or record['status']!=expected['status']
           or name!=expected['reviewer'] or record['review_note']!=expected['review_note']):
            return {'ok':False,'record_id':record['id'],'reason':'Current record diverges from audit events'}
        count=con.execute('SELECT COUNT(*) AS total FROM revisions WHERE record_id=?',(record['id'],)).fetchone()['total']
        if count!=expected['version']:
            return {'ok':False,'record_id':record['id'],'reason':'Revision inventory mismatch'}
    return {'ok':True,'events_checked':len(rows),'records_checked':len(actual),'head_hash':prev,
            'warning':'Hashes detect unsophisticated alterations only; not an independent signature or external notarization.'}


class Credentials(BaseModel):
    username: str = Field(min_length=3,max_length=32)
    password: str = Field(min_length=1,max_length=256)

class Draft(BaseModel):
    test_type: str = Field(max_length=40)
    project_code: str = Field(min_length=1,max_length=80)
    location: str = Field(min_length=1,max_length=120)
    spec_reference: str = Field(default='',max_length=120)
    evidence_reference: str = Field(default='',max_length=120)
    source: Literal['synthetic','authorized'] = 'synthetic'
    authorization_confirmed: bool = False
    measurement_units: dict[str,str] = Field(default_factory=dict)
    measurements: dict[str,Any]

class Edit(Draft):
    expected_version: int = Field(ge=1)

class VersionAction(BaseModel):
    expected_version: int = Field(ge=1)

class ReviewAction(VersionAction):
    decision: Literal['reviewed','needs_correction','rejected']
    note: str = Field(min_length=10,max_length=2000)


def validate_measurements(value: Any, depth: int=0) -> None:
    if depth>4: raise HTTPException(422, 'Data nesting too deep')
    if isinstance(value, dict):
        if len(value)>100: raise HTTPException(422,'Too many fields')
        for k,v in value.items():
            if not isinstance(k,str) or len(k)>70 or not re.fullmatch(r'[a-zA-Z][\w-]*',k):
                raise HTTPException(422,'Invalid field name')
            validate_measurements(v,depth+1)
    elif isinstance(value,list):
        if len(value)>250: raise HTTPException(422,'Too many measurement rows')
        for v in value:validate_measurements(v,depth+1)
    elif isinstance(value,bool) or value is None: pass
    elif isinstance(value,(int,float)):
        if not math.isfinite(value): raise HTTPException(422,'Non-finite number')
    elif isinstance(value,str):
        if len(value)>1000: raise HTTPException(422,'Measurement text too long')
    else: raise HTTPException(422,'Unsupported field value')


def validated_body(body: Draft) -> str:
    if body.test_type not in TEST_TYPES: raise HTTPException(422, 'Unknown test type')
    if body.source == 'authorized' and not body.authorization_confirmed:
        raise HTTPException(422,'Operator must attest to authorization')
    for key in ('project_code','location'):
        if not getattr(body,key).strip(): raise HTTPException(422,key+' cannot be blank')
    for key in ('spec_reference','evidence_reference'):
        if getattr(body,key) and not getattr(body,key).strip(): raise HTTPException(422,key+' cannot contain only spaces')
    if not body.measurements: raise HTTPException(422,'At least one measurement required')
    if len(body.measurement_units)>60 or any(not re.fullmatch(r'measurements\.[A-Za-z][\w-]{0,69}',key) or len(unit)>20 or not re.fullmatch(r'[a-z0-9/%]+',unit) for key,unit in body.measurement_units.items()):
        raise HTTPException(422,'Invalid measurement unit metadata')
    validate_measurements(body.measurements)
    result=body.model_dump(exclude={'authorization_confirmed'})
    # Backward compatible: legacy revisions were serialized without unit metadata.
    # New units are persisted only when supplied explicitly.
    if not result.get('measurement_units'): result.pop('measurement_units',None)
    serialized=canonical(result)
    if len(serialized.encode()) > 45_000: raise HTTPException(413,'Record too large')
    return serialized


def auth(request: Request):
    token=request.cookies.get('cmt_pilot')
    if not token:raise HTTPException(401,'Sign in required')
    token_hash=hashlib.sha256(token.encode()).hexdigest()
    with readonly() as con:
        row=con.execute('''SELECT u.id,u.username,u.role,s.csrf_hash,s.expires FROM sessions s
           JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND u.active=1''',(token_hash,)).fetchone()
    if row is None or int(row['expires'])<=int(time.time()): raise HTTPException(401,'Session expired')
    if request.method not in ('GET','HEAD','OPTIONS'):
        csrf=request.headers.get('x-cmt-csrf','')
        if not csrf or not hmac.compare_digest(hashlib.sha256(csrf.encode()).hexdigest(),row['csrf_hash']):
            raise HTTPException(403,'CSRF token missing or invalid')
    return dict(row)


def engine(user=Depends(auth)):
    if user['role'] != 'engineer':raise HTTPException(403,'Engineer role required')
    return user


@router.post('/login')
def login(credentials: Credentials, response: Response, request: Request):
    # Local, per-username short lockout. Production needs centralized IAM and MFA.
    failed=False;locked=False
    with transaction() as con:
        now=int(time.time())
        attempt=con.execute('SELECT * FROM login_attempts WHERE username=?',(credentials.username,)).fetchone()
        if attempt is not None and attempt['blocked_until']>now:
            locked=True
        else:
            row=con.execute('SELECT * FROM users WHERE username=? AND active=1',(credentials.username,)).fetchone()
            # A missing user still performs an expensive digest operation.
            if row:
                match=hmac.compare_digest(password_digest(credentials.password,bytes.fromhex(row['salt'])),row['password_hash'])
            else:
                password_digest(credentials.password,b'0'*16)
                match=False
            if not match:
                failures=(attempt['failures'] if attempt and now-attempt['last_failure']<900 else 0)+1
                block=now+900 if failures>=5 else 0
                con.execute('INSERT INTO login_attempts (username,failures,blocked_until,last_failure) VALUES (?,?,?,?) '
                            'ON CONFLICT(username) DO UPDATE SET failures=excluded.failures, '
                            'blocked_until=excluded.blocked_until,last_failure=excluded.last_failure',
                            (credentials.username,failures,block,now))
                failed=True
            else:
                con.execute('DELETE FROM login_attempts WHERE username=?',(credentials.username,))
                token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                con.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                            (hashlib.sha256(token.encode()).hexdigest(),row['id'],hashlib.sha256(csrf.encode()).hexdigest(),now+SESSION_SECONDS))
                append_audit(con,row['username'],'LOGIN','-',{})
    # Raise after commit so lockouts are actually retained.
    if locked:raise HTTPException(429,'Login temporarily restricted; retry later')
    if failed:raise HTTPException(401,'Invalid credentials')
    response.set_cookie('cmt_pilot', token, httponly=True, samesite='strict', secure=request.url.scheme == 'https',
                        max_age=SESSION_SECONDS, path='/api/pilot')
    response.headers['Cache-Control']='no-store'
    return {'username':row['username'],'role':row['role'],'csrf':csrf,
            'disclaimer':'Local experimental workflow only. No licensed engineering signature.'}

@router.get('/me')
def me(user=Depends(auth)):
    return {'username':user['username'],'role':user['role'], 'expires':user['expires']}


@router.post('/logout')
def logout(request: Request,response: Response,user=Depends(auth)):
    token_hash=hashlib.sha256(request.cookies['cmt_pilot'].encode()).hexdigest()
    with transaction() as con:
        con.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash,))
        append_audit(con,user['username'],'LOGOUT','-',{})
    response.delete_cookie('cmt_pilot',path='/api/pilot');return {'ok':True}


def view_record(con,row):
    version=con.execute('SELECT * FROM revisions WHERE record_id=? AND version=?',
                        (row['id'],row['current_version'])).fetchone()
    creator=con.execute('SELECT username FROM users WHERE id=?',(row['creator'],)).fetchone()['username']
    reviewer=con.execute('SELECT username FROM users WHERE id=?',(row['reviewer'],)).fetchone() if row['reviewer'] else None
    return {'id':row['id'],'version':row['current_version'],'status':row['status'],
            'created_at':row['created_at'],'creator':creator,
            'reviewer':reviewer['username'] if reviewer else None,
            'review_note':row['review_note'],'reviewed_at':row['reviewed_at'],
            **json.loads(version['body'])}


@router.post('/qa/preview')
def qa_preview(draft: Draft, user=Depends(auth)):
    # Pydantic and bounding validation first; this returns flags, not certification.
    data=json.loads(validated_body(draft))
    return audit_quality(data['test_type'],data)


@router.post('/records',status_code=201)
def create_record(draft: Draft,user=Depends(auth)):
    data=validated_body(draft);record_id='PILOT-'+secrets.token_hex(8).upper()
    with transaction() as con:
        con.execute('INSERT INTO records (id,creator,status,created_at) VALUES (?,?,?,?)',
                    (record_id,user['id'],'draft',utc()))
        con.execute('INSERT INTO revisions VALUES (?,?,?,?,?)',(record_id,1,user['id'],data,utc()))
        append_audit(con,user['username'],'CREATED',record_id,
                     {'version':1,'content_sha256':hashlib.sha256(data.encode()).hexdigest()})
        rec=con.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone()
        return view_record(con,rec)


@router.get('/records')
def list_records(user=Depends(auth)):
    with readonly() as con:
        if user['role']=='engineer':
            rows=con.execute('SELECT * FROM records ORDER BY created_at DESC,id DESC LIMIT 200').fetchall()
        else:
            rows=con.execute('SELECT * FROM records WHERE creator=? ORDER BY created_at DESC,id DESC LIMIT 200',(user['id'],)).fetchall()
        return {'records':[view_record(con,r) for r in rows]}


def get_owned(con,record_id,user):
    row=con.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone()
    if row is None or (user['role']=='technician' and row['creator']!=user['id']):
        raise HTTPException(404,'Record not found')
    return row


@router.get('/records/{record_id}')
def get_record(record_id:str,user=Depends(auth)):
    with readonly() as con:
        return view_record(con,get_owned(con,record_id,user))


@router.put('/records/{record_id}')
def edit_record(record_id:str,body:Edit,user=Depends(auth)):
    data=validated_body(body)
    with transaction() as con:
        row=get_owned(con,record_id,user)
        if row['creator']!=user['id']:raise HTTPException(403,'Only original author may revise')
        if row['current_version']!=body.expected_version: raise HTTPException(409,'Stale version')
        if row['status'] not in ('draft','needs_correction'):raise HTTPException(409,'Record locked at this stage')
        version=row['current_version']+1
        con.execute('INSERT INTO revisions VALUES (?,?,?,?,?)',(record_id,version,user['id'],data,utc()))
        con.execute('UPDATE records SET current_version=?,status=?,reviewer=NULL,review_note=NULL,reviewed_at=NULL WHERE id=?',
                    (version,'draft',record_id))
        append_audit(con,user['username'],'REVISED',record_id,
                     {'version':version,'content_sha256':hashlib.sha256(data.encode()).hexdigest()})
        return view_record(con,con.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone())


@router.get('/records/{record_id}/qa')
def record_qa(record_id: str, user=Depends(auth)):
    with readonly() as con:
        record=view_record(con,get_owned(con,record_id,user))
    return {'record_id':record_id,'version':record['version'],
            **audit_quality(record['test_type'],record)}


@router.post('/records/{record_id}/submit')
def submit(record_id:str,body:VersionAction,user=Depends(auth)):
    with transaction() as con:
        row=get_owned(con,record_id,user)
        if row['creator']!=user['id']:raise HTTPException(403,'Only original author can submit')
        if row['current_version']!=body.expected_version:raise HTTPException(409,'Stale version')
        if row['status']!='draft':raise HTTPException(409,'Only drafts can be submitted')
        content=json.loads(con.execute('SELECT body FROM revisions WHERE record_id=? AND version=?',
                                      (record_id,row['current_version'])).fetchone()['body'])
        if not content.get('spec_reference') or not content.get('evidence_reference'):
            raise HTTPException(422,'Specification and original evidence references required')
        qa=audit_quality(content['test_type'],content)
        if not qa['can_submit']:
            raise HTTPException(422,{'message':'Fix data-quality blockers before submission',
                                     'qa':qa})
        con.execute("UPDATE records SET status='submitted' WHERE id=?",(record_id,))
        append_audit(con,user['username'],'SUBMITTED',record_id,{'version':row['current_version']})
        return view_record(con,con.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone())


@router.post('/records/{record_id}/review')
def review(record_id:str,body:ReviewAction,user=Depends(engine)):
    with transaction() as con:
        row=get_owned(con,record_id,user)
        if row['creator']==user['id']:raise HTTPException(403,'Cannot review your own record')
        if row['current_version']!=body.expected_version:raise HTTPException(409,'Stale version')
        if row['status']!='submitted':raise HTTPException(409,'Only submitted records can be reviewed')
        con.execute('UPDATE records SET status=?,reviewer=?,review_note=?,reviewed_at=? WHERE id=?',
                    (body.decision,user['id'],body.note,utc(),record_id))
        append_audit(con,user['username'],'REVIEW_'+body.decision.upper(),record_id,
                     {'version':row['current_version'],'note':body.note})
        return view_record(con,con.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone())


@router.get('/records/{record_id}/history')
def history(record_id:str,user=Depends(auth)):
    with readonly() as con:
        get_owned(con,record_id,user)
        rows=con.execute('''SELECT v.version,u.username AS actor,v.time,v.body FROM revisions v
                            JOIN users u ON u.id=v.actor WHERE record_id=? ORDER BY version''',(record_id,)).fetchall()
        return {'history':[{'version':r['version'],'actor':r['actor'],'at':r['time'],'body':json.loads(r['body'])} for r in rows]}


@router.get('/audit/check')
def audit_check(user=Depends(engine)):
    with readonly() as con:return verify_audit(con)


@router.get('/audit/events')
def audit_events(user=Depends(engine)):
    with readonly() as con:
        return {'events':[dict(row) for row in con.execute('SELECT seq,at,actor,event,record_id,prev_hash,event_hash FROM audit ORDER BY seq DESC LIMIT 100')]}


@router.get('/export/bridge-candidates')
def bridge_candidates(user=Depends(engine)):
    """Engineer-only read-only candidate handoff. NOT an ElmTree integration.

    Emits ONLY locally reviewed, independently reviewed, explicitly authorized
    records. An operator must still select a tested and approved exchange route.
    """
    with readonly() as con:
        integrity=verify_audit(con)
        if not integrity['ok']:
            raise HTTPException(409,'Audit integrity check failed; bridge export blocked')
        rows=con.execute("SELECT * FROM records WHERE status='reviewed' ORDER BY created_at,id LIMIT 10000").fetchall()
        records=[view_record(con,r) for r in rows]
    from bridge.core import eligible_records
    allowed,withheld=eligible_records(records,demo=False)
    return {'schema':'cmt-bridge-candidates-v1',
            'label':'REVIEW-ONLY / NOT A CERTIFIED REPORT / NO ELMTree WRITE CONNECTION',
            'vendor_import_verified':False,'source':'authorized_only',
            'records':allowed, 'withheld_count':len(withheld),
            'audit_verified':True}


@router.get('/export/neutral.csv')
def export_neutral_csv(user=Depends(engine)):
    # Spreadsheet-safe, vendor-neutral handoff; NO implied ElmTree/GET integration.
    import csv, io
    from fastapi.responses import Response as CsvResponse
    with readonly() as con:
        rows=con.execute('SELECT * FROM records ORDER BY created_at,id').fetchall()
        records=[view_record(con,r) for r in rows]
        integrity=verify_audit(con)
    if not integrity['ok']:
        raise HTTPException(409,'Audit integrity check failed; export blocked')
    def spreadsheet_safe(x):
        value=str(x if x is not None else '')
        # Reject CSV formula interpretation including leading whitespace or control characters.
        if value.lstrip(' \t\r\n').startswith(('=','+','-','@')):
            return "'"+value
        return value
    buffer=io.StringIO(newline='')
    writer=csv.writer(buffer)
    writer.writerow(['NOTICE_UNCERTIFIED','record_id','version','status','test_type','project_code',
                     'location','spec_reference','evidence_reference','source','creator',
                     'reviewer','review_note','measurements_json'])
    for r in records:
        fields=['NOT A CERTIFIED ENGINEERING REPORT',r['id'],r['version'],r['status'],r['test_type'],
                r['project_code'],r['location'],r['spec_reference'],r['evidence_reference'],
                r['source'],r['creator'],r['reviewer'],r['review_note'],canonical(r['measurements'])]
        writer.writerow([spreadsheet_safe(x) for x in fields])
    return CsvResponse(content=buffer.getvalue(),media_type='text/csv; charset=utf-8',
                       headers={'Content-Disposition':'attachment; filename="CMT_vendor_neutral_UNCERTIFIED.csv"',
                                'Cache-Control':'no-store',
                                'X-Content-Type-Options':'nosniff'})


@router.get('/export')
def export(user=Depends(engine)):
    with readonly() as con:
        rows=con.execute('SELECT * FROM records ORDER BY created_at,id').fetchall()
        integrity=verify_audit(con)
        if not integrity['ok']:
            raise HTTPException(409,'Audit integrity check failed; export blocked')
        result={'exported_at':utc(),'label':'NOT AN ENGINEERING CERTIFICATION',
                'records':[view_record(con,r) for r in rows], 'audit':integrity}
    return result


@router.get('/records/{record_id}/report.json')
def record_report(record_id: str, user=Depends(auth)):
    """Portable unsigned engineering REVIEW WORKSHEET with checksum and provenance.

    NOT a signed report, official acceptance or immutable external evidence.
    """
    with readonly() as con:
        row=get_owned(con,record_id,user)
        integrity=verify_audit(con)
        if not integrity['ok']:
            raise HTTPException(409,'Audit integrity check failed; report blocked')
        record=view_record(con,row)
        revisions=con.execute('SELECT v.version,u.username AS actor,v.time,v.body FROM revisions v JOIN users u ON v.actor=u.id WHERE v.record_id=? ORDER BY v.version',(record_id,)).fetchall()
        history=[{'version':r['version'],'actor':r['actor'],'at':r['time'],
                  'source_sha256':hashlib.sha256(r['body'].encode()).hexdigest(),
                  'body':json.loads(r['body'])} for r in revisions]
        events=[dict(r) for r in con.execute('SELECT seq,at,actor,event,record_id,details,prev_hash,event_hash FROM audit WHERE record_id=? ORDER BY seq',(record_id,)).fetchall()]
    qa=audit_quality(record['test_type'],record)
    base={'schema':'cmt-review-worksheet-v1', 'generated_at':utc(),
          'label':'UNSIGNED ENGINEERING REVIEW WORKSHEET — NOT CERTIFIED / NOT ACCEPTANCE',
          'record':record,'qa':qa,'revisions':history,'audit_events':events,
          'audit_head_hash':integrity['head_hash'],
          'limits':['No method compliance or PE signature established',
                    'Source evidence is referenced but not independently authenticated',
                    'Audit hashes are not externally notarized',
                    'Reviewed status is not a material acceptance decision']}
    checksum=hashlib.sha256(canonical(base).encode('utf-8')).hexdigest()
    return {'payload':base,'payload_sha256':checksum,
            'checksum_note':'Checksum detects changes to these exported bytes; it is not a digital signature.'}


def main():
    cli=argparse.ArgumentParser(description='Create local CMT pilot accounts; NO default passwords')
    cli.add_argument('command',choices=['create-user','verify-audit'])
    cli.add_argument('--username');cli.add_argument('--role',choices=ROLE)
    args=cli.parse_args()
    if args.command=='verify-audit':
        with readonly() as con:print(json.dumps(verify_audit(con),indent=2))
    else:
        if not args.username or not args.role:cli.error('--username and --role are required')
        password=getpass.getpass('New password (12+ chars): ')
        confirm=getpass.getpass('Repeat password: ')
        if password != confirm:cli.error('Passwords do not match')
        create_user(args.username,args.role,password)
        print('User created:',args.username,args.role)


if __name__=='__main__':main()
