from sqlalchemy import select,delete,update
from app.models.mfa import AuthFlow,TotpFactor,Passkey,RecoveryCode,MfaKeyState
from app.models.accounts import UserSession

class MfaRepository:
    @staticmethod
    def flow(db,key):return db.get(AuthFlow,key,populate_existing=True)
    @staticmethod
    def totp(db,uid):return db.scalar(select(TotpFactor).where(TotpFactor.user_id==uid))
    @staticmethod
    def passkeys(db,uid):return list(db.scalars(select(Passkey).where(Passkey.user_id==uid).order_by(Passkey.id)))
    @staticmethod
    def codes(db,uid):return list(db.scalars(select(RecoveryCode).where(RecoveryCode.user_id==uid)))
    @staticmethod
    def clear_codes(db,uid):db.execute(delete(RecoveryCode).where(RecoveryCode.user_id==uid))
    @staticmethod
    def sessions(db,uid):return list(db.scalars(select(UserSession).where(UserSession.user_id==uid)))
    @staticmethod
    def clear_factors(db,uid):
        for model in (TotpFactor,Passkey,RecoveryCode):db.execute(delete(model).where(model.user_id==uid))
        db.execute(delete(AuthFlow).where(AuthFlow.user_id==uid))
    @staticmethod
    def encrypted_rows(db):return [db.get(MfaKeyState,1),*db.scalars(select(TotpFactor)),*db.scalars(select(AuthFlow).where(AuthFlow.ciphertext.is_not(None)))]

    @staticmethod
    def invalidate_flows(db,uid,except_hash):db.execute(update(AuthFlow).where(AuthFlow.user_id==uid,AuthFlow.token_hash!=except_hash).values(consumed=True))
