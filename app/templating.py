"""Shared Jinja setup; routers do not import each other for templates."""
from fastapi.templating import Jinja2Templates
from app.date_fields import BIRTH_DATE, DATE_FIELDS
from app.utils.date_utils import register_date_globals

templates = Jinja2Templates(directory="app/templates")
register_date_globals(templates.env)
templates.env.globals["birth_date_field"] = BIRTH_DATE.metadata()
templates.env.globals["rank_order_date_field"] = DATE_FIELDS["rank.rank_order_date"].metadata()
