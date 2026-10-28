"""System account persistence; no transaction ownership."""
from sqlalchemy import select, func
from app.models.accounts import User, UserSession


class AccountRepository:
    @staticmethod
    def user(db, key): return db.get(User, key)

    @staticmethod
    def by_name(db, name): return db.scalar(select(User).where(User.username == name))

    @staticmethod
    def count(db): return db.scalar(select(func.count()).select_from(User))

    @staticmethod
    def session(db, digest): return db.get(UserSession, digest)

    @staticmethod
    def add(db, value): db.add(value); return value

    @staticmethod
    def delete(db, value): db.delete(value)
