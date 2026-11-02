"""Read-only event views; writes continue through the existing person-event API."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import event_views
from app.templating import templates

router = APIRouter(tags=['Event journal'])


def data(db, raw):
    try: return event_views.journal(db, raw)
    except ValueError as error: raise HTTPException(422, str(error)) from error


@router.get('/events')
def journal(request: Request, db: Session = Depends(get_db)):
    model = data(db, request.query_params)
    return templates.TemplateResponse(request=request, name='event_journal.html',
                                      context={'journal': model, 'event_legend': model['legend']},
                                      headers={'Cache-Control': 'no-store'})


@router.get('/events/data')
def journal_data(request: Request, db: Session = Depends(get_db)):
    return JSONResponse(data(db, request.query_params), headers={'Cache-Control': 'no-store'})


@router.get('/events/presence')
def presence(person_id: int, on: date, db: Session = Depends(get_db)):
    return JSONResponse(event_views.presence_for_people(db, [person_id], on)[person_id], headers={'Cache-Control': 'no-store'})
