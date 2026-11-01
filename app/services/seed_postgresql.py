"""Non-destructive reference seeding; no people, resets, automatic upgrades or file copying."""
import argparse
from pathlib import Path
import json
from datetime import date
from sqlalchemy import select,text
from sqlalchemy.orm import sessionmaker
from app.database.settings import Settings
from app.database.schema_check import require_current_schema
from app.database.transactions import service_transaction
from app.models import Rank,EventType,EventSubtype,NameDictionary,TccOffice,StaffStructure,StaffVersion,Position
from app.models.reference_data.ranks import ReferenceRanks
from app.seeds.seed_event_types import EVENT_TYPES
from app.seeds.seed_event_subtypes import EVENT_SUBTYPES


def seed(db,*,dry_run=True,names=None,tcc=None,geography=None,staff_excel=None,version_name=None,valid_from=None,valid_to=None,structure_code='main'):
    if db.get_bind().dialect.name!='postgresql':raise ValueError('Цей CLI призначений тільки для PostgreSQL.')
    report={'new':0,'existing':0,'conflicts':0,'errors':[],'components':{}}
    def row(model,values,keys):
        old=db.scalar(select(model).filter_by(**{k:values[k] for k in keys}))
        if old is not None:
            if any(getattr(old,k)!=v for k,v in values.items()):report['conflicts']+=1
            else:report['existing']+=1
            return old
        report['new']+=1
        if not dry_run:
            old=model(**values);db.add(old);db.flush()
        return old
    with service_transaction(db,immediate=not dry_run):
        if dry_run:db.connection().exec_driver_sql('SET TRANSACTION READ ONLY')
        else:db.execute(text("SELECT pg_advisory_xact_lock(hashtext('project2_reference_seed'))"))
        for values in ReferenceRanks.RANKS:row(Rank,values,['code'])
        for code,name in EVENT_TYPES:
            row(EventType,{'event_type':code,'event_name':name},['event_type'])
        for code,subtypes in EVENT_SUBTYPES.items():
            event=db.scalar(select(EventType).where(EventType.event_type==code))
            if event:
                for subcode,name in subtypes:row(EventSubtype,{'event_type_id':event.event_type_id,'event_subtype':subcode,'event_subtype_name':name},['event_type_id','event_subtype'])
            elif dry_run:report['new']+=len(subtypes)
        report['components']['references']='ready'
        if geography:
            from app.services.seed_packages import preflight_geography
            from app.services.seed_geography import seed_geography
            prepared=preflight_geography(geography)
            report['components']['geography']=seed_geography(db.get_bind(),geography,prepared,connection=db.connection(),dry_run=dry_run,preserve=True)
            report['new']+=sum(v['created'] for v in report['components']['geography'].values())
            report['existing']+=sum(v['existing'] for v in report['components']['geography'].values())
            if not dry_run:
                db.execute(text("SELECT setval(pg_get_serial_sequence('geo_units','id'),greatest(coalesce((SELECT max(id) FROM geo_units),0),1),EXISTS(SELECT 1 FROM geo_units))"))
        if names:
            from app.services.name_dictionary_import import read_workbook
            from app.services.seed_packages import preflight_names
            books=preflight_names(names)['books'] if Path(names).is_dir() else [Path(names)]
            errors=[]
            seen=set()
            for book in books:
                rows,issues=read_workbook(book.read_bytes());errors+=issues
                for item in rows:
                    identity=tuple(item['values'][k] for k in ('kind','sex','normalized_key'))
                    if identity in seen:errors.append('Дубль словника між файлами.');continue
                    seen.add(identity);row(NameDictionary,item['values'],['kind','sex','normalized_key'])
            report['errors']+=errors
            report['components']['names']='ready' if not errors else 'invalid'
        if tcc:
            from app.services.tcc_import import preview
            prepared=preview(db,Path(tcc).read_bytes(),'add');report['errors']+=prepared['errors']
            for item in prepared['rows']:row(TccOffice,item['values'],['normalized_name','normalized_region','normalized_settlement'])
            report['components']['tcc']='ready' if not prepared['errors'] else 'invalid'
        if staff_excel:
            if not version_name or not valid_from:raise ValueError('Штат потребує назви й точної дати початку.')
            from app.services.staff_import import read_positions,preview_import
            from app.seeds.seed_reference import seed_positions
            from app.validators.position_validator import POSITION_ATTRIBUTES
            parsed=read_positions(staff_excel);report['errors']+=parsed['errors']
            structure=db.scalar(select(StaffStructure).where(StaffStructure.code==structure_code))
            existing=db.scalar(select(StaffVersion).where(StaffVersion.staff_structure_id==structure.id,StaffVersion.name==version_name)) if structure else None
            if existing:
                stored=[{key:getattr(p,key) for key in POSITION_ATTRIBUTES} for p in db.scalars(select(Position).where(Position.staff_version_id==existing.id).order_by(Position.position_number))]
                if existing.valid_from!=valid_from or existing.valid_to!=valid_to or stored!=sorted(parsed['positions'],key=lambda r:r['position_number']):report['conflicts']+=1
                else:report['existing']+=1+len(stored)
            else:
                prepared=preview_import(db,staff_excel,structure.id if structure else None,version_name,valid_from,valid_to,valid_to is None)
                report['errors']+=prepared['errors'];report['new']+=1+len(parsed['positions'])
                if not dry_run and not report['errors'] and not report['conflicts']:seed_positions(db,staff_excel,version_name=version_name,valid_from=valid_from,valid_to=valid_to,structure_code=structure_code)
            report['components']['staff']='ready'
        if (report['errors'] or report['conflicts']) and not dry_run:raise ValueError('Засівання скасовано: є конфлікти або помилки. Спочатку виконайте --dry-run.')
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true');parser.add_argument('--allow-production',action='store_true')
    for name in ('names','tcc','geography','staff-excel'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--version-name');parser.add_argument('--valid-from',type=date.fromisoformat);parser.add_argument('--valid-to',type=date.fromisoformat);parser.add_argument('--structure-code',default='main')
    args=parser.parse_args(argv);settings=Settings.read()
    if settings.environment=='production' and not args.allow_production:parser.error('Production seeding requires explicit --allow-production; not authorized by normal development setup.')
    from sqlalchemy import create_engine
    engine=create_engine(settings.url,**settings.engine_options())
    try:
        require_current_schema(engine)
        with sessionmaker(bind=engine,autoflush=False)() as db:
            print(json.dumps(seed(db,**{k:v for k,v in vars(args).items() if k!='allow_production'}),ensure_ascii=False,indent=2))
    except Exception as error:
        # No DSN or bound personal values in diagnostics.
        print('Засівання скасовано: '+(str(error) if isinstance(error,ValueError) else type(error).__name__));return 2
    finally:engine.dispose()
    return 0

if __name__=='__main__':raise SystemExit(main())
