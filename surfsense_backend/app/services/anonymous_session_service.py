import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass

from app.config import config

logger = logging.getLogger(__name__)

ANON_SESSION_COOKIE_NAME = "surfsense_anon_session"

_signing_secret = config.SECRET_KEY
if not _signing_secret:
    _signing_secret = secrets.token_urlsafe(32)
    logger.warning(
        "SECRET_KEY is not set. Using ephemeral secret for anonymous sessions."
    )


@dataclass(frozen=True)
class AnonymousSession:
    session_id: str
    is_new: bool
    cookie_value: str


def _sign_session_id(session_id: str) -> str:
    signature = hmac.new(
        _signing_secret.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def _encode_cookie(session_id: str) -> str:
    signature = _sign_session_id(session_id)
    return f"{session_id}.{signature}"


def _decode_cookie(cookie_value: str | None) -> str | None:
    if not cookie_value:
        return None
    if "." not in cookie_value:
        return None
    session_id, signature = cookie_value.rsplit(".", 1)
    expected = _sign_session_id(session_id)
    if not hmac.compare_digest(signature, expected):
        return None
    return session_id


def get_or_create_anonymous_session(cookie_value: str | None) -> AnonymousSession:
    session_id = _decode_cookie(cookie_value)
    if session_id:
        return AnonymousSession(
            session_id=session_id,
            is_new=False,
            cookie_value=cookie_value or "",
        )

    new_session_id = secrets.token_urlsafe(16)
    encoded = _encode_cookie(new_session_id)
    return AnonymousSession(
        session_id=new_session_id,
        is_new=True,
        cookie_value=encoded,
    )
