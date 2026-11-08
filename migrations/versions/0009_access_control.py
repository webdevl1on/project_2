"""Security 1.4: deny-first access sources, subject link and safe ordinary-role transition."""
from pathlib import Path
from alembic import op
import sqlalchemy as sa
revision='0009_access_control'
down_revision='0008_organization'
branch_labels=depends_on=None

def upgrade():
    op.add_column('users',sa.Column('person_id',sa.Integer(),nullable=True))
    op.create_foreign_key('user_person_fk','users','persons',['person_id'],['person_id'])
    op.create_unique_constraint('user_person_unique','users',['person_id'])
    root=Path(__file__).resolve().parents[1]/'sql'
    op.execute((root/'access_schema.sql').read_text())
    # Preserve identity, hashes, factors and sessions; no inferred data grants.
    op.execute("INSERT INTO access_audit(actor_user_id,target_user_id,occurred_at,operation,before,after,reason) SELECT NULL,id,CURRENT_TIMESTAMP,'role_migration',json_build_object('role',role),json_build_object('role','user'),'Security 1.4: перехід звичайної ролі без автоматичного надання предметних прав' FROM users WHERE role IN ('editor','viewer')")
    op.drop_constraint('users_role_allowed','users',type_='check')
    op.execute("UPDATE users SET role='user',revision=revision+1 WHERE role IN ('editor','viewer')")
    op.create_check_constraint('users_role_allowed','users',"role IN ('master','admin','user')")
    op.execute((root/'access_guards.sql').read_text())

def downgrade():raise RuntimeError('Access history and identities must be preserved. Restore a verified backup to a separate database.')
