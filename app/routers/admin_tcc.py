"""TCC administration uses the existing admin and CSRF policy."""
from urllib.parse import urlencode
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.security.admin import require_admin, check_csrf
from app.routers.admin import render
from app.services import tcc_directory as directory, tcc_import as excel, dictionary_previews

router = APIRouter(prefix='/admin/tcc', dependencies=[Depends(require_admin)])


@router.get('')
def index(request: Request, q: str = '', page: int = 1, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return render(request, 'admin/tcc.html', owner, **directory.page(db, q, page))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get('/template.xlsx')
def template():
    return Response(excel.empty_template(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="tcc_offices_empty.xlsx"', 'Cache-Control': 'no-store'})


@router.get('/new')
@router.get('/{key}/edit')
def editor(request: Request, key: int | None = None, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        data = directory.record(db, key) if key is not None else {'is_active': True}
        return render(request, 'admin/tcc_form.html', owner, data=data, key=key, tcc_types=directory.TYPES)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.post('/new')
@router.post('/{key}/edit')
async def save(request: Request, key: int | None = None, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    data = dict(await request.form()); check_csrf(owner, data.get('csrf'))
    data['is_active'] = data.get('is_active') == 'on'
    try:
        directory.save(db, data, key)
        return RedirectResponse('/admin/tcc?' + urlencode({'message': 'Установу збережено.'}), 303)
    except ValueError as error:
        return render(request, 'admin/tcc_form.html', owner, status=409, data=data, key=key, tcc_types=directory.TYPES, error=str(error))


@router.post('/import/preview')
async def preview(request: Request, file: UploadFile = File(), mode: str = Form('add'), csrf: str = Form(''),
                  owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    check_csrf(owner, csrf)
    try:
        if not (file.filename or '').lower().endswith('.xlsx'):
            raise ValueError('Оберіть .xlsx-файл.')
        prepared = excel.preview(db, await file.read(5 * 1024 * 1024 + 1), mode)
        token = dictionary_previews.store(prepared, owner, resource='tcc') if not prepared['errors'] else None
        return render(request, 'admin/tcc_preview.html', owner, prepared=prepared, token=token, tcc_types=directory.TYPES)
    except ValueError as error:
        return render(request, 'admin/error.html', owner, status=400, error=str(error))
    finally:
        await file.close()


@router.post('/import/confirm')
def confirm(request: Request, token: str = Form(''), csrf: str = Form(''), reviewed: bool = Form(False),
            confirm_updates: bool = Form(False), owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    check_csrf(owner, csrf)
    prepared = None
    try:
        prepared, key = dictionary_previews.load(token, owner, resource='tcc')
        counts = excel.confirm(db, prepared, key, reviewed=reviewed, confirm_updates=confirm_updates)
        return RedirectResponse('/admin/tcc?' + urlencode({'message': f"Імпорт завершено: нових {counts['new']}, оновлених {counts['updated']}."}), 303)
    except ValueError as error:
        if prepared is not None:
            return render(request, 'admin/tcc_preview.html', owner, status=409, prepared=prepared, token=token,
                          tcc_types=directory.TYPES, error=str(error))
        return render(request, 'admin/error.html', owner, status=409, error=str(error))
