import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    login_rate_limiter,
    session_token_valid,
    verify_password,
)
from config import settings
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token and session_token_valid(token):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html")


@router.post("/login")
def login(request: Request, password: Annotated[str, Form()]):
    if login_rate_limiter.is_locked():
        logger.warning("Login attempt while locked out")
        raise HTTPException(status_code=429, detail="Too many failed attempts; try again later.")
    if not verify_password(password, settings.app_password_hash):
        login_rate_limiter.record_failure()
        logger.warning("Failed login attempt")
        return templates.TemplateResponse(
            request, "login.html", {"error": "Wrong password"}, status_code=401
        )
    login_rate_limiter.reset()
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
