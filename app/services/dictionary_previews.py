"""Short-lived private previews bound to the authenticated admin session."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
from app.services.staff_tokens import sign, verify, TTL

DIRECTORY = Path(tempfile.gettempdir()) / "project2-name-dictionary-previews"
PURPOSE = "name-dictionary-import"


def store(prepared, owner):
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    for path in DIRECTORY.glob("*.json"):
        if path.stat().st_mtime < time.time() - TTL:
            path.unlink(missing_ok=True)
    key = secrets.token_hex(32)
    content = json.dumps(prepared, ensure_ascii=False).encode()
    descriptor = os.open(DIRECTORY / (key + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(content)
    return sign({"key": key, "digest": hashlib.sha256(content).hexdigest(), "owner": owner}, PURPOSE)


def load(token, owner):
    payload = verify(token, PURPOSE)
    key = payload.get("key", "")
    if payload.get("owner") != owner or len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
        raise ValueError("Попередній перегляд належить іншій адміністративній сесії.")
    try:
        content = (DIRECTORY / (key + ".json")).read_bytes()
    except OSError as error:
        raise ValueError("Попередній перегляд недоступний. Завантажте Excel повторно.") from error
    if hashlib.sha256(content).hexdigest() != payload["digest"]:
        raise ValueError("Попередній перегляд змінено. Завантажте Excel повторно.")
    return json.loads(content), key
