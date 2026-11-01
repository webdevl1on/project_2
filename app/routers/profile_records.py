"""HTTP adapter; no ORM queries or personnel decisions."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.security.accounts import current_user
from app.routers.documents import payload, failure
from app.services import profile_records as service

router = APIRouter(prefix='/persons/{person_id}/profile-records', tags=['Additional profile records'])


@router.get('/{kind}')
def listing(person_id: int, kind: str, user=Depends(current_user), db: Session=Depends(get_db)):
    try:
        return JSONResponse(service.page(db, user.id, person_id, kind), headers={'Cache-Control':'no-store'})
    except (ValueError, PermissionError) as error:
        return failure(error)


@router.post('/{kind}')
@router.post('/{kind}/{key:int}')
async def save(request: Request, person_id: int, kind: str, key: int | None=None,
               user=Depends(current_user), db: Session=Depends(get_db)):
    data = await payload(request)
    try:
        return {'ok': True, **service.save(db, user.id, person_id, kind, data.get('fields'),
                                          key=key, revision=data.get('revision'))}
    except (ValueError, PermissionError) as error:
        return failure(error)
