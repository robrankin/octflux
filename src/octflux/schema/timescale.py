"""TimescaleDB support (Postgres only, optional).

The high-volume time-series tables are converted to hypertables partitioned on
their time column. This is a no-op unless the ``timescaledb`` extension is present,
so the same schema runs on plain Postgres, SQLite and MySQL. Each table's PK
already includes its time column (see ``tables.py``), which Timescale requires.

Low-volume / non-time-keyed tables (standing_charge, account_balance, octoplus,
ledger_transaction, statement) are intentionally left as regular tables -- mirrors
v1, where only octopus_consumption was a hypertable.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

# table -> (time column, chunk interval)
HYPERTABLES: dict[str, tuple[str, str]] = {
    "consumption": ("interval_start", "7 days"),
    "unit_rate": ("valid_from", "7 days"),
    "carbon_intensity": ("valid_from", "7 days"),
    "meter_reading": ("read_at", "30 days"),
    "dispatch": ("start_at", "7 days"),
    "fact_cost": ("interval_start", "7 days"),  # silver fact, also a hypertable
}


def has_timescale(conn) -> bool:
    """True if the timescaledb extension is installed (sync connection)."""
    row = conn.exec_driver_sql(
        "SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'"
    ).first()
    return row is not None


def create_hypertables(conn) -> list[str]:
    """Convert the configured tables to hypertables. Idempotent; no-op without
    Timescale. ``conn`` is a *sync* SQLAlchemy connection (works from the async
    sink via ``run_sync`` and from Alembic via ``op.get_bind()``)."""
    if conn.dialect.name != "postgresql":
        return []
    # Self-sufficient on the timescaledb image: ensure the extension exists.
    try:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS timescaledb")
    except Exception:  # not a Timescale build / no privilege -> plain Postgres
        log.info("timescaledb_extension_unavailable")
    if not has_timescale(conn):
        return []
    done = []
    for table, (column, interval) in HYPERTABLES.items():
        conn.exec_driver_sql(
            f"SELECT create_hypertable('{table}', '{column}', "
            f"chunk_time_interval => INTERVAL '{interval}', "
            f"if_not_exists => TRUE, migrate_data => TRUE)"
        )
        done.append(table)
    if done:
        log.info("hypertables_created", tables=done)
    return done
