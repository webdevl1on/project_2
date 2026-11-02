"""HTTP adapter for the existing staff-workflow access mode; no ORM queries."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database.db import get_db
from app.security.accounts import check_origin, COOKIE
from app.services import accounts
from app.services import person_events as service
from app.services.service_for_person_event import EventValidationError

router = APIRouter(prefix='/persons/{person_id}/events', tags=['Person events'])


@router.get('')
def listing(person_id: int, db: Session = Depends(get_db)):
    try:
        return JSONResponse(service.page(db, person_id), headers={'Cache-Control': 'no-store'})
    except ValueError as error:
        return JSONResponse({'detail': str(error)}, status_code=404)


@router.post('')
@router.post('/{key:int}')
@router.post('/{key:int}/annul')
async def save(request: Request, person_id: int, key: int | None = None, db: Session = Depends(get_db)):
    check_origin(request)
    actor_id = None
    try:
        actor_id = accounts.authenticate(db, request.cookies.get(COOKIE, ''))[0].id
    except PermissionError:
        pass
    try:
        data = dict(await request.form())
        event_id = service.annul(db, person_id, key, data, actor_id=actor_id) if request.url.path.endswith('/annul') else service.save(db, person_id, data, key, actor_id=actor_id)
        return {'ok': True, 'event_id': event_id, 'message': 'Подію анульовано.' if request.url.path.endswith('/annul') else 'Подію збережено.'}
    except service.EventConflictError as error:
        return JSONResponse({'detail': str(error), 'field': error.field, 'conflicts': error.conflicts}, status_code=409)
    except (EventValidationError, ValueError) as error:
        return JSONResponse({'detail': str(error), 'field': getattr(error, 'field', None)}, status_code=422)
    except SQLAlchemyError:
        return JSONResponse({'detail': 'База даних відхилила збереження. Дані не змінено; оновіть список і повторіть спробу.'}, status_code=409)
