"""One Master, protected active admins and append-only account management audit."""
from alembic import op
import sqlalchemy as sa
revision='0006_account_management'
down_revision='0005_assignment_history'
branch_labels=depends_on=None


def upgrade():
    op.drop_constraint('users_role_check','users',type_='check')
    op.create_check_constraint('users_role_allowed','users',"role IN ('master','admin','editor','viewer')")
    op.create_check_constraint('master_personal_active','users',"role!='master' OR (is_active AND password_hash LIKE 'scrypt$%')")
    op.create_index('one_master','users',['role'],unique=True,postgresql_where=sa.text("role='master'"))
    op.create_table('account_audit',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('actor_user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.Column('operation',sa.String(30),nullable=False),
        sa.Column('before',sa.JSON(),nullable=False),sa.Column('after',sa.JSON(),nullable=False),
        sa.Column('reason',sa.String(2000),nullable=True),
        sa.CheckConstraint("operation IN ('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master')",name='account_audit_operation'))
    op.create_index('ix_account_audit_user_id','account_audit',['user_id'])
    op.execute("""CREATE FUNCTION project2_account_audit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'account audit is append only' USING ERRCODE='23514'; END; $$""")
    for action in ('UPDATE','DELETE'):
        op.execute(f'CREATE TRIGGER account_audit_no_{action.lower()} BEFORE {action} ON account_audit FOR EACH ROW EXECUTE FUNCTION project2_account_audit_guard()')
    op.execute("""CREATE FUNCTION project2_users_policy() RETURNS trigger LANGUAGE plpgsql VOLATILE AS $$
      BEGIN
        PERFORM pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_accounts'));
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'accounts cannot be deleted' USING ERRCODE='23514'; END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.role='master' THEN RAISE EXCEPTION 'promote an existing administrator' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END IF;
        IF NEW.id IS DISTINCT FROM OLD.id THEN RAISE EXCEPTION 'account ID is immutable' USING ERRCODE='23514'; END IF;
        IF NEW.username IS DISTINCT FROM OLD.username THEN RAISE EXCEPTION 'username is immutable' USING ERRCODE='23514'; END IF;
        IF OLD.role='master' AND (NEW.role!='master' OR NOT NEW.is_active) THEN RAISE EXCEPTION 'master is protected' USING ERRCODE='23514'; END IF;
        IF NEW.role='master' AND OLD.role!='master' AND (OLD.role!='admin' OR NOT OLD.is_active OR OLD.password_hash NOT LIKE 'scrypt$%')
          THEN RAISE EXCEPTION 'promote a personal active admin' USING ERRCODE='23514'; END IF;
        IF OLD.role='admin' AND OLD.is_active AND OLD.password_hash LIKE 'scrypt$%'
           AND NEW.role!='master' AND NOT (NEW.role='admin' AND NEW.is_active AND NEW.password_hash LIKE 'scrypt$%')
           AND NOT EXISTS (SELECT 1 FROM users WHERE id!=OLD.id AND role='admin' AND is_active AND password_hash LIKE 'scrypt$%')
          THEN RAISE EXCEPTION 'last active admin is protected' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END; $$""")
    for action,name in [('INSERT','users_no_insert_master'),('UPDATE','users_policy_update'),('DELETE','users_no_delete')]:
        op.execute(f'CREATE TRIGGER {name} BEFORE {action} ON users FOR EACH ROW EXECUTE FUNCTION project2_users_policy()')


def downgrade():
    raise RuntimeError('Downgrade would lose account audit and Master protection. Restore a verified backup to a separate database.')
