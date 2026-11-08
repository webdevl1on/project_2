"""HTTP ACL boundary: resolve real subject IDs before existing route handlers run."""
from fastapi import HTTPException
from app.services import access
from app.models import PersonName,PersonRank,PersonAssignment,Position,PersonPositionMirage
from app.repositories.access_repository import AccessRepository as Repo

CATALOG_MODULES={'geography','name_cases','service_bases'}

async def enforce(request,db):
    user=request.state.authenticated_user
    db.info.pop('access_read_evaluator',None)
    db.info['access_actor']=user.id;db.info['access_session_hash']=request.state.personal_session.token_hash
    if user.role!='admin':request.state.access_evaluator=access.Access(db)
    module=request.scope['endpoint'].__module__.rsplit('.',1)[-1];name=request.scope['endpoint'].__name__
    path=request.url.path;params={k:int(v) if (k=='key' or k.endswith('_id')) and str(v).isdigit() else v for k,v in request.path_params.items()};write=request.method not in ('GET','HEAD','OPTIONS')
    action='edit' if write else 'read'
    if module in ('accounts','account_management','mfa'):
        if module=='account_management' and path.startswith('/admin/') or module=='accounts' and name=='create':
            if user.role not in ('master','admin'):raise HTTPException(403,'Потрібні системні повноваження.')
        return
    if module=='access_control':return  # Its services require fresh MFA and bounded management authority.
    if path in ('/admin','/admin/login','/admin/logout'):
        if user.role not in ('master','admin'):raise HTTPException(403,'Потрібні системні повноваження.')
        return
    if user.role=='admin':return
    def need(category,action=action,**scope):access.require(db,category,action,**scope)
    try:
        if module=='persons':
            if name=='get_persons_page':return
            if name=='person_created':
                need('personal','create');return
            if name in ('person_created','get_person_page','get_person_full_info'):
                e=access.Access(db)
                if not any(e.allowed(c,person_id=params['person_id']) for c in access.CATEGORIES):raise PermissionError()
                return
            if name in ('get_create_person_page','create_person_from_form'):need('personal','create');return
            need('personal',person_id=params['person_id'])
            if name=='get_edit_person_page':need('basic','read',person_id=params['person_id'])
            if write and 'tax_number' in await request.form():need('documents',person_id=params['person_id'])
            return
        if module in ('contacts','geography','service_bases','profile_records','documents','medical','person_events','service_chronology') and 'person_id' in params:
            category={'contacts':'personal','geography':'personal','service_bases':'service','profile_records':'family' if params.get('kind')=='family' else 'personal','documents':'documents','medical':'medical','person_events':'events','service_chronology':'service'}[module]
            if module=='service_chronology' and name=='personal_number':category='personal'
            if module=='contacts' and name=='overview':
                e=access.Access(db)
                if not any(e.allowed(c,person_id=params['person_id']) for c in access.CATEGORIES):raise PermissionError()
                return
            need(category,'override' if module=='documents' and name=='override' else action,person_id=params['person_id'])
            if module=='documents' and (name=='audit_log' or request.query_params.get('history')=='true'):need('history','read',person_id=params['person_id'])
            return
        if module in ('person_name','person_rank','name_cases'):
            model=PersonRank if module=='person_rank' else PersonName
            key=params.get('person_rank_id') or params.get('person_name_id') or params.get('name_id')
            row=Repo.get(db,model,key) if key else None
            pid=params.get('person_id') or (row.person_id if row else None)
            if pid is not None:
                need('service' if module=='person_rank' else 'basic' if module=='person_name' else 'personal',person_id=pid)
                if module=='name_cases':need('basic','read',person_id=pid)
                return
            if module=='name_cases' and name=='dictionary_lookup':return
            raise PermissionError()
        if module in CATALOG_MODULES and not write:return # Reference data only; no person payloads.
        if module=='event_journal' and name=='presence':need('events',person_id=int(request.query_params.get('person_id','0')));return
        if module in ('person_positions','event_journal') or module=='staff' and name=='history':return # Scoped read queries apply below.
        if module=='staff' and name=='assignment_audit':
            row=Repo.get(db,PersonAssignment,int(params['key']))
            if row is None:raise PermissionError()
            need('history','read',person_id=row.person_id);return
        if module in ('staff','service_chronology'):
            body=dict(await request.form()) if write else {}
            assignment=None
            if name in ('correct_assignment','change_assignment_state','assignment'):
                assignment=Repo.get(db,PersonAssignment,int(params['key']))
                if assignment is None:raise PermissionError()
                need('service',person_id=assignment.person_id);need('service',position_id=assignment.staff_position_id)
            if name in ('assign','confirm_history'):
                from app.services.staff_tokens import verify
                body=verify(body.get('token',''),'assignment')
            if name=='change_mirage':
                row=Repo.get(db,PersonPositionMirage,int(params['key']))
                if row is None:raise PermissionError()
                body={**body,'position_id':row.staff_position_id,'person_id':row.person_id}
            if body.get('position_id'):
                need('service',position_id=int(body['position_id']))
                if body.get('person_id'):need('service',person_id=int(body['person_id']))
                return
            if assignment:return
            raise PermissionError()
        if module in ('organization','organization_staff'):
            # Per-object service/flush checks enforce writes; read DTOs are pruned in views.
            e=access.Access(db)
            special='reorder' if name=='reorder' else 'reparent' if params.get('action')=='parent' else 'bind' if name=='mapping' else 'import' if name in ('preview','confirm','receipt_action') else action
            if not any(e.allowed('organization',special,unit_id=key) for key in e.states) and not e.allowed('organization',special):raise PermissionError()
            return
        raise PermissionError() # Every new subject route must declare its policy.
    except (PermissionError,ValueError,TypeError,KeyError):
        raise HTTPException(403,'Недостатньо прав доступу до цієї категорії та області.') from None
