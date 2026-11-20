"""Authentication, JWT, PBKDF2 password hashing, and RBAC helpers.

Self-contained in ``app.shared`` using Python stdlib cryptography primitives so
every layer can enforce RBAC without external SDK dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    """Supported RBAC roles."""

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class AuthTokenError(ValueError):
    """Raised when a JWT is malformed, expired, or has an invalid signature."""


class UserContext(BaseModel):
    """Authenticated principal attached to a request."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    roles: tuple[str, ...] = (UserRole.VIEWER.value,)
    tenant_id: str = Field(default="default", min_length=1, max_length=64)
    is_authenticated: bool = True


class UserRecord(BaseModel):
    """MongoDB persistence record for registered users."""

    model_config = ConfigDict(populate_by_name=True, validate_default=True)

    user_id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    username: str = Field(min_length=3, max_length=64)
    password_hash: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=lambda: [UserRole.VIEWER.value])
    tenant_id: str = Field(default="default", min_length=1, max_length=64)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="python", by_alias=True)


def hash_password(password: str, *, iterations: int = 120_000) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random 16-byte salt."""
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification of a password against a stored PBKDF2 hash."""
    try:
        scheme, iter_str, salt, expected_hex = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        actual_hex = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(actual_hex, expected_hex)
    except Exception:
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _encode_jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def create_access_token(
    *,
    user_id: str,
    username: str,
    roles: Sequence[str],
    secret: str,
    expires_minutes: int = 30,
    tenant_id: str = "default",
) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "roles": list(roles),
        "tenant_id": tenant_id,
        "type": "access",
        "iat": now,
        "exp": now + max(1, expires_minutes) * 60,
    }
    return _encode_jwt(payload, secret)


def create_refresh_token(
    *,
    user_id: str,
    username: str,
    roles: Sequence[str],
    secret: str,
    expires_minutes: int = 60 * 24 * 7,
    tenant_id: str = "default",
) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "roles": list(roles),
        "tenant_id": tenant_id,
        "type": "refresh",
        "iat": now,
        "exp": now + max(1, expires_minutes) * 60,
    }
    return _encode_jwt(payload, secret)


def decode_token(
    token: str,
    *,
    secret: str,
    expected_type: str = "access",
    default_tenant_id: str = "default",
) -> UserContext:
    """Validate HS256 signature, expiration, and token type."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthTokenError("Malformed token")
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(actual_sig, expected_sig):
            raise AuthTokenError("Invalid signature")
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if payload.get("type") != expected_type:
            raise AuthTokenError("Invalid token type")
        if int(payload.get("exp", 0)) < int(time.time()):
            raise AuthTokenError("Token expired")
        user_id = str(payload["sub"])
        username = str(payload["username"])
        roles = tuple(str(r) for r in payload.get("roles", ()))
        tenant_id = (
            str(payload.get("tenant_id") or default_tenant_id).strip()
            or default_tenant_id
        )
        return UserContext(
            user_id=user_id,
            username=username,
            roles=roles or (UserRole.VIEWER.value,),
            tenant_id=tenant_id,
        )
    except AuthTokenError:
        raise
    except Exception as exc:
        raise AuthTokenError("Invalid token") from exc


def can_access_resource(
    *,
    user: UserContext | None,
    owner_id: str | None,
    allowed_roles: Sequence[str] | None,
) -> bool:
    """Enforce RBAC + ownership access check (IDOR protection)."""
    if user is None:
        return True
    if UserRole.ADMIN.value in user.roles:
        return True
    if owner_id is not None and owner_id == user.user_id:
        return True
    if not allowed_roles:
        return True
    return bool(set(user.roles) & set(allowed_roles))
