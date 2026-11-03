"""Keep legacy DAY_OFF history; add a standalone clerical VLK event type."""
from alembic import op
revision = '0004_event_catalog'
down_revision = '0003_event_corrections'
branch_labels = depends_on = None


def upgrade():
    op.execute("UPDATE event_types SET event_is_active=false WHERE event_type='DAY_OFF'")
    op.execute("INSERT INTO event_types (event_type,event_name,event_is_active,event_exclusive) SELECT 'VLK','ВЛК',true,true WHERE NOT EXISTS (SELECT 1 FROM event_types WHERE event_type='VLK')")


def downgrade():
    raise RuntimeError('Do not remove referenced catalog entries or overwrite prior user activity; restore a verified backup into a separate database.')
