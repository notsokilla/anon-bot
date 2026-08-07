"""Подписанный токен для ленда.

Формат: base64url(json).hmac_sha256_hex
payload: {"m": message_id, "s": sender_id, "c": 0|1 (согласие на раскрытие), "u": recipient_id}
Ленд валидирует подпись тем же TOKEN_SECRET и после оплаты:
 - если c=1 — показывает отправителя (s),
 - если c=0 — показывает "отправитель остался анонимным".
"""
import base64
import hashlib
import hmac
import json

from ..config import settings


def sign_token(payload: dict) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    sig = hmac.new(settings.token_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(settings.token_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return json.loads(base64.urlsafe_b64decode(body))
    except Exception:
        return None