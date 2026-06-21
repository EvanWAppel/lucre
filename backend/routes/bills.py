import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from models import Bill
from services.bills import upcoming_bills, upcoming_total
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_login)])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/bills")
def bills_page(request: Request, db: DbSession):
    today = date.today()
    upcoming = upcoming_bills(db, today)
    manual = db.query(Bill).filter(Bill.recurring_series_id.is_(None)).all()
    return templates.TemplateResponse(
        request,
        "bills.html",
        {"upcoming": upcoming, "total": upcoming_total(upcoming), "manual": manual},
    )


@router.get("/bills/new")
def new_bill_form(request: Request):
    return templates.TemplateResponse(request, "bill_form.html", {"bill": None})


@router.post("/bills/new")
def create_bill(
    name: Annotated[str, Form()],
    amount: Annotated[float, Form()],
    cadence: Annotated[str, Form()],
    next_due: Annotated[date, Form()],
    db: DbSession,
    due_day_override: Annotated[int | None, Form()] = None,
    autopay: Annotated[bool, Form()] = False,
):
    bill = Bill(
        name=name,
        amount=amount,
        cadence=cadence,
        next_due=next_due,
        due_day_override=due_day_override,
        autopay=autopay,
    )
    db.add(bill)
    db.commit()
    logger.info("Created manual bill %s (%s)", bill.id, name)
    return RedirectResponse("/bills", status_code=303)


@router.get("/bills/{bill_id}/edit")
def edit_bill_form(request: Request, bill_id: int, db: DbSession):
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    return templates.TemplateResponse(request, "bill_form.html", {"bill": bill})


@router.post("/bills/{bill_id}/edit")
def update_bill(
    bill_id: int,
    db: DbSession,
    due_day_override: Annotated[int | None, Form()] = None,
    autopay: Annotated[bool, Form()] = False,
    name: Annotated[str | None, Form()] = None,
    amount: Annotated[float | None, Form()] = None,
    cadence: Annotated[str | None, Form()] = None,
    next_due: Annotated[date | None, Form()] = None,
):
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    # Overrides apply to any bill; the manual descriptor fields only to manual bills
    # (derived bills source those from their series).
    bill.due_day_override = due_day_override
    bill.autopay = autopay
    if not bill.is_derived:
        if name is not None:
            bill.name = name
        if amount is not None:
            bill.amount = amount
        if cadence is not None:
            bill.cadence = cadence
        if next_due is not None:
            bill.next_due = next_due
    db.commit()
    logger.info("Updated bill %s", bill_id)
    return RedirectResponse("/bills", status_code=303)


@router.post("/bills/{bill_id}/delete")
def delete_bill(bill_id: int, db: DbSession):
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.is_derived:
        raise HTTPException(
            status_code=400,
            detail="Derived bills follow their subscription; dismiss the subscription instead.",
        )
    db.delete(bill)
    db.commit()
    logger.info("Deleted manual bill %s", bill_id)
    return RedirectResponse("/bills", status_code=303)
