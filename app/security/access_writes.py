"""Last service-layer check for ORM writes in an identified application operation.

HTTP binds its verified principal to the Session. Explicit service actor IDs use
that same boundary. DB-owner seed/migration tools are not HTTP user operations.
"""
from sqlalchemy import event,inspect
from sqlalchemy.orm import Session
from app.services import access

PERSON_CATEGORIES={
 'person_names':'basic','person_ranks':'service','passports':'documents',
 'person_service_history':'service','person_contacts':'personal','person_addresses':'personal',
 'person_birthplaces':'personal','person_service_bases':'service','person_events':'events',
 'person_medical_exams':'medical','person_injuries':'medical','person_awards':'medical','person_dna_samples':'medical',
 'personnel_tasks':'medical','person_medical_selections':'medical','person_education':'personal',
 'person_family_members':'family','person_directives':'personal',
}

@event.listens_for(Session,'before_flush')
def check_writes(db,ctx,instances):
    if db.info.get('access_actor') is None:return
    rows=list(db.new|db.dirty|db.deleted)
    protected=[r for r in rows if r.__table__.name in PERSON_CATEGORIES or r.__table__.name in (
        'persons','person_assignments','person_position_mirages','person_name_cases','positions','staff_structures','staff_versions','org_units','org_unit_states','org_operational_subordinations','org_staff_coverage','person_documents','document_details','document_driving_categories','document_files','person_document_states','medical_document_links')]
    if not protected:return
    e=db.info.get('access_write_evaluator') or access.Access(db)
    if e.user.role=='admin':return
    def need(c,a='edit',**scope):
        if not e.allowed(c,a,**scope):raise PermissionError('Недостатньо прав для збереження цієї категорії та області.')
    created=db.info.setdefault('access_created_people',set())
    clinical={}
    def clinical_document(doc):
        if doc.person_id not in clinical:clinical[doc.person_id]=access.Repo.medical_document_ids(db,doc.person_id)
        if doc.id in clinical[doc.person_id]:need('medical',person_id=doc.person_id)
    for row in protected:
        table=row.__table__.name;pid=getattr(row,'person_id',None)
        if table=='persons' and row in db.new:
            need('personal','create');created.add(row);continue
        if pid and any(p.person_id==pid for p in created):continue # Initial aggregate, authorized by explicit create permission.
        if table=='persons':
            history=inspect(row).attrs.tax_number.history
            if history.has_changes():need('documents',person_id=pid)
            if any(inspect(row).attrs[k].history.has_changes() for k in ('birth_day','birth_month','birth_year','sex','personal_number')):need('personal',person_id=pid)
        elif table in ('person_assignments','person_position_mirages'):
            need('service',person_id=pid);need('service',position_id=row.staff_position_id)
            state=inspect(row)
            for old in state.attrs.person_id.history.deleted:need('service',person_id=old)
            for old in state.attrs.staff_position_id.history.deleted:need('service',position_id=old)
        elif table=='person_name_cases':
            from app.models import PersonName
            name=db.get(PersonName,row.person_name_id)
            if name is None:raise PermissionError('ПІБ недоступне.')
            if any(p.person_id==name.person_id for p in created):continue
            need('personal',person_id=name.person_id);need('basic','read',person_id=name.person_id)
        elif table in PERSON_CATEGORIES:need(PERSON_CATEGORIES[table],person_id=pid)
        elif table in ('person_documents','person_document_states'):
            need('documents',person_id=pid)
            if table=='person_documents':clinical_document(row)
        elif table in ('document_details','document_driving_categories','document_files','medical_document_links'):
            from app.models import PersonDocument
            doc=db.get(PersonDocument,row.document_id)
            if doc is None:raise PermissionError('Документ недоступний.')
            need('documents',person_id=doc.person_id)
            clinical_document(doc)
            if table=='medical_document_links':need('medical',person_id=doc.person_id)
        elif table=='positions':
            state=inspect(row);action='bind' if any(state.attrs[k].history.has_changes() for k in ('org_unit_id','managed_unit_id')) and row not in db.new else 'edit'
            need('organization',action,position_id=row.position_id,unit_id=row.org_unit_id)
            if row.managed_unit_id and action=='bind':need('organization','bind',unit_id=row.managed_unit_id)
        elif table=='org_units':
            if row in db.new:need('organization',unit_id=db.info.get('access_new_unit_parent'))
            elif any(inspect(row).attrs[k].history.has_changes() for k in ('sort_order','formed_on','dissolved_on','annulled_at','kind')):need('organization','reorder' if inspect(row).attrs.sort_order.history.has_changes() else 'edit',unit_id=row.id)
        elif table=='org_unit_states':
            action=db.info.get('access_org_action')
            need('organization','reparent' if action=='reparent' else 'edit',unit_id=row.org_unit_id)
        elif table in ('org_operational_subordinations','org_staff_coverage'):need('organization','bind' if table=='org_staff_coverage' and db.info.get('access_org_action')=='bind' else 'edit',unit_id=row.org_unit_id)
        elif table in ('staff_structures','staff_versions'):
            from app.models import StaffStructure
            structure=row if table=='staff_structures' else db.get(StaffStructure,row.staff_structure_id)
            need('organization','bind' if db.info.get('access_org_action')=='bind' else 'edit',unit_id=structure.org_unit_id)

@event.listens_for(Session,'after_commit')
@event.listens_for(Session,'after_rollback')
def clear_created(db):
    db.info.pop('access_created_people',None);db.info.pop('access_read_evaluator',None);db.info.pop('access_new_unit_parent',None)
