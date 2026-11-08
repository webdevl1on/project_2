"""Bind an explicit trusted service actor to its SQLAlchemy operation, never HTTP body data."""
from functools import wraps
from inspect import signature
from contextlib import contextmanager
from types import SimpleNamespace


@contextmanager
def authorization_snapshot(db):
    """Evaluate against the factual pre-write scope throughout an atomic operation."""
    previous=db.info.get('access_write_evaluator')
    if previous is not None or db.info.get('access_actor') is None:
        yield
        return
    from app.services.access import Access
    evaluator=Access(db)
    def frozen(row):return SimpleNamespace(**{c.name:getattr(row,c.name) for c in row.__table__.columns})
    evaluator.positions={key:frozen(row) for key,row in evaluator.positions.items()}
    evaluator.current={key:frozen(row) for key,row in evaluator.current.items()}
    evaluator.past={key:[frozen(row) for row in rows] for key,rows in evaluator.past.items()}
    db.info['access_write_evaluator']=evaluator
    try:yield
    finally:db.info.pop('access_write_evaluator',None)

def actor_operation(function):
    params=signature(function)
    @wraps(function)
    def operation(*args,**kwargs):
        values=params.bind(*args,**kwargs).arguments;db=values.get('db')
        identity=values.get('actor_id',values.get('actor'))
        previous=db.info.get('access_actor') if db is not None else None
        if identity is not None and previous is not None and identity!=previous:raise PermissionError('Автор операції не відповідає перевіреній сесії.')
        if db is not None and identity is not None:db.info['access_actor']=identity
        try:return function(*args,**kwargs)
        finally:
            if db is not None:
                if previous is None:db.info.pop('access_actor',None)
                else:db.info['access_actor']=previous
    return operation
