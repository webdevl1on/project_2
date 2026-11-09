"""Extend the existing maintenance boundary to PostgreSQL application writes."""
import re
from sqlalchemy import event,text
from sqlalchemy.orm import Session

class MaintenanceUnavailable(RuntimeError):pass

def protect_write(db):
    if db.get_bind().dialect.name!='postgresql':return
    connection=db.connection();transaction=db.get_transaction()
    if db.info.get('backup_write_transaction') is transaction:return
    if not connection.scalar(text("SELECT pg_try_advisory_xact_lock_shared(hashtext(current_schema()),hashtext('project2_backup_snapshot'))")):
        raise MaintenanceUnavailable('Триває фіксація резервного знімка. Повторіть збереження; введені дані не втрачено.')
    db.info['backup_write_transaction']=transaction

@event.listens_for(Session,'before_flush')
def before_flush(db,*_):
    if db.new or db.dirty or db.deleted:protect_write(db)

@event.listens_for(Session,'do_orm_execute')
def before_bulk(state):
    if state.is_insert or state.is_update or state.is_delete or re.match(r'^\s*(INSERT|UPDATE|DELETE|MERGE)\b',str(state.statement),re.I):protect_write(state.session)
