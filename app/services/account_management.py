"""Safe account presentation; password hashes and session tokens never leave here."""
from datetime import datetime,UTC
from app.account_policy import ROLES,OPERATIONS,personal
from app.repositories.account_repository import AccountRepository as Repo
from app.services import accounts
from app.utils.date_utils import format_system_timestamp


def public_user(user):
    locked=bool(user.locked_until and user.locked_until.replace(tzinfo=UTC)>datetime.now(UTC))
    return {**accounts.account_snapshot(user),'role_label':ROLES[user.role],
            'personal':personal(user),'status':'Вимкнений адміністратором' if not user.is_active else 'Тимчасово заблокований вхід' if locked else 'Активний',
            'temporary_locked':locked,'locked_until':format_system_timestamp(user.locked_until) if locked else None,
            'created_at':format_system_timestamp(user.created_at)}


def listing(db,actor_id,q=''):
    actor=accounts.authorize(db,actor_id,('master','admin'))
    query=q.strip().casefold()
    users=[public_user(user) for user in Repo.users(db) if not query or any(query in str(value).casefold() for value in (user.id,user.username,user.display_name))]
    return {'users':users,'q':q,'needs_admin':actor.role=='master' and Repo.active_admins(db)==0}


def detail(db,actor_id,key):
    actor=accounts.authorize(db,actor_id,('master','admin'))
    user=Repo.user(db,key)
    if user is None:raise ValueError('Обліковий запис не існує.')
    return {'account':public_user(user),'can_manage':personal(user) and (user.role=='user' or actor.role=='master'),
            'own_account':actor_id==key,'active_sessions':Repo.session_count(db,key)}


def audit_page(db,actor_id,key=None,page=1):
    accounts.authorize(db,actor_id,('master','admin'))
    page=max(1,page)
    fields={'id':'ID','username':'Логін','display_name':'Відображуване ім’я','role':'Роль','is_active':'Активний','revision':'Версія запису',
            'factor_kind':'Вид фактора','factor_id':'ID фактора','renamed':'Перейменовано','password_changed':'Пароль змінено','revoked_sessions':'Відкликано сесій'}
    def value(field,item):
        if field=='role':return ROLES.get(item,item)
        if type(item) is bool:return 'Так' if item else 'Ні'
        return '—' if item is None else item
    entries=[]
    for row,actor in Repo.audit(db,key,(page-1)*50):
        changes=[(label,value(field,row.before.get(field)),value(field,row.after.get(field))) for field,label in fields.items() if row.before.get(field)!=row.after.get(field)]
        entries.append({'id':row.id,'user_id':row.user_id,'actor_user_id':row.actor_user_id,'actor':actor or 'Системна CLI-операція',
                        'occurred_at':format_system_timestamp(row.occurred_at),'operation':OPERATIONS[row.operation],'changes':changes,'reason':row.reason})
    return {'entries':entries,'page':page,'user_id':key}
