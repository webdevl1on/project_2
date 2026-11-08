"""Explicit synthetic User grants replacing old Editor/Viewer regression fixtures.

New ACL tests do not use this adapter: their Users start with no permissions.
Production migration grants nothing. No runtime behavior is patched here.
"""
from app.services import accounts
from app.models.access import AccessRule
from app.access_catalog import CATEGORIES

def legacy_user(db,username,display_name,password,role='user',**kwargs):
    old=role
    from app.models import User
    manager=db.get(User,kwargs.get('actor_id')) if kwargs.get('actor_id') else None
    if role=='admin' and manager and manager.role=='admin':
        # Pre-existing administrator in a synthetic DB-owner fixture, not an application grant.
        with accounts.account_write(db):
            user=User(username=username,display_name=display_name,password_hash=accounts.password_hash(password),role='admin');db.add(user);db.flush()
            accounts.audit_change(db,user,'create',{},None,'Synthetic pre-existing administrator fixture')
            key=user.id
        return key
    key=accounts.create_user(db,username,display_name,password,'user' if old in ('editor','viewer') else role,**kwargs)
    if old in ('editor','viewer'):
        for category in CATEGORIES:
            db.add(AccessRule(user_id=key,scope_type='global',category=category,action='edit' if old=='editor' else 'read',effect='ALLOW',created_by=kwargs['actor_id']))
        if old=='editor':db.add(AccessRule(user_id=key,scope_type='global',category='personal',action='create',effect='ALLOW',created_by=kwargs['actor_id']))
        db.commit()
    return key
