"""Service-basis forms and read-only, advisory TCC suggestions."""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import service_bases, tcc_directory

router = APIRouter()


@router.post('/persons/{person_id}/service-bases')
@router.post('/persons/{person_id}/service-bases/{key}')
async def save_basis(request: Request, person_id: int, key: int | None = None, db: Session = Depends(get_db)):
    try:
        key = service_bases.save(db, person_id, dict(await request.form()), key)
        return {'ok': True, 'id': key}
    except ValueError as error:
        return JSONResponse({'detail': str(error)}, status_code=409)


@router.get('/tcc/suggestions')
def suggestions(q: str = '', region: str = '', settlement: str = '', db: Session = Depends(get_db)):
    try:
        if max(len(q), len(region), len(settlement)) > 250:
            raise ValueError('Пошук: максимум 250 символів.')
        return {'offices': tcc_directory.suggestions(db, q, region, settlement)}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get('/tcc/locations')
def locations(db: Session = Depends(get_db)):
    return tcc_directory.locations(db)
