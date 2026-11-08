"""System-wide identities; independent of personnel/document records."""
from datetime import datetime, UTC
from sqlalchemy import String, Integer, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index, JSON, event, text, inspect
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base
from app.models.staff import SystemTimestamps


class User(SystemTimestamps, Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey('persons.person_id',name='user_person_fk'))
    username: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint('person_id',name='user_person_unique'),
        CheckConstraint("role IN ('master','admin','user')",name='users_role_allowed'),
        CheckConstraint("role != 'master' OR (is_active AND password_hash LIKE 'scrypt$%')",name='master_personal_active'),
        Index('one_master', 'role', unique=True, sqlite_where=text("role='master'"),postgresql_where=text("role='master'")),
    )


class UserSession(Base):
    __tablename__ = 'user_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    public_id: Mapped[str | None] = mapped_column(String(32),unique=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_activity: Mapped[datetime | None] = mapped_column(DateTime)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__=(CheckConstraint("mfa_verified_at IS NULL OR (public_id IS NOT NULL AND created_at IS NOT NULL AND last_activity IS NOT NULL AND last_activity>=created_at AND mfa_verified_at>=created_at AND mfa_verified_at<expires_at AND expires_at>created_at)",name='session_mfa_times'),)


class AccountAudit(Base):
    __tablename__='account_audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime,default=lambda:datetime.now(UTC))
    operation: Mapped[str] = mapped_column(String(30))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(2000))
    __table_args__=(CheckConstraint("operation IN ('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master','mfa_enroll','factor_add','factor_remove','backup_use','backup_generate','mfa_recover','mfa_reauth')",name='account_audit_operation'),)


@event.listens_for(Base.metadata,'after_create')
def account_guards(metadata,connection,**kwargs):
    if connection.dialect.name!='sqlite':return
    tables=set(inspect(connection).get_table_names())
    if 'account_audit' in tables:
        for action in ('UPDATE','DELETE'):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS account_audit_no_{action.lower()} BEFORE {action} ON account_audit BEGIN SELECT RAISE(ABORT,'account audit is append only'); END")
    if 'users' not in tables:return
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS users_no_delete BEFORE DELETE ON users BEGIN SELECT RAISE(ABORT,'accounts cannot be deleted'); END")
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS users_no_insert_master BEFORE INSERT ON users WHEN NEW.role='master' BEGIN SELECT RAISE(ABORT,'promote an existing administrator'); END")
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS users_policy_update BEFORE UPDATE ON users BEGIN
      SELECT CASE WHEN NEW.id!=OLD.id THEN RAISE(ABORT,'account ID is immutable') END;
      SELECT CASE WHEN NEW.username!=OLD.username THEN RAISE(ABORT,'username is immutable') END;
      SELECT CASE WHEN OLD.role='master' AND (NEW.role!='master' OR NOT NEW.is_active) THEN RAISE(ABORT,'master is protected') END;
      SELECT CASE WHEN NEW.role='master' AND OLD.role!='master' AND (OLD.role!='admin' OR NOT OLD.is_active OR OLD.password_hash NOT LIKE 'scrypt$%') THEN RAISE(ABORT,'promote a personal active admin') END;
      SELECT CASE WHEN OLD.role='admin' AND OLD.is_active AND OLD.password_hash LIKE 'scrypt$%'
        AND NEW.role!='master' AND NOT (NEW.role='admin' AND NEW.is_active AND NEW.password_hash LIKE 'scrypt$%')
        AND NOT EXISTS (SELECT 1 FROM users WHERE id!=OLD.id AND role='admin' AND is_active AND password_hash LIKE 'scrypt$%')
        THEN RAISE(ABORT,'last active admin is protected') END;
    END""")
