"""
Synapse — FastAPI bağımlılıkları (auth).

Tipik kullanım:

    from fastapi import Depends
    from app.api.deps import current_user, current_user_id

    @router.get("/me")
    def me(user = Depends(current_user)):
        ...

Header: `Authorization: Bearer <jwt>`
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session

from app.core.models import User
from app.core.security import TokenError, decode_access_token
from app.db.database import get_session


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def current_user_id_optional(
    authorization: str | None = Header(default=None),
) -> str | None:
    """Token varsa user_id döndürür; yoksa None. Geri-uyumlu route'lar için."""
    token = _extract_bearer_token(authorization)
    if token is None:
        return None
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token icinde sub yok",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return sub


def current_user_id(
    user_id: str | None = Depends(current_user_id_optional),
) -> str:
    """Token zorunlu; eksikse 401."""
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization Bearer token gerekli",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


def current_user(
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> User:
    """Token + DB'de hala mevcut kullanıcı."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="kullanici bulunamadi",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def resolve_effective_user_id(
    requested_user_id: str | None,
    token_user_id: str | None,
) -> str:
    """
    Token + opsiyonel query/body `user_id` çakışmasını tek noktada yönet:
    - Token varsa: token kazanır. requested farklıysa 403.
    - Token yoksa: requested varsa onu kullan (geri uyum).
    - İkisi de yoksa: 401.

    Sprint B'de yalnızca seçilmiş hassas route'larda kullanılır; Sprint F'de
    tüm route'lara yayılacaktır.
    """
    if token_user_id:
        if requested_user_id and requested_user_id != token_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token ile istenen user_id eslesmiyor",
            )
        return token_user_id
    if requested_user_id:
        return requested_user_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik dogrulama gerekli (Bearer token veya user_id)",
        headers={"WWW-Authenticate": "Bearer"},
    )
