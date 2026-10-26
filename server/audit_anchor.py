"""Optional externally stored Ed25519 audit checkpoints for a LOCAL CMT pilot.

Not a licensed engineer signature. Keep private key separate from the DB and off
shared computers, under an encrypted passphrase; distribute the public key
independently and archive checkpoints in separate immutable storage.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from .pilot import canonical, readonly, verify_audit


def create_keypair(private: Path, public: Path, passphrase: str):
    private=private.resolve();public=public.resolve()
    if private == public: raise ValueError('Private/public paths must differ')
    if len(passphrase) < 16: raise ValueError('Key passphrase must be at least 16 characters')
    if private.exists() or public.exists():raise FileExistsError('Refusing to overwrite existing keys')
    private.parent.mkdir(parents=True,exist_ok=True); public.parent.mkdir(parents=True,exist_ok=True)
    pair=Ed25519PrivateKey.generate()
    private_bytes=pair.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                     serialization.BestAvailableEncryption(passphrase.encode()))
    public_bytes=pair.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    fd=os.open(private,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as out:out.write(private_bytes)
    except BaseException:
        private.unlink(missing_ok=True)
        raise
    try:
        fd_pub=os.open(public,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
        with os.fdopen(fd_pub,'wb') as out:out.write(public_bytes)
    except BaseException:
        private.unlink(missing_ok=True)
        raise
    return {'key_fingerprint_sha256':hashlib.sha256(public_bytes).hexdigest(),
            'private_key_encrypted':True,'public_key':str(public)}


def make_checkpoint(private:Path, passphrase:str, output:Path):
    if output.exists():raise FileExistsError('Refusing to overwrite an audit checkpoint')
    if len(passphrase)<16:raise ValueError('Passphrase is too short')
    with readonly() as con:
        verdict=verify_audit(con)
    if not verdict['ok']:
        raise ValueError('Cannot sign inconsistent or tampered audit database')
    raw=private.read_bytes()
    key=serialization.load_pem_private_key(raw,password=passphrase.encode())
    if not isinstance(key,Ed25519PrivateKey):raise ValueError('An Ed25519 key is required')
    pub=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    envelope={'schema':'cmt-local-ed25519-checkpoint-v1',
              'created_utc':datetime.now(timezone.utc).isoformat(),
              'audit_head_sha256':verdict['head_hash'],
              'event_count':verdict['events_checked'],
              'record_count':verdict['records_checked'],
              'public_key_fingerprint_sha256':hashlib.sha256(pub).hexdigest(),
              'legal_status':'Independent technical checkpoint; NOT a professional engineer signature'}
    signature=key.sign(canonical(envelope).encode('utf-8'))
    data={'payload':envelope,'signature_ed25519_b64':base64.b64encode(signature).decode('ascii')}
    output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return data


def verify_checkpoint(public:Path, checkpoint:Path, *, check_current_db:bool=True):
    content=json.loads(checkpoint.read_text(encoding='utf-8'))
    payload=content['payload']
    if payload.get('schema')!='cmt-local-ed25519-checkpoint-v1':
        raise ValueError('Unknown checkpoint schema')
    pub_pem=public.read_bytes()
    if hashlib.sha256(pub_pem).hexdigest()!=payload['public_key_fingerprint_sha256']:
        raise ValueError('Checkpoint was made with a different public key')
    pub=serialization.load_pem_public_key(pub_pem)
    if not isinstance(pub,Ed25519PublicKey):raise ValueError('Expected an Ed25519 public key')
    try:
        pub.verify(base64.b64decode(content['signature_ed25519_b64'],validate=True),canonical(payload).encode('utf-8'))
    except (InvalidSignature,ValueError) as exc:
        raise ValueError('Checkpoint signature invalid') from exc
    result={'signature_valid':True,'db_matches_signed_checkpoint':None,
            'warning':'Technical tamper-evidence only. Not a PE engineering signature.'}
    if check_current_db:
        with readonly() as con:report=verify_audit(con)
        result['db_matches_signed_checkpoint']=(report['ok'] and
           report['head_hash']==payload['audit_head_sha256'] and
           report['events_checked']==payload['event_count'] and
           report['records_checked']==payload['record_count'])
    return result


def main():
    import getpass
    cli=argparse.ArgumentParser(description='CMT local signed audit checkpoints (not PE signatures)')
    group=cli.add_subparsers(dest='command',required=True)
    mk=group.add_parser('create-key');mk.add_argument('private',type=Path);mk.add_argument('public',type=Path)
    sign=group.add_parser('sign');sign.add_argument('private',type=Path);sign.add_argument('checkpoint',type=Path)
    verify=group.add_parser('verify');verify.add_argument('public',type=Path);verify.add_argument('checkpoint',type=Path)
    a=cli.parse_args()
    if a.command=='create-key':
        password=getpass.getpass('Choose encrypted signing-key passphrase (16+ chars): ')
        again=getpass.getpass('Confirm passphrase: ')
        if password!=again:cli.error('Passphrases do not match')
        result=create_keypair(a.private,a.public,password)
    elif a.command=='sign':
        result=make_checkpoint(a.private,getpass.getpass('Encrypted signing key passphrase: '),a.checkpoint)
    else:
        result=verify_checkpoint(a.public,a.checkpoint)
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
