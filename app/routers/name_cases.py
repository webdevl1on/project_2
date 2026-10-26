"""Public read-only dictionary lookup and edits of a specific name snapshot."""
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database.db import get_db
from app.name_cases import CASES, NAME_PARTS, SEXES
from app.services import name_cases
from app.templating import templates

router = APIRouter()


@router.get("/name-dictionaries/lookup")
def dictionary_lookup(kind: str, sex: str, word: str = Query(max_length=100), db: Session = Depends(get_db)):
    try:
        return JSONResponse(name_cases.lookup(db, kind, word, sex), headers={"Cache-Control": "no-store"})
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


def render_personal(request, db, name_id, data=None, error=None, status=200):
    try:
        record, person, resolved, saved_data = name_cases.personal_page(db, name_id)
    except ValueError as missing:
        raise HTTPException(404, str(missing)) from missing
    return templates.TemplateResponse(request=request, name="person_name_cases.html", status_code=status,
        context={"record": record, "person": person, "resolved": resolved,
                 "form_data": data if data is not None else saved_data, "error": str(error) if error else None,
                 "error_fields": getattr(error, "fields", []), "parts": NAME_PARTS, "cases": CASES, "sexes": SEXES})


@router.get("/person_name/{name_id}/cases")
def personal_cases(request: Request, name_id: int, db: Session = Depends(get_db)):
    return render_personal(request, db, name_id)


@router.post("/person_name/{name_id}/cases")
async def update_personal_cases(request: Request, name_id: int, db: Session = Depends(get_db)):
    data = dict(await request.form())
    try:
        person_id = name_cases.update_personal(db, name_id, data)
        return RedirectResponse(f"/person_full_info/{person_id}", 303)
    except ValueError as error:
        return render_personal(request, db, name_id, data, error, 400)
    except SQLAlchemyError:
        return render_personal(request, db, name_id, data, ValueError("Збереження відхилено. Введені значення залишилися у формі."), 409)
