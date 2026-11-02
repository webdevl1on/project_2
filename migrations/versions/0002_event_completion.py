"""Add explicit event planning/completion without rewriting historical periods."""
from alembic import op
import sqlalchemy as sa

revision = '0002_event_completion'
down_revision = '0001_postgresql'
branch_labels = depends_on = None


def upgrade():
    op.add_column('person_events', sa.Column('planned_end', sa.Date(), nullable=True))
    op.add_column('person_events', sa.Column('completion_confirmed', sa.Boolean(), nullable=False, server_default=sa.false()))
    # Existing date_end was the actual end under the old contract. Preserve it,
    # recognise closed legacy records, never infer a planned end or close opens.
    op.execute("UPDATE person_events SET completion_confirmed = true WHERE date_end <= (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Kyiv')::date")
    op.create_check_constraint('event_planned_period', 'person_events', 'planned_end IS NULL OR planned_end >= date_start')
    op.create_check_constraint('event_confirmed_end', 'person_events', 'NOT completion_confirmed OR date_end IS NOT NULL')
    for code, label in [('SERVICE_DUTY', 'Чергування'), ('SERVICE_AFTER_DUTY', 'Після чергування'), ('SERVICE_DAY_OFF', 'Вихідний')]:
        op.get_bind().execute(sa.text('''INSERT INTO event_subtypes (event_type_id,event_subtype,event_subtype_name,event_subtype_is_active)
            SELECT t.event_type_id,:code,:label,true FROM event_types t WHERE t.event_type='SERVICE'
            AND NOT EXISTS (SELECT 1 FROM event_subtypes s WHERE s.event_type_id=t.event_type_id AND s.event_subtype=:code)''').bindparams(sa.bindparam('code', type_=sa.String()), sa.bindparam('label', type_=sa.String())), {'code': code, 'label': label})


def downgrade():
    raise RuntimeError('Downgrade would discard planning and completion decisions; restore a verified backup into a separate database.')
