"""Silver + gold transforms.

Silver: ``refresh_silver`` recomputes the ``fact_cost`` table for a rolling window
by joining bronze ``consumption`` to the ``agreement`` in force and the matching
``unit_rate`` (cross-dialect SQLAlchemy Core; runs on SQLite and Postgres).

Gold: ``create_gold`` builds TimescaleDB continuous aggregates + compression +
(optional) retention. Postgres + timescaledb only; a no-op elsewhere.
"""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa
import structlog

from ..core.time import now_naive
from .tables import agreement, consumption, fact_cost, unit_rate
from .timescale import has_timescale

log = structlog.get_logger(__name__)

_FACT_COLS = [
    "account_number", "mpan", "serial_number", "fuel", "is_export",
    "interval_start", "interval_end", "consumption_kwh", "tariff_code",
    "unit_price_inc_vat", "cost_pence", "collected_at",
]


def refresh_silver(conn, window_days: int = 7) -> int:
    """Recompute fact_cost for the last ``window_days`` (delete window + reinsert).
    Returns the number of fact_cost rows for the window. Sync connection."""
    now = now_naive()
    start = now - timedelta(days=window_days)
    c, a, u, f = consumption, agreement, unit_rate, fact_cost

    conn.execute(sa.delete(f).where(f.c.interval_start >= start))

    joined = c.join(
        a,
        sa.and_(
            a.c.mpan == c.c.mpan, a.c.is_export == c.c.is_export,
            c.c.interval_start >= a.c.valid_from,
            sa.or_(a.c.valid_to.is_(None), c.c.interval_start < a.c.valid_to),
        ),
    ).join(
        u,
        sa.and_(
            u.c.tariff_code == a.c.tariff_code, u.c.is_export == c.c.is_export,
            c.c.interval_start >= u.c.valid_from,
            sa.or_(u.c.valid_to.is_(None), c.c.interval_start < u.c.valid_to),
        ),
    )
    sel = (
        sa.select(
            a.c.account_number, c.c.mpan, c.c.serial_number, c.c.fuel, c.c.is_export,
            c.c.interval_start, c.c.interval_end,
            c.c.consumption.label("consumption_kwh"),
            a.c.tariff_code, u.c.value_inc_vat.label("unit_price_inc_vat"),
            (c.c.consumption * u.c.value_inc_vat).label("cost_pence"),
            sa.literal(now).label("collected_at"),
        )
        .select_from(joined)
        .where(sa.and_(c.c.fuel == "electricity", c.c.interval_start >= start))
    )
    conn.execute(sa.insert(f).from_select(_FACT_COLS, sel))
    return conn.execute(
        sa.select(sa.func.count()).select_from(f).where(f.c.interval_start >= start)
    ).scalar_one()


# -- gold: TimescaleDB continuous aggregates + policies -----------------------

def _cagg_ddl(name: str, bucket: str, label: str, source: str, cols: str, group: str) -> str:
    return (
        f"CREATE MATERIALIZED VIEW IF NOT EXISTS {name} "
        f"WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS "
        f"SELECT time_bucket(INTERVAL '{bucket}', {source}) AS {label}, {cols} "
        f"FROM {{table}} GROUP BY {label}, {group} WITH NO DATA"
    )


_CONS_COLS = "mpan, serial_number, fuel, is_export, sum(consumption) AS kwh"
_CONS_GRP = "mpan, serial_number, fuel, is_export"
_COST_COLS = "account_number, mpan, is_export, sum(consumption_kwh) AS kwh, sum(cost_pence) AS cost_pence"
_COST_GRP = "account_number, mpan, is_export"

# Energy used per meter + energy cost per account, each at hour / day / month.
# name -> (ddl, start_offset, end_offset)
_CAGGS: dict[str, tuple[str, str, str]] = {
    "cagg_consumption_hourly": (
        _cagg_ddl("cagg_consumption_hourly", "1 hour", "hour", "interval_start",
                  _CONS_COLS, _CONS_GRP).format(table="consumption"), "30 days", "1 hour"),
    "cagg_consumption_daily": (
        _cagg_ddl("cagg_consumption_daily", "1 day", "day", "interval_start",
                  _CONS_COLS, _CONS_GRP).format(table="consumption"), "1 year", "1 hour"),
    "cagg_consumption_monthly": (
        _cagg_ddl("cagg_consumption_monthly", "1 month", "month", "interval_start",
                  _CONS_COLS, _CONS_GRP).format(table="consumption"), "5 years", "1 day"),
    "cagg_cost_hourly": (
        _cagg_ddl("cagg_cost_hourly", "1 hour", "hour", "interval_start",
                  _COST_COLS, _COST_GRP).format(table="fact_cost"), "30 days", "1 hour"),
    "cagg_cost_daily": (
        _cagg_ddl("cagg_cost_daily", "1 day", "day", "interval_start",
                  _COST_COLS, _COST_GRP).format(table="fact_cost"), "1 year", "1 hour"),
    "cagg_cost_monthly": (
        _cagg_ddl("cagg_cost_monthly", "1 month", "month", "interval_start",
                  _COST_COLS, _COST_GRP).format(table="fact_cost"), "5 years", "1 day"),
    "cagg_carbon_daily": (
        _cagg_ddl("cagg_carbon_daily", "1 day", "day", "valid_from",
                  "postcode, avg(intensity_gco2_kwh) AS avg_intensity", "postcode")
        .format(table="carbon_intensity"), "1 year", "1 hour"),
}

