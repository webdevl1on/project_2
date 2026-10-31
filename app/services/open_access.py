"""A real shared audit actor for the temporary unrestricted application mode."""
import secrets
from app.database.transactions import service_transaction
from app.models.accounts import User
from app.repositories.account_repository import AccountRepository as Repo

USERNAME='project2-open-access'
DISPLAY_NAME='Спільний автор — авторизацію вимкнено'
PREFIX='open-access-only$'


def identity(db):
    user=Repo.by_name(db,USERNAME)
    if user is None:
        with service_transaction(db,immediate=True):
            user=Repo.by_name(db,USERNAME)
            if user is None:
                user=Repo.add(db,User(username=USERNAME,display_name=DISPLAY_NAME,role='admin',is_active=True,password_hash=PREFIX+secrets.token_hex(32)))
                db.flush()
            validate(user)
            key=user.id
        return Repo.user(db,key)
    return validate(user)


def validate(user):
    if user.role!='admin' or not user.is_active or user.display_name!=DISPLAY_NAME or not user.password_hash.startswith(PREFIX):
        raise ValueError('Службовий обліковий запис вільного доступу змінено. Наявні записи автоматично не перезаписуються.')
    return user
