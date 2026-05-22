"""Postgres sink driver (async via psycopg v3)."""

from __future__ import annotations

from sqlalchemy import URL

from .base import SqlSink


def build(name: str, options: dict) -> SqlSink:
    if options.get("dsn"):
        url = options["dsn"]
    else:
        url = URL.create(
            "postgresql+psycopg",
            username=options.get("user"),
            password=options.get("password"),
            host=options.get("host"),
            port=options.get("port"),
            database=options.get("database"),
        )
    return SqlSink(
        name, url,
        auto_create=options.get("auto_create", False),
        retention_days=options.get("retention_days", 0),
    )
