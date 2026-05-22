"""Authentication helpers for API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from photofactory.config import AppConfig

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(config: AppConfig, username: str) -> str:
    expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=config.auth.token_ttl_minutes)
    payload = {
        "sub": username,
        "exp": expires_at,
    }
    return jwt.encode(payload, config.auth.jwt_secret, algorithm="HS256")


def require_auth(config: AppConfig):
    def _dep(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> str:
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
        if username != config.auth.username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            )
        return username

    return _dep
