"""Persistent MFA credentials/challenges, never process-local authentication state."""
from datetime import datetime
from sqlalchemy import String,Integer,DateTime,ForeignKey,LargeBinary,Boolean,CheckConstraint,JSON
from sqlalchemy.orm import Mapped,mapped_column
from app.database.base import Base

class MfaKeyState(Base):
    __tablename__='mfa_key_state'
    id: Mapped[int]=mapped_column(primary_key=True)
    ciphertext: Mapped[str]=mapped_column(String(1000))
    __table_args__=(CheckConstraint('id=1',name='one_mfa_key_state'),)

class TotpFactor(Base):
    __tablename__='totp_factors'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    ciphertext: Mapped[str]=mapped_column(String(1000))
    last_step: Mapped[int]=mapped_column(default=-1)
    __table_args__=(CheckConstraint('last_step>=-1',name='totp_step_valid'),)

class Passkey(Base):
    __tablename__='passkeys'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    credential_id: Mapped[bytes]=mapped_column(LargeBinary,unique=True)
    public_key: Mapped[bytes]=mapped_column(LargeBinary)
    sign_count: Mapped[int]=mapped_column(default=0)
    name: Mapped[str]=mapped_column(String(100))
    __table_args__=(CheckConstraint('sign_count>=0',name='passkey_counter_valid'),)

class RecoveryCode(Base):
    __tablename__='recovery_codes'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    digest: Mapped[str]=mapped_column(String(64),unique=True)

class AuthFlow(Base):
    __tablename__='auth_flows'
    token_hash: Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    csrf_token: Mapped[str]=mapped_column(String(64))
    kind: Mapped[str]=mapped_column(String(20))
    password_stamp: Mapped[str]=mapped_column(String(64))
    session_hash: Mapped[str|None]=mapped_column(ForeignKey('user_sessions.token_hash',ondelete='CASCADE'))
    expires_at: Mapped[datetime]=mapped_column(DateTime)
    consumed: Mapped[bool]=mapped_column(Boolean,default=False)
    verified: Mapped[bool]=mapped_column(Boolean,default=False)
    attempts: Mapped[int]=mapped_column(Integer,default=0)
    ciphertext: Mapped[str|None]=mapped_column(String(1000))
    challenge: Mapped[dict|None]=mapped_column(JSON)
    return_to: Mapped[str]=mapped_column(String(4096),default='/persons')
    __table_args__=(CheckConstraint("kind IN ('setup','login','manage','reauth')",name='auth_flow_kind'),CheckConstraint('attempts>=0 AND attempts<=5',name='auth_flow_attempts'),)
