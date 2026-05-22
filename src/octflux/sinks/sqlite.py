"""SQLite sink driver -- builds an aiosqlite URL and hands it to the shared SqlSink."""

from __future__ import annotations

from .base import SqlSink


def build(name: str, options: dict) -> SqlSink:
    path = options.get("path", "octflux.db")
    return SqlSink(name, f"sqlite+aiosqlite:///{path}", auto_create=options.get("auto_create", True))
