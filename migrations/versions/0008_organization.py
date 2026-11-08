"""Organizational history, explicit roster coverage and partial import receipts."""
from pathlib import Path
from alembic import op
import sqlalchemy as sa
revision='0008_organization'
down_revision='0007_mfa_sessions'
branch_labels=depends_on=None


def upgrade():
    # New objects below are frozen PostgreSQL DDL, never live-model create_all.
    _create_core()
    for name,typ in [('annulled_at',sa.DateTime()),('annulment_reason',sa.String(2000)),('annulled_by',sa.Integer())]:op.add_column('staff_versions',sa.Column(name,typ,nullable=True))
    op.create_check_constraint('org_version_annul_reason','staff_versions',"(annulled_at IS NULL AND annulment_reason IS NULL AND annulled_by IS NULL) OR (annulled_at IS NOT NULL AND annulment_reason IS NOT NULL AND length(trim(annulment_reason)) BETWEEN 1 AND 2000)")
    op.create_foreign_key('staff_version_annulled_by_fk','staff_versions','users',['annulled_by'],['id'])
    op.execute('ALTER TABLE staff_versions DROP CONSTRAINT version_period_exclusion')
    op.execute("ALTER TABLE staff_versions ADD CONSTRAINT version_period_exclusion EXCLUDE USING gist (staff_structure_id WITH =,daterange(valid_from,coalesce(valid_to,DATE '9999-12-31'),'[]') WITH &&) WHERE (annulled_at IS NULL)")
    op.add_column('staff_structures',sa.Column('org_unit_id',sa.Integer(),nullable=True))
    op.create_foreign_key('staff_structure_org_fk','staff_structures','org_units',['org_unit_id'],['id'])
    op.create_unique_constraint('staff_structure_org_unique','staff_structures',['org_unit_id'])
    for name,typ in [('org_unit_id',sa.Integer()),('managed_unit_id',sa.Integer()),('valid_from',sa.Date()),('valid_to',sa.Date()),('annulled_at',sa.DateTime()),('annulment_reason',sa.String(2000)),('annulled_by',sa.Integer())]:op.add_column('positions',sa.Column(name,typ,nullable=True))
    for name,target,key in [('org_unit_id','org_units','id'),('managed_unit_id','org_units','id'),('annulled_by','users','id')]:op.create_foreign_key('position_'+name+'_fk','positions',target,[name],[key])
    op.create_index('ix_positions_org_unit_id','positions',['org_unit_id'])
    op.drop_constraint('positions_staff_version_id_position_number_key','positions',type_='unique')
    op.create_index('active_staff_position_number','positions',['staff_version_id','position_number'],unique=True,postgresql_where=sa.text('annulled_at IS NULL'))
    op.create_check_constraint('org_position_period','positions','valid_to IS NULL OR valid_from IS NULL OR valid_to>=valid_from')
    op.create_check_constraint('org_position_annul_reason','positions',"annulled_at IS NULL OR (annulment_reason IS NOT NULL AND length(trim(annulment_reason)) BETWEEN 1 AND 2000)")
    _create_staff()
    root=Path(__file__).resolve().parents[1]/'sql'
    op.execute((root/'organization_tree_guards.sql').read_text())
    op.execute((root/'organization_staff_guards.sql').read_text())


def _create_core():
    op.execute("\nCREATE TABLE org_units (\n\tid SERIAL NOT NULL, \n\tkind VARCHAR(20) NOT NULL, \n\tformed_on DATE NOT NULL, \n\tdissolved_on DATE, \n\tsort_order INTEGER NOT NULL, \n\tannulled_at TIMESTAMP WITHOUT TIME ZONE, \n\tannulment_reason VARCHAR(2000), \n\tannulled_by INTEGER, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\trevision INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT org_unit_kind CHECK (kind IN ('unit','regiment','battalion','company','platoon','squad','other')), \n\tCONSTRAINT org_unit_lifetime CHECK (dissolved_on IS NULL OR dissolved_on>=formed_on), \n\tCONSTRAINT org_unit_annulment CHECK ((annulled_at IS NULL AND annulment_reason IS NULL AND annulled_by IS NULL) OR (annulled_at IS NOT NULL AND annulment_reason IS NOT NULL AND length(trim(annulment_reason)) BETWEEN 1 AND 2000)), \n\tFOREIGN KEY(annulled_by) REFERENCES users (id)\n)\n\n")
    op.execute('\nCREATE TABLE org_unit_states (\n\tid SERIAL NOT NULL, \n\torg_unit_id INTEGER NOT NULL, \n\tname VARCHAR(500) NOT NULL, \n\tnormalized_name VARCHAR(500) NOT NULL, \n\tprimary_parent_id INTEGER, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\trevision INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT org_state_period CHECK (valid_to IS NULL OR valid_to>=valid_from), \n\tCONSTRAINT org_state_not_self CHECK (primary_parent_id IS NULL OR primary_parent_id!=org_unit_id), \n\tCONSTRAINT org_state_name CHECK (length(trim(normalized_name))>0), \n\tFOREIGN KEY(org_unit_id) REFERENCES org_units (id), \n\tFOREIGN KEY(primary_parent_id) REFERENCES org_units (id)\n)\n\n')
    op.execute('CREATE INDEX ix_org_unit_states_primary_parent_id ON org_unit_states (primary_parent_id)')
    op.execute('CREATE INDEX ix_org_unit_states_org_unit_id ON org_unit_states (org_unit_id)')
    op.execute('CREATE INDEX ix_org_state_period ON org_unit_states (org_unit_id, valid_from, valid_to)')
    op.execute('\nCREATE TABLE org_operational_subordinations (\n\tid SERIAL NOT NULL, \n\torg_unit_id INTEGER NOT NULL, \n\tparent_id INTEGER NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tnote VARCHAR(2000), \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\trevision INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT org_operational_period CHECK (valid_to IS NULL OR valid_to>=valid_from), \n\tCONSTRAINT org_operational_not_self CHECK (parent_id!=org_unit_id), \n\tFOREIGN KEY(org_unit_id) REFERENCES org_units (id), \n\tFOREIGN KEY(parent_id) REFERENCES org_units (id)\n)\n\n')
    op.execute('CREATE INDEX ix_org_operational_subordinations_org_unit_id ON org_operational_subordinations (org_unit_id)')
    op.execute('CREATE INDEX ix_org_operational_subordinations_parent_id ON org_operational_subordinations (parent_id)')
    op.execute("\nCREATE TABLE org_audit (\n\tid SERIAL NOT NULL, \n\torg_unit_id INTEGER NOT NULL, \n\tactor_user_id INTEGER NOT NULL, \n\toccurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\toperation VARCHAR(30) NOT NULL, \n\tbefore JSON NOT NULL, \n\tafter JSON NOT NULL, \n\treason VARCHAR(2000), \n\tPRIMARY KEY (id), \n\tCONSTRAINT org_audit_operation CHECK (operation IN ('create','state','dissolve','annul','order','operational','coverage','map','import','withdraw','position','position_annul','reassignment')), \n\tFOREIGN KEY(org_unit_id) REFERENCES org_units (id), \n\tFOREIGN KEY(actor_user_id) REFERENCES users (id)\n)\n\n")
    op.execute('CREATE INDEX ix_org_audit_org_unit_id ON org_audit (org_unit_id)')

