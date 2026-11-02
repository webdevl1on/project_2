"""Preserve annulled events and record intentional type corrections."""
from alembic import op
import sqlalchemy as sa
revision = '0003_event_corrections'
down_revision = '0002_event_completion'
branch_labels = depends_on = None


def upgrade():
    op.add_column('person_events', sa.Column('annulled_at', sa.DateTime(), nullable=True))
    op.add_column('person_events', sa.Column('annulment_reason', sa.Text(), nullable=True))
    op.add_column('person_events', sa.Column('annulled_by', sa.Integer(), nullable=True))
    op.create_foreign_key('event_annulled_by_user','person_events','users',['annulled_by'],['id'])
    op.create_check_constraint('event_annulment_reason','person_events',"(annulled_at IS NULL AND annulment_reason IS NULL AND annulled_by IS NULL) OR (annulled_at IS NOT NULL AND annulment_reason IS NOT NULL AND length(trim(annulment_reason)) > 0)")
    op.create_table('person_event_corrections',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('person_events.event_id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.Column('operation',sa.String(30),nullable=False),
        sa.Column('before',sa.JSON(),nullable=False), sa.Column('after',sa.JSON(),nullable=False),
        sa.CheckConstraint("operation IN ('type_change','annul')",name='event_correction_operation'))
    op.create_index('ix_person_event_corrections_event_id','person_event_corrections',['event_id'])
    op.execute("""CREATE FUNCTION project2_event_correction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'event corrections are append only'; END; $$""")
    for action in ('UPDATE','DELETE'):
        op.execute(f'CREATE TRIGGER event_correction_no_{action.lower()} BEFORE {action} ON person_event_corrections FOR EACH ROW EXECUTE FUNCTION project2_event_correction_guard()')
    op.execute("""CREATE FUNCTION project2_event_record_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'annul event instead of deleting'; END IF;
          IF OLD.annulled_at IS NOT NULL THEN RAISE EXCEPTION 'annulled event is immutable'; END IF;
          RETURN NEW;
        END; $$""")
    op.execute('CREATE TRIGGER person_event_no_delete BEFORE DELETE ON person_events FOR EACH ROW EXECUTE FUNCTION project2_event_record_guard()')
    op.execute('CREATE TRIGGER person_event_annulled_immutable BEFORE UPDATE ON person_events FOR EACH ROW EXECUTE FUNCTION project2_event_record_guard()')


def downgrade():
    raise RuntimeError('Downgrade would lose annulment and correction history; restore a verified backup into a separate database.')
