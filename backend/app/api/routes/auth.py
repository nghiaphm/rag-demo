"""Authentication routes: register, login, refresh, and current user profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.api.dependencies.auth import get_current_user
from app.shared.auth import (
    AuthTokenError,
    UserContext,
    UserRecord,
    UserRole,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.shared.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    roles: list[UserRole] = Field(default_factory=lambda: [UserRole.VIEWER])


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    roles: list[str]


def _users_collection(request: Request):
    cloud = getattr(request.app.state, "cloud_connections", None)
    database = getattr(getattr(cloud, "mongodb", None), "database", None)
    if database is None:
        raise HTTPException(status_code=503, detail="Database chưa sẵn sàng.")
    return database["users"]


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request) -> TokenResponse:
    users = _users_collection(request)
    existing = await run_in_threadpool(users.find_one, {"username": payload.username})
    if existing is not None:
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.")

    record = UserRecord(
        username=payload.username,
        password_hash=hash_password(payload.password),
        roles=[r.value for r in payload.roles],
    )
    await run_in_threadpool(users.insert_one, record.to_mongo())

    secret = settings.jwt_secret_key.get_secret_value()
    access = create_access_token(
        user_id=record.user_id,
        username=record.username,
        roles=record.roles,
        secret=secret,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    refresh = create_refresh_token(
        user_id=record.user_id,
        username=record.username,
        roles=record.roles,
        secret=secret,
        expires_minutes=settings.jwt_refresh_token_expire_minutes,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=record.user_id,
        username=record.username,
        roles=record.roles,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request) -> TokenResponse:
    users = _users_collection(request)
    doc = await run_in_threadpool(users.find_one, {"username": payload.username})
    if doc is None or not verify_password(payload.password, str(doc.get("password_hash", ""))):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu.")
    if not doc.get("is_active", True):
        raise HTTPException(status_code=403, detail="Tài khoản đã bị vô hiệu hóa.")

    user_id = str(doc["_id"])
    username = str(doc["username"])
    roles = [str(r) for r in doc.get("roles", [UserRole.VIEWER.value])]
    secret = settings.jwt_secret_key.get_secret_value()
    return TokenResponse(
        access_token=create_access_token(
            user_id=user_id,
            username=username,
            roles=roles,
            secret=secret,
            expires_minutes=settings.jwt_access_token_expire_minutes,
        ),
        refresh_token=create_refresh_token(
            user_id=user_id,
            username=username,
            roles=roles,
            secret=secret,
            expires_minutes=settings.jwt_refresh_token_expire_minutes,
        ),
        user_id=user_id,
        username=username,
        roles=roles,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest) -> TokenResponse:
    secret = settings.jwt_secret_key.get_secret_value()
    try:
        user = decode_token(payload.refresh_token, secret=secret, expected_type="refresh")
    except AuthTokenError as exc:
        raise HTTPException(status_code=401, detail="Refresh token không hợp lệ.") from exc

    return TokenResponse(
        access_token=create_access_token(
            user_id=user.user_id,
            username=user.username,
            roles=user.roles,
            secret=secret,
            expires_minutes=settings.jwt_access_token_expire_minutes,
        ),
        refresh_token=payload.refresh_token,
        user_id=user.user_id,
        username=user.username,
        roles=list(user.roles),
    )


@router.get("/me")
async def me(current_user: UserContext | None = Depends(get_current_user)) -> dict:
    if current_user is None:
        return {"authenticated": False, "auth_enabled": False}
    return {
        "authenticated": True,
        "auth_enabled": True,
        "user_id": current_user.user_id,
        "username": current_user.username,
        "roles": list(current_user.roles),
    }
