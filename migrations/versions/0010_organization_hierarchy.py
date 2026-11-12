"""Explicit organization levels and additional unit kinds; preserve all identities/history."""
from pathlib import Path
from alembic import op
import sqlalchemy as sa
revision='0010_organization_hierarchy'
down_revision='0009_access_control'
branch_labels=depends_on=None

def upgrade():
    op.add_column('org_units',sa.Column('hierarchy_level',sa.Integer(),nullable=True))
    op.drop_constraint('org_unit_kind','org_units',type_='check')
    op.create_check_constraint('org_unit_kind','org_units',"kind IN ('unit','regiment','battalion','detachment','company','battery','platoon','squad','team','crew','other')")
    # NULL is retained for existing unclassified other units; no guessed levels.
    op.create_check_constraint('org_unit_level','org_units',"(kind='other' AND (hierarchy_level IS NULL OR hierarchy_level BETWEEN 1 AND 7)) OR (kind!='other' AND hierarchy_level IS NULL)")
    op.execute((Path(__file__).resolve().parents[1]/'sql/organization_hierarchy.sql').read_text())

def downgrade():
    raise RuntimeError('Organization kinds/levels and audit must be preserved. Restore a verified backup in isolation.')