# Total bill (plain views over the daily cost cagg + standing charge):
#   net = energy import cost + standing charge - export earnings.
_BILL_DAILY = """
CREATE OR REPLACE VIEW bill_daily AS
WITH c AS (
    SELECT day, account_number,
           coalesce(sum(kwh)        FILTER (WHERE NOT is_export), 0) AS import_kwh,
           coalesce(sum(kwh)        FILTER (WHERE is_export),     0) AS export_kwh,
           coalesce(sum(cost_pence) FILTER (WHERE NOT is_export), 0) AS import_pence,
           coalesce(sum(cost_pence) FILTER (WHERE is_export),     0) AS export_pence
    FROM cagg_cost_daily GROUP BY day, account_number
)
SELECT c.day, c.account_number, c.import_kwh, c.export_kwh,
       c.import_pence, coalesce(s.value_inc_vat, 0) AS standing_pence, c.export_pence,
       c.import_pence + coalesce(s.value_inc_vat, 0) - c.export_pence AS net_pence
FROM c
LEFT JOIN LATERAL (
    SELECT value_inc_vat FROM standing_charge s
    WHERE c.day >= s.valid_from AND (s.valid_to IS NULL OR c.day < s.valid_to)
    ORDER BY s.valid_from DESC LIMIT 1
) s ON true
"""

_BILL_MONTHLY = """
CREATE OR REPLACE VIEW bill_monthly AS
SELECT time_bucket(INTERVAL '1 month', day) AS month, account_number,
       sum(import_kwh) AS import_kwh, sum(export_kwh) AS export_kwh,
       sum(import_pence) AS import_pence, sum(standing_pence) AS standing_pence,
       sum(export_pence) AS export_pence, sum(net_pence) AS net_pence
FROM bill_daily GROUP BY month, account_number
"""

# table -> (compress_orderby, compress_segmentby, compress_after)
# Every PRIMARY KEY column must appear in segmentby or orderby, or older
# TimescaleDB (<= 2.x) rejects the config ("cannot be enforced with the given
# compression configuration"). PK = (mpan, serial_number, fuel, is_export,
# interval_start); interval_start is the orderby, the rest segment the series.
_COMPRESS = {
    "consumption": ("interval_start DESC", "mpan, serial_number, fuel, is_export", "30 days"),
    "fact_cost":   ("interval_start DESC", "mpan, serial_number, fuel, is_export", "30 days"),
}


def create_gold(conn, *, retention_days: int = 0) -> list[str]:
    """Create continuous aggregates + compression (+ optional retention). No-op
    unless Postgres + TimescaleDB. ``conn`` must be autocommit (policies cannot
    run inside a transaction)."""
    if conn.dialect.name != "postgresql" or not has_timescale(conn):
        return []
    done: list[str] = []

    for name, (ddl, start_off, end_off) in _CAGGS.items():
        conn.exec_driver_sql(ddl)
        conn.exec_driver_sql(
            f"SELECT add_continuous_aggregate_policy('{name}', "
            f"start_offset => INTERVAL '{start_off}', end_offset => INTERVAL '{end_off}', "
            f"schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE)"
        )
        done.append(name)

    conn.exec_driver_sql(_BILL_DAILY)
    conn.exec_driver_sql(_BILL_MONTHLY)
    done += ["bill_daily", "bill_monthly"]

    for table, (orderby, segmentby, after) in _COMPRESS.items():
        conn.exec_driver_sql(
            f"ALTER TABLE {table} SET (timescaledb.compress, "
            f"timescaledb.compress_orderby = '{orderby}', "
            f"timescaledb.compress_segmentby = '{segmentby}')"
        )
        conn.exec_driver_sql(
            f"SELECT add_compression_policy('{table}', INTERVAL '{after}', if_not_exists => TRUE)"
        )
        done.append(f"compress:{table}")

    # Retention drops only the high-resolution raw/derived hypertables; the caggs
    # and the price/audit tables are kept forever. Reconciled every start so the
    # policy can be added, re-windowed, or removed (days=0 -> keep forever) by config
    # alone. Coerce the config value before interpolating it into SQL.
    days = int(retention_days)
    for table in ("consumption", "fact_cost"):
        conn.exec_driver_sql(f"SELECT remove_retention_policy('{table}', if_exists => TRUE)")
        if days > 0:
            conn.exec_driver_sql(
                f"SELECT add_retention_policy('{table}', INTERVAL '{days} days', if_not_exists => TRUE)"
            )
            done.append(f"retention:{table}={days}d")

    log.info("gold_created", objects=done)
    return done
