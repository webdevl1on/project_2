"""Protected dictionary administration; business and SQL live below HTTP."""
import hmac
from urllib.parse import urlencode
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.name_cases import CASES, NAME_PARTS, SEXES, IMPORT_HEADERS
from app.security.admin import (require_admin, configured_token, check_transport, new_session,
                                csrf_token, check_csrf, dev_admin_open, COOKIE, TTL)
from app.services import name_cases, name_dictionary_import, dictionary_previews
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["Administration"])


def render(request, name, owner=None, status=200, **context):
    return templates.TemplateResponse(request=request, name=name, status_code=status,
        headers={"Cache-Control": "no-store"}, context={"parts": NAME_PARTS, "cases": CASES,
        "sexes": SEXES, "csrf": csrf_token(owner) if owner else "", **context})


@router.get("/login")
def login_page(request: Request):
    if dev_admin_open(request):
        return RedirectResponse("/admin", 303)
    if configured_token():
        check_transport(request)
    return render(request, "admin/login.html", enabled=bool(configured_token()))


@router.post("/login")
def login(request: Request, token: str = Form("")):
    if dev_admin_open(request):
        return RedirectResponse("/admin", 303)
    expected = configured_token()
    if expected is None:
        raise HTTPException(503, "Адміністрування вимкнено.")
    check_transport(request)
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Вхід дозволено лише з цієї сторінки.")
    if not hmac.compare_digest(token.encode(), expected.encode()):
        return render(request, "admin/login.html", status=401, enabled=True, error="Неправильний адміністративний токен.")
    response = RedirectResponse("/admin", 303)
    response.set_cookie(COOKIE, new_session(), max_age=TTL, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict", path="/admin")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/logout")
def logout(csrf: str = Form(""), owner: str = Depends(require_admin)):
    check_csrf(owner, csrf)
    response = RedirectResponse("/admin/login", 303)
    response.delete_cookie(COOKIE, path="/admin")
    return response


@router.get("")
def index(request: Request):
    try:
        owner = require_admin(request)
    except HTTPException as error:
        if error.status_code == 401:
            return RedirectResponse("/admin/login", 303)
        raise
    return render(request, "admin/index.html", owner, message=request.query_params.get("message", ""))


@router.get("/dictionaries")
def dictionaries(request: Request, kind: str = "surname", q: str = "", page: int = 1,
                 owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        context = name_cases.dictionary_page(db, kind, q, page)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return render(request, "admin/dictionaries.html", owner, **context)


@router.get("/dictionaries/template.xlsx")
def dictionary_template(owner: str = Depends(require_admin)):
    return Response(name_dictionary_import.empty_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="name_dictionaries_empty.xlsx"', "Cache-Control": "no-store"})


@router.post("/dictionaries/import/preview")
async def import_preview(request: Request, file: UploadFile = File(), mode: str = Form("add"),
                         csrf: str = Form(""), owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    check_csrf(owner, csrf)
    try:
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise ValueError("Оберіть .xlsx-файл.")
        content = await file.read(5 * 1024 * 1024 + 1)
        prepared = name_dictionary_import.preview(db, content, mode)
        token = dictionary_previews.store(prepared, owner) if not prepared["errors"] else None
        return render(request, "admin/import_preview.html", owner, prepared=prepared, token=token)
    except ValueError as error:
        return render(request, "admin/error.html", owner, status=400, error=str(error))
    finally:
        await file.close()


@router.post("/dictionaries/import/confirm")
def import_confirm(request: Request, token: str = Form(""), csrf: str = Form(""),
                   reviewed: bool = Form(False), confirm_updates: bool = Form(False),
                   owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    check_csrf(owner, csrf)
    prepared = None
    try:
        prepared, key = dictionary_previews.load(token, owner)
        counts = name_dictionary_import.confirm(db, prepared, key, reviewed=reviewed, confirm_updates=confirm_updates)
        message = f"Імпорт завершено: нових {counts['new']}, оновлених {counts['updated']}, незмінених {counts['unchanged']}, пропущених {counts['skipped']}."
        return RedirectResponse("/admin?" + urlencode({"message": message}), 303)
    except ValueError as error:
        if prepared is not None:
            return render(request, "admin/import_preview.html", owner, status=409,
                          prepared=prepared, token=token, error=str(error))
        return render(request, "admin/error.html", owner, status=409, error=str(error))


@router.get("/dictionaries/new")
def new_dictionary(request: Request, kind: str = "surname", owner: str = Depends(require_admin)):
    if kind not in NAME_PARTS:
        raise HTTPException(400, "Невідомий словник.")
    return render(request, "admin/dictionary_form.html", owner, data={"kind": kind}, key=None)


@router.get("/dictionaries/{key}/edit")
def edit_dictionary(request: Request, key: int, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        record = name_cases.dictionary_record(db, key)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    data = {field: getattr(record, field) for field in (*IMPORT_HEADERS, "kind", "is_verified", "revision")}
    return render(request, "admin/dictionary_form.html", owner, data=data, key=key)


async def save_form(request, owner, db, key):
    form = await request.form()
    check_csrf(owner, form.get("csrf"))
    data = {field: str(form.get(field, "")) for field in (*IMPORT_HEADERS, "kind", "revision")}
    data["is_verified"] = form.get("is_verified") == "on"
    try:
        revision = int(data["revision"]) if key is not None else None
        name_cases.save_dictionary(db, data, key=key, revision=revision, verified=data["is_verified"])
        return RedirectResponse("/admin/dictionaries?" + urlencode({"kind": data["kind"]}), 303)
    except ValueError as error:
        return render(request, "admin/dictionary_form.html", owner, status=409, data=data, key=key, error=str(error))


@router.post("/dictionaries/new")
async def create_dictionary(request: Request, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    return await save_form(request, owner, db, None)


@router.post("/dictionaries/{key}/edit")
async def update_dictionary(request: Request, key: int, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    return await save_form(request, owner, db, key)
