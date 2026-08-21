from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.person_military_service import PersonRank
from app.services.service_common_person_func import CommonPersonFunc