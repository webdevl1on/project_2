"""Explicit MFA key initialization/rotation; never generates a transient key."""
import argparse

def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--initialize',action='store_true');group.add_argument('--rotate',action='store_true');args=parser.parse_args()
    from app.database.db import engine
    from app.database.schema_check import require_current_schema
    from sqlalchemy.orm import Session
    from app.models.mfa import MfaKeyState
    from app.security.mfa_config import MARKER,encrypt,decrypt,require_keys
    from app.repositories.mfa_repository import MfaRepository
    from app.services.accounts import account_write
    require_current_schema(engine)
    with Session(engine) as db,account_write(db):
        if args.initialize:
            if db.get(MfaKeyState,1):require_keys(db)
            else:db.add(MfaKeyState(id=1,ciphertext=encrypt(MARKER)))
        else:
            require_keys(db)
            for row in MfaRepository.encrypted_rows(db):row.ciphertext=encrypt(decrypt(row.ciphertext))
    print('Ключ MFA перевірено; операцію завершено.')
if __name__=='__main__':main()
