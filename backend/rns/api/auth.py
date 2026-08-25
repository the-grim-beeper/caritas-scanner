"""One shared password, one signed cookie. Every /api route except /health and
/login depends on `require_session`."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from rns.config import settings

COOKIE = "rns_session"
router = APIRouter()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="rns-session")


def require_session(request: Request) -> str:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not signed in")
    try:
        return _serializer().loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired) as exc:
        raise HTTPException(status_code=401, detail="session invalid") from exc


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody, response: Response) -> dict:
    if body.password != settings.app_password:
        raise HTTPException(status_code=401, detail="wrong password")
    token = _serializer().dumps("reader")
    response.set_cookie(
        COOKIE, token, max_age=settings.session_max_age_seconds, httponly=True, samesite="lax",
        secure=settings.environment == "production",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/session")
def session(_: str = Depends(require_session)) -> dict:
    return {"ok": True}


AuthDep = Depends(require_session)
