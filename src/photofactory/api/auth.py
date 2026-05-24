"""Authentication helpers for API endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from photofactory.config import AppConfig

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: str


def create_access_token(config: AppConfig, username: str, role: str) -> str:
    expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=config.auth.token_ttl_minutes)
    payload = {
        "sub": username,
        "role": role,
        "exp": expires_at,
    }
    return jwt.encode(payload, config.auth.jwt_secret, algorithm="HS256")


def require_auth(config: AppConfig):
    def _dep(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> AuthUser:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
            )
        token = credentials.credentials
        try:
            payload = jwt.decode(token, config.auth.jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            ) from exc
        username = payload.get("sub")
        role = payload.get("role")
        if not username or role not in {"bild", "admin"}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return AuthUser(username=username, role=role)

    return _dep


def require_admin(config: AppConfig):
    base_dep = require_auth(config)

    def _dep(user: AuthUser = Depends(base_dep)) -> AuthUser:
        if user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        return user

    return _dep
