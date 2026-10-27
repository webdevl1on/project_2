"""Minimal opt-in admin access until the application has users and roles."""
import hashlib
import hmac
from ipaddress import ip_address
import os
import secrets
import time
from fastapi import HTTPException, Request

COOKIE = "project2_admin"
TTL = 8 * 60 * 60


class _LocalDevOwner(str):
    """Request-authorized local development identity, never read from a cookie."""


_DEV_OWNER = _LocalDevOwner(secrets.token_hex(32))


def dev_admin_open(request: Request):
    """Explicit development opt-in for direct loopback connections only."""
    if os.environ.get("PROJECT2_DEV_ADMIN_OPEN") != "1":
        return False
    if not request.client:
        return False
    try:
        peer_is_local = ip_address(request.client.host).is_loopback
    except ValueError:
        return False
    host = request.url.hostname
    if not peer_is_local or host not in {"localhost", "127.0.0.1", "::1"}:
        return False
    # A forwarded address must never authorize a remote caller as local.
    if any(key == "forwarded" or key.startswith("x-forwarded-") or key == "x-real-ip"
           for key in request.headers):
        return False
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        return False
    return request.headers.get("sec-fetch-site") != "cross-site"


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
    if dev_admin_open(request):
        return _DEV_OWNER
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
    if isinstance(owner, _LocalDevOwner):
        return ""
    return signed(owner, "csrf")


def check_csrf(owner, token):
    if isinstance(owner, _LocalDevOwner):
        return
    if not hmac.compare_digest(csrf_token(owner).encode(), (token or "").encode()):
        raise HTTPException(403, "Невірний CSRF-токен. Оновіть сторінку.")
