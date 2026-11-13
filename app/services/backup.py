"""Security 1.5 server CLI. Run from the repository root; never restores dev/prod."""
import argparse,base64,getpass,json,os,sys
from pathlib import Path
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.services.backups.crypto import private_file,canonical


def new_key(path):
    path=Path(path).resolve();repo=Path(__file__).resolve().parents[2]
    if path==repo or repo in path.parents:raise ValueError('BACKUP_KEY_MUST_BE_OUTSIDE_REPOSITORY')
    with private_file(path) as out:out.write(canonical({'current':'key1','keys':{'key1':base64.b64encode(os.urandom(32)).decode()}}))


def master(db):
    from app.services import accounts
    from app.services.backups.commands import authorize
    token=getpass.getpass('Чинна персональна сесія Master після свіжої MFA: ')
    user,session=accounts.authenticate(db,token);db.info['access_session_hash']=session.token_hash
    actor=authorize(db,user.id,critical=True)
    if actor.role!='master':raise PermissionError('BACKUP_MASTER_REQUIRED')
    return actor.id


@contextmanager
def recovered_configuration(values):
    previous={k:os.environ.get(k) for k in values}
    os.environ.update(values)
    try:yield
    finally:
        for k,v in previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


def recovered_master(engine,values):
    from app.services import accounts,mfa
    from app.models import User
    username=input('Логін Master у відновленій копії: ').strip();password=getpass.getpass('Пароль Master: ')
    with recovered_configuration(values),Session(engine) as db:
        token,_=accounts.login(db,username,password)
        user,state=mfa.pending(db,token)
        if not user or user.role!='master':raise PermissionError('RESTORE_MASTER_REQUIRED')
        method=input('Другий фактор (totp або backup): ').strip()
        if method not in ('totp','backup'):raise ValueError('RESTORE_FACTOR_REQUIRED')
        mfa.prove(db,token,method,getpass.getpass('Одноразовий код: '))
        result=mfa.finish(db,token);actor=accounts.authenticate(db,result['token'])[0]
        return actor.id


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    gen=sub.add_parser('keygen');gen.add_argument('--file',required=True)
    approve=sub.add_parser('approve-drill');approve.add_argument('--target-url-env',default='PROJECT2_BACKUP_DRILL_DATABASE_URL');approve.add_argument('--reason',required=True);approve.add_argument('--days',type=int,default=30);approve.add_argument('--until-revoked',action='store_true');approve.add_argument('--confirm',action='store_true')
    sub.add_parser('drill');sub.add_parser('revoke-drill')
    emergency=sub.add_parser('approve-emergency');emergency.add_argument('--reason',required=True);emergency.add_argument('--days',type=int,default=30);emergency.add_argument('--until-revoked',action='store_true');emergency.add_argument('--confirm',action='store_true')
    sub.add_parser('revoke-emergency')
    for name in ('status','run-once','create','verify'):
        p=sub.add_parser(name)
        if name=='verify':p.add_argument('--id',required=True);p.add_argument('--external',action='store_true')
    for name in ('restore-plan','restore-apply'):
        p=sub.add_parser(name);p.add_argument('--target-url-env',default='PROJECT2_RESTORE_DATABASE_URL');p.add_argument('--offline-master',action='store_true')
        if name=='restore-plan':p.add_argument('--id',required=True);p.add_argument('--reason',required=True);p.add_argument('--external',action='store_true')
        else:p.add_argument('--plan',required=True);p.add_argument('--output',required=True);p.add_argument('--confirm',action='store_true');p.add_argument('--write-config')
    args=parser.parse_args(argv)
    try:
        if args.command=='keygen':new_key(args.file);print('Новий ключ записано в захищений файл.');return 0
        from app.database.db import engine,settings
        from app.services.backups.config import BackupConfig
        from app.services.backups.engine import BackupEngine
        from app.services.backups import restore
        from app.database.maintenance import database_lease
        service=BackupEngine(engine,settings,BackupConfig.load(settings))
        if args.command=='run-once':
            try:okay=service.run_once()
            except Exception:print('BACKUP_WORKER_FAILED',file=sys.stderr);return 1
            return 0 if okay else 1
        if args.command=='status':
            with Session(engine) as db:master(db)
            print(json.dumps(service.store.status(),ensure_ascii=False));return 0
        offline=getattr(args,'offline_master',False)
        if offline:
            import ctypes
            privileged=bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name=='nt' else os.geteuid()==0
            if not privileged:raise PermissionError('RESTORE_LOCAL_ADMIN_REQUIRED')
            actor=None
        else:
            with Session(engine) as db:actor=master(db)
        service.store.initialize()
        with (database_lease(service.config.root/'worker') if offline else service.operation_lock()):
            if args.command=='approve-drill':
                from app.services.backups.drills import approve
                approve(service,actor,args.target_url_env,args.reason,0 if args.until_revoked else args.days,args.confirm);result={'approved':True}
            elif args.command=='approve-emergency':
                from app.services.backups.emergency import approve
                approve(service,actor,args.reason,0 if args.until_revoked else args.days,args.confirm);result={'approved':True}
            elif args.command=='revoke-emergency':
                permit=service.ring.read(service.config.root/'emergency-permit.json');permit['active']=False;service.ring.save(service.config.root/'emergency-permit.json',permit)
                service.store.event('emergency_revoke','SUCCESS',actor=actor);result={'revoked':True}
            elif args.command=='revoke-drill':
                permit=service.ring.read(service.config.root/'drill-permit.json');permit['active']=False;service.ring.save(service.config.root/'drill-permit.json',permit)
                service.store.event('drill_revoke','SUCCESS',actor=actor);result={'revoked':True}
            elif args.command=='drill':
                from app.services.backups.drills import maybe_run
                result=maybe_run(service,force=True,actor=actor)
                if result is None:raise ValueError('BACKUP_DRILL_APPROVAL_REQUIRED')
            elif args.command=='create':
                result=service.create(actor=actor)
                from app.services.backups.drills import maybe_run
                maybe_run(service,force=True,identity=result['id'],required=True,actor=actor)
            elif args.command=='verify':result=service.verify(args.id,actor=actor,external=args.external)
            elif args.command=='restore-plan':result=restore.plan(service,args.id,os.environ[args.target_url_env],actor=actor,reason=args.reason,external=args.external)
            else:
                result=restore.apply(service,args.plan,os.environ[args.target_url_env],args.output,actor=actor,confirmed=args.confirm,authorize=recovered_master if offline else None)
                if args.write_config:
                    from app.services.backups.bundle import open_bundle
                    plan=service.ring.read(service.config.root/'plans'/(args.plan+'.json'));archive,capsule=service.locations(plan['backup_id'],plan['external'])
                    destination=Path(args.write_config).resolve();repo=Path(__file__).resolve().parents[2]
                    if destination==repo or repo in destination.parents:raise ValueError('RESTORE_CONFIG_MUST_BE_OUTSIDE_REPOSITORY')
                    with open_bundle(service.config,service.ring,service.secret_ring,archive,capsule) as (_,values,__):
                        with private_file(destination) as out:out.write(canonical(values))
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ValueError,PermissionError,OSError,KeyError,TypeError,SQLAlchemyError):
        # Never interpolate database/subprocess/crypto exceptions into console or journals.
        print('BACKUP_OPERATION_REFUSED: перевірте конфігурацію, права та захищений журнал.',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
