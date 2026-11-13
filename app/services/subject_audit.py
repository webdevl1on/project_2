"""Mapper hooks share the existing ORM service transaction.

No audit backfill. Dedicated document/medical/assignment/org audits remain canonical.
Unknown server-side actors stay NULL. Caller supplied HTTP fields never enter here.
"""
from datetime import date,datetime,UTC
from sqlalchemy import event,select
from sqlalchemy.orm import object_session
from app.database.base import Base
from app.models.subject_audit import SubjectAudit

TABLES={
    'persons':'personal','person_names':'basic','person_name_cases':'personal',
    'person_ranks':'service','person_service_history':'service','person_service_bases':'service',
    'person_contacts':'personal','person_addresses':'personal','person_birthplaces':'personal',
    'person_position_mirages':'service','person_events':'events',
    'positions':'organization','staff_structures':'organization','staff_versions':'organization',
}

def value(v):
    if isinstance(v,datetime):return (v.replace(tzinfo=UTC) if v.tzinfo is None else v.astimezone(UTC)).isoformat()
    if isinstance(v,(date,datetime)):return v.isoformat()
    return v

def record(mapper,connection,row,operation):
    table=row.__table__;db=object_session(row)
    if TABLES[table.name]=='organization' and db and db.info.get('access_org_action'):return
    pk=list(table.primary_key)[0];identity=getattr(row,pk.name)
    before=getattr(row,'_subject_audit_before',{})
    if table.name=='person_events' and operation=='edit' and db:
        from app.models.event_correction import PersonEventCorrection
        if any(isinstance(a,PersonEventCorrection) and a.event_id==row.event_id for a in db.new):
            row.__dict__.pop('_subject_audit_before',None);return
    if operation=='edit':
        persisted=connection.execute(select(table).where(pk==identity)).mappings().one()
        after={k:value(v) for k,v in persisted.items()}
    else:after={c.name:value(getattr(row,c.name)) for c in table.columns} if operation!='delete' else {}
    if operation=='edit' and before==after:return
    pid=getattr(row,'person_id',None)
    if table.name=='person_name_cases':
        names=Base.metadata.tables['person_names']
        pid=connection.scalar(select(names.c.person_id).where(names.c.person_name_id==row.person_name_id))
        if before:before['person_id']=connection.scalar(select(names.c.person_id).where(names.c.person_name_id==before['person_name_id']))
        if after:after['person_id']=pid
    actor=db.info.get('access_actor') if db else None
    if table.name=='staff_versions':
        structures=Base.metadata.tables['staff_structures']
        after['org_unit_id']=connection.scalar(select(structures.c.org_unit_id).where(structures.c.id==row.staff_structure_id))
        if before:before['org_unit_id']=connection.scalar(select(structures.c.org_unit_id).where(structures.c.id==before['staff_structure_id']))
    connection.execute(SubjectAudit.__table__.insert().values(actor_user_id=actor,person_id=pid,
        object_type=table.name,object_id=identity,category=TABLES[table.name],operation=operation,
        before=before,after=after,reason=(db.info.get('audit_reason') if db else None)))
    row.__dict__.pop('_subject_audit_before',None)

def before(mapper,connection,row):
    table=row.__table__;pk=list(table.primary_key)[0]
    statement=select(table).where(pk==getattr(row,pk.name))
    if connection.dialect.name=='postgresql':statement=statement.with_for_update()
    found=connection.execute(statement).mappings().first()
    row._subject_audit_before={k:value(v) for k,v in found.items()} if found else {}

def install():
    for mapper in list(Base.registry.mappers):
        model=mapper.class_
        if mapper.local_table.name not in TABLES:continue
        event.listen(model,'before_update',before);event.listen(model,'before_delete',before)
        event.listen(model,'after_insert',lambda m,c,r:record(m,c,r,'create'))
        event.listen(model,'after_update',lambda m,c,r:record(m,c,r,'edit'))
        event.listen(model,'after_delete',lambda m,c,r:record(m,c,r,'delete'))
