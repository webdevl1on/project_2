
"""Frozen complete PostgreSQL schema, constraints, guards and function adapters."""
from pathlib import Path
from alembic import op

revision = '0001_postgresql'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    root = Path(__file__).resolve().parents[1] / 'sql'
    for name in ('initial_schema.sql', 'initial_guards.sql', 'initial_functions.sql', 'initial_catalog.sql'):
        op.get_bind().exec_driver_sql(
            (root / name).read_text(encoding="utf-8"),
            execution_options={'no_parameters': True}
        )


def downgrade():
    raise RuntimeError(
        'Initial production schema downgrade is destructive; '
        'restore a verified backup into a separate database.'
    )
