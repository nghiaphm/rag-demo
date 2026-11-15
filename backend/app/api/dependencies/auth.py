"""FastAPI authentication and RBAC dependencies."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException

from app.shared.auth import AuthTokenError, UserContext, decode_token
from app.shared.config import settings


def get_current_user(
    authorization: str | None = Header(default=None),
) -> UserContext | None:
    """Resolve the current user from Bearer JWT when AUTH_ENABLED is true.

    Returns ``None`` when authentication is disabled so local/offline workflows
    and legacy tests continue operating without credentials.
    """
    if not settings.auth_enabled:
        return None

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Thiếu Bearer token xác thực.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token xác thực không hợp lệ.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return decode_token(
            token,
            secret=settings.jwt_secret_key.get_secret_value(),
            expected_type="access",
        )
    except AuthTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail="Token xác thực không hợp lệ hoặc đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_roles(*allowed_roles: str) -> Callable[[UserContext | None], UserContext | None]:
    """Dependency factory enforcing that an authenticated user holds at least one role."""

    def _checker(user: UserContext | None = Depends(get_current_user)) -> UserContext | None:
        if user is None:
            return None
        if "admin" in user.roles:
            return user
        if not (set(user.roles) & set(allowed_roles)):
            raise HTTPException(status_code=403, detail="Không đủ quyền thực hiện thao tác này.")
        return user

    return _checker
