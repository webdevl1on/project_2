"""Atomic independent facts, explicit evidence and non-destructive task sync."""
from datetime import date
from app.models import MedicalSelection, PersonnelTask, PersonnelAudit, MedicalDocumentLink, PersonDocument, DocumentDetails
from app.models.medical import MODELS
from app.medical_catalog import FORM_FIELDS, DOCUMENT_ROLES, EXAM_STATES, FITNESS, AWARD_STATES, BASES, TASK_STATES
from app.repositories.medical_repository import MedicalRepository as Repo
from app.repositories.document_repository import DocumentRepository as Docs
from app.services.accounts import authorize
from app.services.documents import document_transaction, audit as document_audit, _text, WRITE_ROLES


def exact(value,required=False):
    if value in (None,''):
        if required:raise ValueError('Потрібна повна календарна дата.')
        return None
    if type(value) is date:return value
    if not isinstance(value,str) or len(value)!=10 or value[4:5]!='-' or value[7:8]!='-':raise ValueError('Потрібна повна календарна дата: день, місяць, рік.')
    try:return date.fromisoformat(value)
    except ValueError:raise ValueError('Некоректна календарна дата.') from None


def record(db,pid,kind,key,revision=None):
    if kind not in MODELS:raise ValueError('Невідомий розділ.')
    row=Repo.get(db,kind,key)
    if not row or row.person_id!=pid:raise ValueError('Запис цієї особи не знайдено.')
    if revision is not None and str(row.revision)!=str(revision):raise ValueError('Запис уже змінено; оновіть дані. Чернетку не знищено.')
    return row


def snapshot(row):
    return {c.name:(v.isoformat() if isinstance(v,date) else v) for c in row.__table__.columns if c.name not in ('created_at','updated_at') for v in [getattr(row,c.name)]}


def audit(db,actor,pid,kind,row,operation,old):
    new=snapshot(row)
    Repo.add(db,PersonnelAudit(person_id=pid,actor_id=actor,entity=kind,entity_id=row.id if hasattr(row,'id') else pid,operation=operation,changes={key:{'old':old.get(key),'new':new.get(key)} for key in old.keys()|new.keys() if old.get(key)!=new.get(key)}))


def _link(db,pid,kind,value):
    if value in (None,''):return None
    if type(value) is not int and not (isinstance(value,str) and value.isdecimal()):raise ValueError('Потрібен цілий ID запису.')
    try:key=int(value)
    except (ValueError,TypeError):raise ValueError('Некоректний ID запису.') from None
    return record(db,pid,kind,key).id


def validated(db,pid,kind,data):
    if kind not in MODELS or not isinstance(data,dict):raise ValueError('Невідомий розділ або некоректні поля.')
    allowed={field[0] for field in FORM_FIELDS[kind]}
    if set(data)-allowed:raise ValueError('Невідомі поля: '+', '.join(sorted(set(data)-allowed)))
    values={}
    for key,label,input_type,options in FORM_FIELDS[kind]:
        value=data.get(key)
        if key in ('injury_id','award_id'):value=_link(db,pid,'injuries' if key=='injury_id' else 'awards',value)
        elif input_type=='date':
            try:value=exact(value,kind=='dna' and key=='collected_on')
            except ValueError as error:raise ValueError(label+': '+str(error)) from None
        elif input_type=='checkbox':
            if value not in (True,False,None):raise ValueError(label+': потрібна галочка.')
            value=bool(value)
        elif input_type=='select':
            value=value or {'exams':{'status':'NEEDS_EXAM','basis':'OTHER'},'awards':{'status':'NOT_PROCESSED'},'tasks':{'status':'OPEN'}}.get(kind,{}).get(key)
            if value is not None and value not in options:raise ValueError(label+': невідоме значення.')
        else:value=_text(value,options or 500)
        values[key]=value
    if kind=='tasks' and not values['title']:raise ValueError('Вкажіть назву завдання.')
    if kind=='exams':
        if values['injury_id'] and values['basis']!='INJURY':raise ValueError('Пов’язане поранення потребує підстави «Поранення».')
        if values['status']!='COMPLETED' and values['fitness']:raise ValueError('Придатність вноситься лише для завершеного ВЛК.')
    if kind=='awards':
        if values['submission_confirmed'] and not (values['submission_on'] and values['submission_number']):raise ValueError('Підтверджене подання потребує дати та реквізитів подання.')
        if values['refusal_confirmed'] and not (values['refusal_on'] and values['refusal_number'] and values['refusal_reason']):raise ValueError('Оформлений рапорт потребує дати, номера та короткого обґрунтування.')
    return values


