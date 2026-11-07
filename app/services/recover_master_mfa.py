"""Local operator procedure; no HTTP equivalent and no temporary login bypass."""
import argparse
from getpass import getpass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--user-id',type=int,required=True);args=parser.parse_args()
    import os
    if os.name=='nt':
        import ctypes
        allowed=bool(ctypes.windll.shell32.IsUserAnAdmin())
    else:allowed=os.geteuid()==0
    if not allowed:parser.error('Потрібен локальний адміністратор ОС (Administrator/root).')
    from app.database.db import engine
    from app.database.schema_check import require_current_schema
    from sqlalchemy.orm import Session
    from app.models import User
    from app.services import accounts,mfa
    require_current_schema(engine)
    with Session(engine) as db:
        user=db.get(User,args.user_id)
        password=getpass('Поточний пароль Master: ')
        if not user or user.role!='master' or not accounts.verify_password(password,user.password_hash):parser.error('Master та пароль не підтверджені.')
        reason=input('Як перевірено особу власника і чому потрібне відновлення: ').strip()
        if not reason or input(f'Підтвердження: RESET MFA MASTER {user.id}: ').strip()!=f'RESET MFA MASTER {user.id}':parser.error('Скасовано.')
        mfa.recover(db,None,user.id,reason,password=password)
    print('Фактори й сесії відкликано. Наступний вхід вимагає пароля та нового налаштування MFA.')
if __name__=='__main__':main()
