"""Geography HTTP adapter; no SQL or business decisions."""
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import geography
from app.templating import templates
router = APIRouter()

@router.get('/geography/search')
def search(kind: str, q: str = '', parent_id: int | None = None, db: Session = Depends(get_db)):
    try:
        return geography.suggestions(db, kind, q, parent_id)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error

@router.post('/persons/{person_id}/geography/{block}')
async def save(request: Request, person_id: int, block: str, db: Session = Depends(get_db)):
    form = dict(await request.form())
    try:
        warnings = geography.save(db, person_id, block, form)
    except ValueError as error:
        context = geography.page(db, person_id)
        context.update(geo_draft=form, geo_error=str(error), geo_edit_block=block)
        return templates.TemplateResponse(request=request, name='person/components/geography.html', context=context, status_code=400)
    return templates.TemplateResponse(request=request, name='person/components/geography.html',
        context={**geography.page(db, person_id), 'geo_message': 'Збережено.', 'geo_warnings': warnings, 'geo_edit_block': block})