def _create_staff():
    op.execute('\nCREATE TABLE org_staff_coverage (\n\tid SERIAL NOT NULL, \n\torg_unit_id INTEGER NOT NULL, \n\tstaff_version_id INTEGER NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tannulled_at TIMESTAMP WITHOUT TIME ZONE, \n\tannulment_reason VARCHAR(2000), \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\trevision INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT org_coverage_period CHECK (valid_to IS NULL OR valid_to>=valid_from), \n\tFOREIGN KEY(org_unit_id) REFERENCES org_units (id), \n\tFOREIGN KEY(staff_version_id) REFERENCES staff_versions (id)\n)\n\n')
    op.execute('CREATE INDEX ix_org_staff_coverage_org_unit_id ON org_staff_coverage (org_unit_id)')
    op.execute('CREATE INDEX ix_org_staff_coverage_staff_version_id ON org_staff_coverage (staff_version_id)')
    op.execute("\nCREATE TABLE org_staff_imports (\n\tid SERIAL NOT NULL, \n\tidentity_key VARCHAR(64) NOT NULL, \n\tscope_unit_id INTEGER NOT NULL, \n\towner_unit_id INTEGER NOT NULL, \n\tstaff_version_id INTEGER, \n\tmode VARCHAR(20) NOT NULL, \n\teffective_on DATE NOT NULL, \n\tvalid_to DATE, \n\tactor_id INTEGER NOT NULL, \n\tsnapshot JSON NOT NULL, \n\teffects JSON NOT NULL, \n\twithdrawn_at TIMESTAMP WITHOUT TIME ZONE, \n\twithdrawal_reason VARCHAR(2000), \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\trevision INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT org_import_mode CHECK (mode IN ('add','official','correct','replace')), \n\tUNIQUE (identity_key), \n\tFOREIGN KEY(scope_unit_id) REFERENCES org_units (id), \n\tFOREIGN KEY(owner_unit_id) REFERENCES org_units (id), \n\tFOREIGN KEY(staff_version_id) REFERENCES staff_versions (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id)\n)\n\n")
    op.execute("\nCREATE TABLE org_staff_import_rows (\n\tid SERIAL NOT NULL, \n\timport_id INTEGER NOT NULL, \n\trow_number INTEGER NOT NULL, \n\tpayload JSON NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tissue VARCHAR(2000), \n\tposition_id INTEGER, \n\tbefore JSON, \n\tafter_revision INTEGER, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\trevision INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (import_id, row_number), \n\tCONSTRAINT org_import_row_status CHECK (status IN ('pending','accepted','unchanged','conflict')), \n\tFOREIGN KEY(import_id) REFERENCES org_staff_imports (id), \n\tFOREIGN KEY(position_id) REFERENCES positions (position_id)\n)\n\n")
    op.execute('CREATE INDEX ix_org_staff_import_rows_import_id ON org_staff_import_rows (import_id)')
    op.execute('\nCREATE TABLE org_reassignments (\n\tid SERIAL NOT NULL, \n\timport_id INTEGER NOT NULL, \n\tassignment_id INTEGER NOT NULL, \n\treplacement_position_id INTEGER, \n\tresolved_assignment_id INTEGER, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\trevision INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (import_id, assignment_id), \n\tFOREIGN KEY(import_id) REFERENCES org_staff_imports (id), \n\tFOREIGN KEY(assignment_id) REFERENCES person_assignments (id), \n\tFOREIGN KEY(replacement_position_id) REFERENCES positions (position_id), \n\tFOREIGN KEY(resolved_assignment_id) REFERENCES person_assignments (id)\n)\n\n')

def downgrade():raise RuntimeError('Organization history cannot be discarded. Restore a verified backup to a separate database.')
