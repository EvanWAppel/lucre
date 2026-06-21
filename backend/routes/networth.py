import logging
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from services.networth import networth_series, sparkline_points
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_login)])

DbSession = Annotated[Session, Depends(get_db)]

_CHART_WIDTH = 300
_CHART_HEIGHT = 60
_ALLOWED_RANGES = (30, 90, 365)


@router.get("/api/networth")
def networth_chart(request: Request, db: DbSession, days: int = 90):
    if days not in _ALLOWED_RANGES:
        days = 90
    today = date.today()
    series = networth_series(db, start=today - timedelta(days=days - 1), end=today)
    values = [value for _, value in series]
    coords = sparkline_points(values, width=_CHART_WIDTH, height=_CHART_HEIGHT)
    polyline = " ".join(f"{x},{y}" for x, y in coords)
    return templates.TemplateResponse(
        request,
        "_networth_chart.html",
        {
            "days": days,
            "ranges": _ALLOWED_RANGES,
            "polyline": polyline,
            "latest": values[-1] if values else None,
            "width": _CHART_WIDTH,
            "height": _CHART_HEIGHT,
        },
    )
