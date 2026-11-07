"""Mandatory two-stage MFA and bounded sessions; legacy sessions stay invalid."""
from alembic import op
import sqlalchemy as sa
revision='0007_mfa_sessions'
down_revision='0006_account_management'
branch_labels=depends_on=None
OPERATIONS="'create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master','mfa_enroll','factor_add','factor_remove','backup_use','backup_generate','mfa_recover','mfa_reauth'"

def upgrade():
    for name,typ in [('public_id',sa.String(32)),('created_at',sa.DateTime()),('last_activity',sa.DateTime()),('mfa_verified_at',sa.DateTime())]:op.add_column('user_sessions',sa.Column(name,typ,nullable=True))
    op.create_unique_constraint('user_sessions_public_id_key','user_sessions',['public_id'])
    op.create_check_constraint('session_mfa_times','user_sessions',"mfa_verified_at IS NULL OR (public_id IS NOT NULL AND created_at IS NOT NULL AND last_activity IS NOT NULL AND last_activity>=created_at AND mfa_verified_at>=created_at AND mfa_verified_at<expires_at AND expires_at>created_at)")
    # NULL on all old rows: never manufacture proof of MFA for legacy sessions.
    op.execute('\nCREATE TABLE mfa_key_state (\n\tid SERIAL NOT NULL, \n\tciphertext VARCHAR(1000) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT one_mfa_key_state CHECK (id=1)\n)\n\n')
    op.execute('\nCREATE TABLE totp_factors (\n\tid SERIAL NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\tciphertext VARCHAR(1000) NOT NULL, \n\tlast_step INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT totp_step_valid CHECK (last_step>=-1), \n\tUNIQUE (user_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)\n\n')
    op.execute('\nCREATE TABLE passkeys (\n\tid SERIAL NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\tcredential_id BYTEA NOT NULL, \n\tpublic_key BYTEA NOT NULL, \n\tsign_count INTEGER NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT passkey_counter_valid CHECK (sign_count>=0), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tUNIQUE (credential_id)\n)\n\n')
    op.execute('CREATE INDEX ix_passkeys_user_id ON passkeys (user_id)')
    op.execute('\nCREATE TABLE recovery_codes (\n\tid SERIAL NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\tdigest VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tUNIQUE (digest)\n)\n\n')
    op.execute('CREATE INDEX ix_recovery_codes_user_id ON recovery_codes (user_id)')
    op.execute("\nCREATE TABLE auth_flows (\n\ttoken_hash VARCHAR(64) NOT NULL, \n\tuser_id INTEGER NOT NULL, \n\tcsrf_token VARCHAR(64) NOT NULL, \n\tkind VARCHAR(20) NOT NULL, \n\tpassword_stamp VARCHAR(64) NOT NULL, \n\tsession_hash VARCHAR(64), \n\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tconsumed BOOLEAN NOT NULL, \n\tverified BOOLEAN NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tciphertext VARCHAR(1000), \n\tchallenge JSON, \n\treturn_to VARCHAR(4096) NOT NULL, \n\tPRIMARY KEY (token_hash), \n\tCONSTRAINT auth_flow_kind CHECK (kind IN ('setup','login','manage','reauth')), \n\tCONSTRAINT auth_flow_attempts CHECK (attempts>=0 AND attempts<=5), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(session_hash) REFERENCES user_sessions (token_hash) ON DELETE CASCADE\n)\n\n")
    op.execute('CREATE INDEX ix_auth_flows_user_id ON auth_flows (user_id)')
    op.drop_constraint('account_audit_operation','account_audit',type_='check')
    op.create_check_constraint('account_audit_operation','account_audit',f'operation IN ({OPERATIONS})')

def downgrade():raise RuntimeError('Restore a verified backup to a separate database; do not remove MFA protections or audit.')
