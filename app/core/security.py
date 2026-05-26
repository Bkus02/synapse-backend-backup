"""
Synapse — parola özetleme (bcrypt) ve JWT token üretimi/doğrulaması.

Bu modül framework-agnostiktir; FastAPI bağımlılıkları `app/api/deps.py`
içindedir. Parolalar tek yön bcrypt ile özetlenir; tokenlar HS256 imzalı
JWT'dir ve `Settings.jwt_access_token_expire_minutes` süresince geçerlidir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.settings import settings


class TokenError(Exception):
    """JWT doğrulama / decode hatalarının tek tipi."""


# ---------------------------------------------------------------------------
# Parola özetleme
# ---------------------------------------------------------------------------


def hash_password(plain_password: str) -> str:
    """Düz parolayı bcrypt ile özetle (utf-8 string döner)."""
    if not isinstance(plain_password, str):
        raise TypeError("plain_password str olmalı")
    pw_bytes = plain_password.encode("utf-8")
    # bcrypt 72 byte üzeri parolayı sessizce keser; pratikte 72'den uzun
    # parolalar zaten alışılmadık, ama yine de uyarı amaçlı maks. uzunluk
    # uygulamaya bırakılmıştır.
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """Düz parola hash ile eşleşiyor mu? Hash boşsa False."""
    if not hashed_password:
        return False
    if not isinstance(plain_password, str) or not isinstance(hashed_password, str):
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # `hashed_password` bcrypt formatında değilse (örn. eski plain text
        # alanlar) checkpw `ValueError` fırlatır. Sessizce False döndür ki
        # legacy data güvenli biçimde reddedilsin.
        return False


def looks_like_bcrypt_hash(value: str | None) -> bool:
    """`$2a$` / `$2b$` / `$2y$` prefix kontrolü; opsiyonel migration için."""
    if not value or len(value) < 7:
        return False
    return value.startswith(("$2a$", "$2b$", "$2y$"))


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def create_access_token(
    subject: str,
    *,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """JWT access token üretir. `subject` genelde user.id'dir."""
    if not subject:
        raise ValueError("subject (user id) bos olamaz")
    expires_in = expires_minutes or settings.jwt_access_token_expire_minutes
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_in)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """JWT'yi doğrular ve payload'u döndürür; hata → `TokenError`."""
    if not token:
        raise TokenError("token bos")
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token suresi doldu") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("gecersiz token") from exc
