"""Batch persistence for already-validated seed packages, no transaction ownership."""
from sqlalchemy import select, insert, update, func, and_, or_
from app.models import GeoUnit, GeoImportLink, GeoSource, GeoCityDistrict, GeoAlias, NameDictionary, NameDictionaryImport


def name_rows(db, values):
    existing={(r.kind,r.sex,r.normalized_key):r for r in db.scalars(select(NameDictionary))}
    report={'new':0,'unchanged':0,'updated':0}
    for value in values:
        key=(value['kind'],value['sex'],value['normalized_key']); old=existing.get(key)
        if old is None:
            db.add(NameDictionary(**value)); report['new']+=1
        elif all(getattr(old,k)==v for k,v in value.items()): report['unchanged']+=1
        else:
            for k,v in value.items(): setattr(old,k,v)
            report['updated']+=1
    return report


def geo_batch(connection, rows, kind, parent_ids, sources, digest):
    units=GeoUnit.__table__; links=GeoImportLink.__table__
    ids=[r['id'] for r in rows]
    old_links={r['external_id']:r for r in connection.execute(select(links).where(links.c.kind==kind,links.c.external_id.in_(ids))).mappings()}
    old={key:r['unit_id'] for key,r in old_links.items()}
    code_field=units.c.iso_code if kind=='country' else units.c.katottg_code
    codes=[r.get('iso_alpha2') if kind=='country' else r.get('katottg_code') for r in rows]
    official={}
    candidates=connection.execute(select(units.c.id,code_field).where(units.c.kind==kind,code_field.in_([c for c in codes if c]))) if any(codes) else []
    for row in candidates:
        if row[1] in official: raise ValueError('Неоднозначний офіційний код в існуючій БД.')
        official[row[1]]=row[0]
    next_id=connection.scalar(select(func.coalesce(func.max(units.c.id),0)))+1
    existing_ids=set(old.values()) | set(official.values())
    current_units={r['id']:r for r in connection.execute(select(units).where(units.c.id.in_(existing_ids))).mappings()} if existing_ids else {}
    new_units=[]; new_links=[]; mapped={}; created=0
    for raw in rows:
        code=raw.get('iso_alpha2') if kind=='country' else raw.get('katottg_code')
        uid=old.get(raw['id']) or official.get(code)
        value={'kind':kind,'name':raw.get('name_uk',raw.get('name')), 'parent_id':parent_ids.get(raw['id']),
               'iso_code':raw.get('iso_alpha2') or None,'katottg_code':raw.get('katottg_code') or None}
        from app.geography import normalize
        value['normalized_name']=normalize(value['name'])
        if uid is None:
            uid=next_id; next_id+=1; new_units.append(dict(id=uid,**value)); created+=1
        else:
            # Explicitly accepted package updates affect dictionary data, never address snapshots.
            current=current_units[uid]
            if current['kind']!=kind: raise ValueError('Зовнішній ключ зіставлено з іншою категорією GeoUnit.')
            if any(current[k]!=v for k,v in value.items()):
                connection.execute(update(units).where(units.c.id==uid).values(**value,revision=current['revision']+1))
        mapped[raw['id']]=uid
        details={k:raw[k] for k in ('source_row','street_type','settlement_type','region_type','external_code','source_city_district','iso_alpha3','iso_numeric') if k in raw}
        link={'kind':kind,'external_id':raw['id'],'unit_id':uid,'source_id':raw['source_id'],
              'source_version':sources[raw['source_id']]['version_date'],'package_digest':digest,'details':details}
        if raw['id'] not in old: new_links.append(link)
        elif any(old_links[raw['id']][key]!=value for key,value in link.items()):
            connection.execute(update(links).where(links.c.kind==kind,links.c.external_id==raw['id']).values(**link))
    if new_units: connection.execute(insert(units),new_units)
    if new_links: connection.execute(insert(links),new_links)
    return mapped,created


def city_batch(connection, rows, settlements, sources, digest):
    table=GeoCityDistrict.__table__; count=0
    existing={r.external_id:r.id for r in connection.execute(select(table.c.external_id,table.c.id).where(table.c.external_id.in_([r['id'] for r in rows])))}
    official={r.katottg_code:r.id for r in connection.execute(select(table.c.katottg_code,table.c.id).where(table.c.katottg_code.in_([r['katottg_code'] for r in rows])))}
    new=[]
    for raw in rows:
        value={'external_id':raw['id'],'name':raw['name'],'katottg_code':raw['katottg_code'],
               'settlement_id':settlements[raw['settlement_id']], 'source_id':raw['source_id'],
               'source_version':sources[raw['source_id']]['version_date'],'package_digest':digest}
        key=existing.get(raw['id']) or official.get(raw['katottg_code'])
        if key: connection.execute(update(table).where(table.c.id==key).values(**value))
        else: new.append(value); count+=1
    if new: connection.execute(insert(table),new)
    return count


def database_snapshot(connection):
    from app.models import (Rank,EventType,EventSubtype,Position,Person,PersonName,PersonRank,
                            PersonBirthplace,PersonAddress,PersonAssignment,PersonContact)
    count=lambda model:connection.scalar(select(func.count()).select_from(model))
    counts={m.__tablename__:count(m) for m in (Rank,EventType,EventSubtype,NameDictionary,Position,Person,PersonBirthplace,PersonAddress,PersonAssignment,GeoCityDistrict,PersonContact)}
    for kind,table in [('country','countries'),('region','regions'),('district','districts'),('community','communities'),('settlement','settlements'),('street','streets')]:
        counts[table]=connection.scalar(select(func.count()).select_from(GeoUnit).where(GeoUnit.kind==kind))
    names_and_ranks=[]
    for model in (PersonName,PersonRank):
        grouped=select(model.person_id,func.count().label('n')).where(model.is_active==True).group_by(model.person_id).subquery()
        names_and_ranks.append(connection.scalar(select(func.count()).select_from(grouped).where(grouped.c.n==1)))
    invalid_sex=connection.scalar(select(func.count()).select_from(Person).where(or_(Person.sex.is_(None),Person.sex.not_in(['male','female']))))
    people=list(connection.scalars(select(Person.person_id)))
    return counts,names_and_ranks,invalid_sex,people


def assignment_targets(db,row,version_id):
    from app.models import Person,Position,PersonAssignment
    person=db.scalar(select(Person.person_id).where(Person.tax_number==row['tax_number']))
    position=db.scalar(select(Position.position_id).where(Position.staff_version_id==version_id,Position.position_number==row['position_number']))
    existing=None
    if person is not None and position is not None:
        existing=db.scalar(select(PersonAssignment.id).where(PersonAssignment.person_id==person,PersonAssignment.position_id==position,
                PersonAssignment.assigned_from==row['start'],PersonAssignment.assigned_to==row['end']))
    return person,position,existing


def source_rows(connection,sources):
    table=GeoSource.__table__
    for key,value in sources.items():
        if connection.scalar(select(table.c.id).where(table.c.id==key)):
            connection.execute(update(table).where(table.c.id==key).values(metadata_json=value))
        else: connection.execute(insert(table).values(id=key,metadata_json=value))


def alias_row(connection,unit_id,name):
    from app.geography import normalize
    table=GeoAlias.__table__
    if connection.scalar(select(table.c.id).where(table.c.unit_id==unit_id,table.c.name==name)): return 0
    connection.execute(insert(table).values(unit_id=unit_id,name=name,normalized_name=normalize(name),historical=True))
    return 1
