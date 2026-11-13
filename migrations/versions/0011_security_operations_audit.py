"""Append-only audit gaps; no invented past operations or credentials."""
from alembic import op
import sqlalchemy as sa
revision='0011_security_operations_audit'
down_revision='0010_organization_hierarchy'
branch_labels=depends_on=None

def upgrade():
    op.alter_column('account_audit','user_id',nullable=True)
    op.drop_constraint('account_audit_operation','account_audit',type_='check')
    op.create_check_constraint('account_audit_operation','account_audit',"operation IN ('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master','mfa_enroll','factor_add','factor_remove','backup_use','backup_generate','mfa_recover','mfa_reauth','login','login_failed','mfa_failed','logout')")
    op.create_check_constraint('account_audit_target','account_audit',"user_id IS NOT NULL OR operation='login_failed'")
    op.create_table('subject_audit',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),sa.Column('actor_user_id',sa.Integer(),sa.ForeignKey('users.id')),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('persons.person_id')),sa.Column('object_type',sa.String(80),nullable=False),
        sa.Column('object_id',sa.Integer(),nullable=False),sa.Column('category',sa.String(40),nullable=False),
        sa.Column('operation',sa.String(30),nullable=False),sa.Column('before',sa.JSON(),nullable=False),
        sa.Column('after',sa.JSON(),nullable=False),sa.Column('reason',sa.String(2000)),
        sa.CheckConstraint("operation IN ('create','edit','delete')",name='subject_audit_operation'))
    op.create_index('subject_audit_person_time','subject_audit',['person_id','occurred_at'])
    op.execute("""CREATE FUNCTION project2_subject_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'subject audit is append only'; END $$;
      CREATE TRIGGER subject_audit_no_update BEFORE UPDATE ON subject_audit FOR EACH ROW EXECUTE FUNCTION project2_subject_audit_immutable();
      CREATE TRIGGER subject_audit_no_delete BEFORE DELETE ON subject_audit FOR EACH ROW EXECUTE FUNCTION project2_subject_audit_immutable();""")

def downgrade():
    raise RuntimeError('Audit history must be preserved; restore a verified copy in isolation.')
