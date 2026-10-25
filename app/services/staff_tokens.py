"""Signed short-lived confirmations. No browser flag authorizes stale writes."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import time

_KEY=os.environ.get("STAFF_SIGNING_KEY","").encode() or secrets.token_bytes(32)
TTL=1200
PREVIEWS=Path(tempfile.gettempdir())/"project2-staff-previews"


def sign(payload, purpose):
    data=base64.urlsafe_b64encode(json.dumps({"purpose":purpose,"expires":int(time.time())+TTL,"payload":payload},separators=(",",":")).encode()).decode()
    return data+"."+hmac.new(_KEY,data.encode(),hashlib.sha256).hexdigest()


def verify(token,purpose):
    try:
        data,signature=token.split(".")
        if not hmac.compare_digest(signature,hmac.new(_KEY,data.encode(),hashlib.sha256).hexdigest()): raise ValueError()
        envelope=json.loads(base64.urlsafe_b64decode(data))
        if envelope["purpose"]!=purpose or envelope["expires"]<time.time(): raise ValueError()
        return envelope["payload"]
    except (ValueError,KeyError,TypeError):
        raise ValueError("Підтвердження недійсне або прострочене. Повторіть перевірку.") from None


def store_preview(prepared):
    PREVIEWS.mkdir(mode=0o700,exist_ok=True)
    for path in PREVIEWS.glob("*.json"):
        if path.stat().st_mtime<time.time()-TTL: path.unlink(missing_ok=True)
    key=secrets.token_hex(32)
    data=json.dumps(prepared,ensure_ascii=False).encode()
    path=PREVIEWS/(key+".json")
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,"wb") as target: target.write(data)
    return sign({"key":key,"digest":hashlib.sha256(data).hexdigest()},"import")


def load_preview(token):
    payload=verify(token,"import")
    if len(payload["key"])!=64 or any(char not in "0123456789abcdef" for char in payload["key"]): raise ValueError("Некоректне підтвердження.")
    try: data=(PREVIEWS/(payload["key"]+".json")).read_bytes()
    except OSError: raise ValueError("Попередній перегляд недоступний. Завантажте Excel повторно.") from None
    if hashlib.sha256(data).hexdigest()!=payload["digest"]: raise ValueError("Дані попереднього перегляду змінилися.")
    return json.loads(data),payload["key"]
