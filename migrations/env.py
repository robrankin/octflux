"""Alembic environment. Migrations run with a *sync* engine; the URL comes from
$OCTFLUX_DB_URL so the same migrations apply to SQLite, Postgres or MySQL."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

from octflux.schema.tables import metadata

target_metadata = metadata


def _url() -> str:
    url = os.environ.get("OCTFLUX_DB_URL") or context.config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("set OCTFLUX_DB_URL (a sync SQLAlchemy URL) to run migrations")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
