"""Database engine/session helpers."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from photofactory.config import AppConfig


def build_engine(config: AppConfig):
    return create_engine(config.database.url, pool_pre_ping=True)


def build_session_factory(config: AppConfig) -> sessionmaker[Session]:
    engine = build_engine(config)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
