"""Unified read-only audit UI. Search/export share the same authorized projection."""
from urllib.parse import urlencode
from datetime import datetime
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.security.accounts import current_user
from app.services import audit
from app.templating import templates

router=APIRouter(prefix='/admin/audit',tags=['Audit'])
TABS={'system':'Системний аудит','subject':'Аудит предметних даних','backup':'Аудит резервування'}

def parameters(request):
    params=dict(request.query_params)
    if 'sort1' in params:
        params['sort']=','.join(('-' if params.get('dir'+str(i))=='desc' else '')+params['sort'+str(i)] for i in range(1,4) if params.get('sort'+str(i))) or '-at,id'
    return params

@router.get('')
def page(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    params=parameters(request);kind=params.get('tab','system')
    try:result=audit.page(db,kind,params,user_id=user.id)
    except ValueError as error:raise HTTPException(422,str(error)) from None
    columns=[{'key':k,'label':v,'informational':True,'default_visible':True,'draggable':True,'resizable':True,'sortable':False,'filterable':False,'width':250 if k in ('before','after','reason') else 150,'min_width':80} for k,v in audit.LABELS.items()]
    config={'id':'audit-'+kind,'groups':[{'key':'audit','label':TABS[kind],'columns':columns}]}
    def link(**changes):return '/admin/audit?'+urlencode({**params,**changes})
    return templates.TemplateResponse(request=request,name='admin/audit.html',context={
        'audit_page':result,'audit_params':params,'audit_tab':kind,'audit_tabs':TABS,'audit_columns':config,
        'audit_labels':audit.LABELS,'audit_link':link,'audit_timestamp':lambda v:datetime.fromisoformat(v),
        'export_url':'/admin/audit/export.txt?'+urlencode(params),'audit_changes':audit.changed,'audit_field':audit.field_label,'audit_display':audit.display})

@router.get('/export.txt')
def export(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    params=parameters(request)
    try:rows=audit.filtered(db,params.get('tab','system'),params,user_id=user.id)
    except ValueError as error:raise HTTPException(422,str(error)) from None
    return StreamingResponse(audit.text_export(rows),media_type='text/plain; charset=utf-8',headers={'Content-Disposition':'attachment; filename="project2-audit.txt"','Cache-Control':'no-store'})