def processed(award):
    return bool((award.submission_confirmed and award.submission_on and award.submission_number) or (award.refusal_confirmed and award.refusal_on and award.refusal_number and award.refusal_reason))


def _sync(db,actor,pid):
    injuries=Repo.rows(db,'injuries',pid);tasks=Repo.rows(db,'tasks',pid);awards=Repo.rows(db,'awards',pid)
    warnings=[]
    for injury in injuries:
        task=next((t for t in tasks if t.kind=='injury_award' and t.injury_id==injury.id),None)
        if task is None:
            task=Repo.add(db,PersonnelTask(person_id=pid,kind='injury_award',injury_id=injury.id,title='Опрацювати питання нагородження',status='OPEN',manual_decision=False))
            db.flush();audit(db,actor,pid,'tasks',task,'automatic_create',{})
        evidence=[a for a in awards if a.injury_id==injury.id and processed(a)]
        desired='COMPLETED' if evidence else 'OPEN'
        award_id=evidence[0].id if len(evidence)==1 else None
        if task.manual_decision:
            if task.status!=desired:warnings.append(f'Завдання №{task.id}: ручне рішення збережено; автоматичний стан був би «{TASK_STATES[desired]}».')
        elif task.status!=desired or task.award_id!=award_id:
            old=snapshot(task);task.status=desired;task.award_id=award_id;db.flush();audit(db,actor,pid,'tasks',task,'automatic_sync',old)
    return warnings


def save(db,actor,pid,kind,data,*,key=None,revision=None):
    with document_transaction(db,subject="кадрового запису"):
        authorize(db,actor,WRITE_ROLES)
        if Repo.person(db,pid) is None:raise ValueError('Особу не знайдено.')
        if kind not in MODELS or not isinstance(data,dict):raise ValueError('Невідомий розділ або некоректні поля.')
        if key is not None:
            if revision is None:raise ValueError('Потрібна revision.')
            row=record(db,pid,kind,key,revision);old=snapshot(row)
            values=validated(db,pid,kind,{**{f[0]:getattr(row,f[0]) for f in FORM_FIELDS[kind]},**data})
        else:
            values=validated(db,pid,kind,data)
            row=Repo.add(db,MODELS[kind](person_id=pid));old={}
        if kind=='exams' and key is not None and values['status']!='COMPLETED':
            choice=Repo.selection(db,pid)
            if choice and choice.exam_id==key:raise ValueError('Спочатку скасуйте ручний вибір активного ВЛК.')
        if kind=='tasks':
            if key is not None and row.kind=='injury_award' and values['injury_id']!=row.injury_id:raise ValueError('Джерело автоматичного завдання не змінюється.')
            if values['status']!='OPEN':
                if not values['decision_reason']:raise ValueError('Вкажіть причину ручного завершення або скасування.')
            # Editing responsible/note alone must not override automatic workflow.
            if key is None or values['status']!=row.status or (values['status']!='OPEN' and values['decision_reason']!=row.decision_reason):row.manual_decision=True
        for name,value in values.items():setattr(row,name,value)
        db.flush();audit(db,actor,pid,kind,row,'update' if key is not None else 'create',old)
        warnings=_sync(db,actor,pid) if kind in ('injuries','awards') else []
        result=row.id
    return {'id':result,'warnings':warnings}


