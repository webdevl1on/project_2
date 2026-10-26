"""Minimal opt-in admin access until the application has users and roles."""
import hashlib
import hmac
import os
import secrets
import time
from fastapi import HTTPException, Request

COOKIE = "project2_admin"
TTL = 8 * 60 * 60


def configured_token():
    token = os.environ.get("PROJECT2_ADMIN_TOKEN", "")
    return token if len(token) >= 32 else None


def allow_http():
    return os.environ.get("PROJECT2_ADMIN_ALLOW_HTTP") == "1"


def check_transport(request):
    if request.url.scheme != "https" and not allow_http():
        raise HTTPException(403, "Адміністративний доступ вимагає HTTPS. Для локальної розробки потрібне явне PROJECT2_ADMIN_ALLOW_HTTP=1.")


def signed(value, purpose):
    secret = configured_token()
    if not secret:
        raise HTTPException(503, "Адміністрування вимкнено: налаштуйте PROJECT2_ADMIN_TOKEN (щонайменше 32 символи).")
    signature = hmac.new(secret.encode(), (purpose + ":" + value).encode(), hashlib.sha256).hexdigest()
    return value + "." + signature


def new_session():
    return signed(f"{int(time.time()) + TTL}:{secrets.token_hex(32)}", "session")


def require_admin(request: Request):
    if configured_token() is None:
        raise HTTPException(503, "Адміністрування вимкнено: PROJECT2_ADMIN_TOKEN не налаштовано.")
    check_transport(request)
    cookie = request.cookies.get(COOKIE, "")
    try:
        value, signature = cookie.rsplit(".", 1)
        expires, nonce = value.split(":")
        if not hmac.compare_digest(cookie, signed(value, "session")) or int(expires) < time.time() or len(nonce) != 64:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(401, "Потрібен адміністративний вхід.") from None
    return nonce


def csrf_token(owner):
    return signed(owner, "csrf")


def check_csrf(owner, token):
    if not hmac.compare_digest(csrf_token(owner).encode(), (token or "").encode()):
        raise HTTPException(403, "Невірний CSRF-токен. Оновіть сторінку.")
