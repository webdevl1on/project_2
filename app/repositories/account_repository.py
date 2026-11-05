"""System account persistence; no transaction ownership."""
from datetime import datetime,UTC
from sqlalchemy import select, func, delete, text
from app.models.accounts import User, UserSession, AccountAudit


class AccountRepository:
    @staticmethod
    def user(db, key): return db.get(User, key)

    @staticmethod
    def by_name(db, name): return db.scalar(select(User).where(User.username == name))

    @staticmethod
    def count(db): return db.scalar(select(func.count()).select_from(User))

    @staticmethod
    def bootstrap_accounts(db): return list(db.scalars(select(User)))

    @staticmethod
    def session(db, digest): return db.get(UserSession, digest)

    @staticmethod
    def add(db, value): db.add(value); return value

    @staticmethod
    def delete(db, value): db.delete(value)


    @staticmethod
    def lock_management(db):
        if db.get_bind().dialect.name=='postgresql':
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_accounts'))"))

    @staticmethod
    def locked_user(db,key):
        return db.get(User,key,populate_existing=True,with_for_update=db.get_bind().dialect.name=='postgresql')

    @staticmethod
    def active_admins(db):
        return db.scalar(select(func.count()).select_from(User).where(User.role=='admin',User.is_active.is_(True),User.password_hash.like('scrypt$%')))

    @staticmethod
    def master(db):return db.scalar(select(User).where(User.role=='master'))

    @staticmethod
    def users(db):return list(db.scalars(select(User).order_by((User.role=='master').desc(),User.id)))

    @staticmethod
    def revoke_sessions(db,key):
        return db.execute(delete(UserSession).where(UserSession.user_id==key)).rowcount

    @staticmethod
    def session_count(db,key):
        return db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id==key,UserSession.expires_at>datetime.now(UTC)))

    @staticmethod
    def audit(db,key=None,offset=0):
        from sqlalchemy.orm import aliased
        actor=aliased(User)
        query=select(AccountAudit,actor.display_name).outerjoin(actor,actor.id==AccountAudit.actor_user_id)
        if key is not None:query=query.where(AccountAudit.user_id==key)
        return list(db.execute(query.order_by(AccountAudit.id.desc()).offset(offset).limit(50)))