def select_active(db,actor,pid,exam_id,revision=None):
    if exam_id is not None and type(exam_id) is not int:raise ValueError('Потрібен ID ВЛК або null.')
    with document_transaction(db,subject="кадрового запису"):
        authorize(db,actor,WRITE_ROLES)
        if Repo.person(db,pid) is None:raise ValueError('Особу не знайдено.')
        if exam_id is not None:
            chosen=record(db,pid,'exams',exam_id)
            if chosen.status!='COMPLETED':raise ValueError('Активним може бути лише завершене ВЛК.')
        row=Repo.selection(db,pid)
        if row and str(row.revision)!=str(revision):raise ValueError('Ручний вибір уже змінено; оновіть дані.')
        old=snapshot(row) if row else {}
        row=row or Repo.add(db,MedicalSelection(person_id=pid))
        row.exam_id=exam_id;db.flush();audit(db,actor,pid,'selection',row,'manual_select' if exam_id else 'automatic_select',old)


def active_exam(db,pid):
    result=Repo.active(db,pid)
    row,ambiguous=result if result else (None,False)
    return row,('Активне ВЛК не визначено: однакові або відсутні дати завершених довідок.' if ambiguous else None)


def link_document(db,actor,pid,kind,key,category,*,document_id=None,revision=None):
    if category not in DOCUMENT_ROLES.get(kind,{}):raise ValueError('Невідома категорія документа.')
    with document_transaction(db,subject="кадрового запису"):
        authorize(db,actor,WRITE_ROLES);target=record(db,pid,kind,key,revision)
        if revision is None:raise ValueError('Потрібна revision предметного запису.')
        if document_id is not None:
            if type(document_id) is not int:raise ValueError('Потрібен цілий ID документа.')
            doc=Docs.document(db,document_id)
            if not doc or doc.person_id!=pid:raise ValueError('Документ належить іншій особі або відсутній.')
        else:
            # A historical shell avoids the single-current-per-type constraint;
            # it is not a claim about physical presence or completeness.
            doc=Docs.add(db,PersonDocument(person_id=pid,document_type_id=Docs.type(db,'other').id,is_current=False))
            db.flush();Docs.add(db,DocumentDetails(document_id=doc.id));document_audit(db,actor,doc,'create',{'source':kind,'record_id':key,'category':category})
        fk={'exams':'exam_id','injuries':'injury_id','awards':'award_id'}[kind]
        old=snapshot(target)
        link=Repo.add(db,MedicalDocumentLink(document_id=doc.id,category=category,**{fk:key}));db.flush()
        # Touch revision so concurrent link creation cannot use stale snapshots.
        target.revision+=1
        audit(db,actor,pid,kind,target,'document_link',old)
        document_audit(db,actor,doc,'medical_link',{'entity':kind,'id':key,'category':category})
        result=doc.id
    return result


def page(db,actor,pid):
    authorize(db,actor)
    if Repo.person(db,pid) is None:raise ValueError('Особу не знайдено.')
    result={kind:[snapshot(row) for row in Repo.rows(db,kind,pid)] for kind in MODELS}
    chosen,warning=active_exam(db,pid);choice=Repo.selection(db,pid)
    result.update(active_exam=snapshot(chosen) if chosen else None,active_warning=warning,
                  selection={'exam_id':choice.exam_id if choice else None,'revision':choice.revision if choice else None})
    result['links']=[{**snapshot(link),'files':[{'id':f.id,'name':f.original_name,'revision':f.revision} for f in Repo.files(db,link.document_id)],'document_revision':Docs.document(db,link.document_id).revision} for link in Repo.links(db,pid)]
    result['audit']=[{'id':r.id,'actor_id':r.actor_id,'occurred_at':r.occurred_at.isoformat()+'Z','entity':r.entity,'entity_id':r.entity_id,'operation':r.operation,'changes':r.changes} for r in Repo.audits(db,pid)]
    result['pending_exams']=[r for r in result['exams'] if r['status']!='COMPLETED']
    result['warnings']=[f'Завдання №{t["id"]}: діє ручне рішення.' for t in result['tasks'] if t['manual_decision']]
    return result
