"""Logical assignment annulment and append-only personnel operations."""
from alembic import op
import sqlalchemy as sa

revision = '0005_assignment_history'
down_revision = '0004_event_catalog'
branch_labels = depends_on = None


def upgrade():
    op.add_column('person_assignments', sa.Column('annulled_at', sa.DateTime(), nullable=True))
    op.add_column('person_assignments', sa.Column('annulment_reason', sa.String(2000), nullable=True))
    op.add_column('person_assignments', sa.Column('annulled_by', sa.Integer(), nullable=True))
    op.create_foreign_key('assignment_annulled_by_user', 'person_assignments', 'users', ['annulled_by'], ['id'])
    op.create_check_constraint('assignment_annulment_reason', 'person_assignments', "(annulled_at IS NULL AND annulment_reason IS NULL AND annulled_by IS NULL) OR (annulled_at IS NOT NULL AND annulment_reason IS NOT NULL AND length(trim(annulment_reason)) BETWEEN 1 AND 2000)")
    for name, field in [('person_period_exclusion','person_id'),('position_period_exclusion','staff_position_id')]:
        op.execute(f'ALTER TABLE person_assignments DROP CONSTRAINT {name}')
        op.execute(f"ALTER TABLE person_assignments ADD CONSTRAINT {name} EXCLUDE USING gist ({field} WITH =, daterange(assigned_from,coalesce(assigned_to,DATE '9999-12-31'),'[]') WITH &&) WHERE (annulled_at IS NULL)")
    op.create_table('assignment_audit',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('assignment_id', sa.Integer(), sa.ForeignKey('person_assignments.id'), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('operation', sa.String(30), nullable=False),
        sa.Column('before', sa.JSON(), nullable=False), sa.Column('after', sa.JSON(), nullable=False),
        sa.Column('reason', sa.String(2000), nullable=True),
        sa.CheckConstraint("operation IN ('create','edit','orders','complete','transfer','annul','restore')", name='assignment_audit_operation'))
    op.create_index('ix_assignment_audit_assignment_id', 'assignment_audit', ['assignment_id'])
    op.execute("""CREATE FUNCTION project2_assignment_audit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'assignment audit is append only' USING ERRCODE='23514'; END; $$""")
    for action in ('UPDATE','DELETE'):
        op.execute(f'CREATE TRIGGER assignment_audit_no_{action.lower()} BEFORE {action} ON assignment_audit FOR EACH ROW EXECUTE FUNCTION project2_assignment_audit_guard()')
    for action in ('insert', 'update'):
        op.execute(f"""CREATE OR REPLACE FUNCTION guard_person_assignments_{action}_fn() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN
            IF NEW.annulled_at IS NOT NULL THEN RETURN NEW; END IF;
            PERFORM 1 FROM staff_versions v JOIN positions p ON p.staff_version_id=v.id WHERE p.position_id=NEW.staff_position_id FOR SHARE OF v;
            IF NOT EXISTS (SELECT 1 FROM positions p JOIN staff_versions v ON v.id=p.staff_version_id
              WHERE p.position_id=NEW.staff_position_id AND NEW.assigned_from>=v.valid_from
              AND (v.valid_to IS NULL OR (NEW.assigned_to IS NOT NULL AND NEW.assigned_to<=v.valid_to)))
            THEN RAISE EXCEPTION 'assignment outside version period' USING ERRCODE='23514'; END IF;
            IF EXISTS (SELECT 1 FROM person_assignments a WHERE a.id!=NEW.id AND a.annulled_at IS NULL
              AND (a.person_id=NEW.person_id OR a.staff_position_id=NEW.staff_position_id)
              AND a.assigned_from<=coalesce(NEW.assigned_to,DATE '9999-12-31')
              AND NEW.assigned_from<=coalesce(a.assigned_to,DATE '9999-12-31'))
            THEN RAISE EXCEPTION 'assignment periods overlap' USING ERRCODE='23514'; END IF;
            RETURN NEW;
          END; $$""")
        op.execute(f"""CREATE OR REPLACE FUNCTION guard_staff_versions_{action}_fn() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN
            IF EXISTS (SELECT 1 FROM staff_versions v WHERE v.id!=NEW.id AND v.staff_structure_id=NEW.staff_structure_id
              AND v.valid_from<=coalesce(NEW.valid_to,DATE '9999-12-31') AND NEW.valid_from<=coalesce(v.valid_to,DATE '9999-12-31'))
            THEN RAISE EXCEPTION 'staff version periods overlap' USING ERRCODE='23514'; END IF;
            IF EXISTS (SELECT 1 FROM person_assignments a JOIN positions p ON p.position_id=a.staff_position_id
              WHERE p.staff_version_id=NEW.id AND a.annulled_at IS NULL AND (a.assigned_from<NEW.valid_from OR
              (NEW.valid_to IS NOT NULL AND (a.assigned_to IS NULL OR a.assigned_to>NEW.valid_to))))
            THEN RAISE EXCEPTION 'assignments outside version period' USING ERRCODE='23514'; END IF;
            RETURN NEW;
          END; $$""")
    op.execute("""CREATE FUNCTION project2_annulled_assignment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.annulled_at IS NOT NULL AND (NEW.annulled_at IS NOT NULL OR
          ROW(NEW.person_id,NEW.staff_position_id,NEW.assigned_from,NEW.assigned_to,NEW.assignment_order_number,NEW.assignment_order_date,NEW.release_order_number,NEW.release_order_date,NEW.completion_reason,NEW.completion_note)
          IS DISTINCT FROM ROW(OLD.person_id,OLD.staff_position_id,OLD.assigned_from,OLD.assigned_to,OLD.assignment_order_number,OLD.assignment_order_date,OLD.release_order_number,OLD.release_order_date,OLD.completion_reason,OLD.completion_note))
        THEN RAISE EXCEPTION 'restore annulled assignment before editing' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END; $$""")
    op.execute('CREATE TRIGGER assignment_annulled_guard BEFORE UPDATE ON person_assignments FOR EACH ROW EXECUTE FUNCTION project2_annulled_assignment_guard()')


def downgrade():
    raise RuntimeError('Downgrade would destroy assignment audit; restore a verified backup to a separate database.')
