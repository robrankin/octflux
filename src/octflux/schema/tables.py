"""Dialect-agnostic table definitions (SQLAlchemy Core).

One ``MetaData`` drives both the runtime sinks and Alembic migrations, so the
schema is defined once and works on Postgres, SQLite and MySQL. Every table's
PRIMARY KEY is its natural key (no surrogate id) -- required so the time-series
tables can become TimescaleDB hypertables -- plus a ``collected_at`` bookkeeping
column (set by the sink, excluded from change-detection).
"""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()


def _table(name: str, *cols: sa.Column, key: tuple[str, ...]) -> sa.Table:
    # The natural key is the PRIMARY KEY (no surrogate id). For the time-series
    # tables the key includes a time column, which is what lets them become
    # TimescaleDB hypertables (see schema/timescale.py) -- a hypertable's PK/unique
    # index MUST contain the partitioning column.
    return sa.Table(
        name,
        metadata,
        *cols,
        sa.Column("collected_at", _DT, nullable=False),
        sa.PrimaryKeyConstraint(*key, name=f"pk_{name}"),
    )


# Stored naive, always UTC. tz-aware columns round-trip inconsistently across
# SQLite/MySQL, which breaks natural-key lookups; the sink normalises to naive UTC.
_DT = sa.DateTime(timezone=False)
_RATE = sa.Numeric(14, 6)

unit_rate = _table(
    "unit_rate",
    sa.Column("tariff_code", sa.String(64), nullable=False),
    sa.Column("product_code", sa.String(64)),
    sa.Column("is_export", sa.Boolean, nullable=False),
    sa.Column("valid_from", _DT, nullable=False),
    sa.Column("valid_to", _DT),
    sa.Column("value_exc_vat", _RATE),
    sa.Column("value_inc_vat", _RATE),
    key=("tariff_code", "is_export", "valid_from"),
)

standing_charge = _table(
    "standing_charge",
    sa.Column("tariff_code", sa.String(64), nullable=False),
    sa.Column("product_code", sa.String(64)),
    sa.Column("valid_from", _DT, nullable=False),
    sa.Column("valid_to", _DT),
    sa.Column("value_exc_vat", _RATE),
    sa.Column("value_inc_vat", _RATE),
    key=("tariff_code", "valid_from"),
)

consumption = _table(
    "consumption",
    sa.Column("mpan", sa.String(32), nullable=False),
    sa.Column("serial_number", sa.String(32), nullable=False),
    sa.Column("fuel", sa.String(16), nullable=False),
    sa.Column("is_export", sa.Boolean, nullable=False),
    sa.Column("interval_start", _DT, nullable=False),
    sa.Column("interval_end", _DT, nullable=False),
    sa.Column("consumption", sa.Float),
    key=("mpan", "serial_number", "fuel", "is_export", "interval_start"),
)

account_balance = _table(
    "account_balance",
    sa.Column("account_number", sa.String(32), nullable=False),
    sa.Column("queried_at", _DT, nullable=False),
    sa.Column("balance_pennies", sa.BigInteger, nullable=False),
    key=("account_number", "queried_at"),
)

ledger_transaction = _table(
    "ledger_transaction",
    sa.Column("transaction_id", sa.String(64), nullable=False),
    sa.Column("account_number", sa.String(32), nullable=False),
    sa.Column("posted_date", sa.Date),
    sa.Column("created_at", _DT),
    sa.Column("amount_pennies", sa.BigInteger, nullable=False),
    sa.Column("balance_carried_forward_pennies", sa.BigInteger),
    sa.Column("is_credit", sa.Boolean),
    sa.Column("title", sa.String(255)),
    sa.Column("transaction_type", sa.String(64)),
    key=("transaction_id",),
)

dispatch = _table(
    "dispatch",
    sa.Column("account_number", sa.String(32), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("start_at", _DT, nullable=False),
    sa.Column("end_at", _DT, nullable=False),
    sa.Column("delta_kwh", sa.Float),
    sa.Column("source", sa.String(64)),
    sa.Column("location", sa.String(64)),
    key=("account_number", "status", "start_at"),
)

carbon_intensity = _table(
    "carbon_intensity",
    sa.Column("postcode", sa.String(16), nullable=False),
    sa.Column("valid_from", _DT, nullable=False),
    sa.Column("valid_to", _DT),
    sa.Column("intensity_gco2_kwh", sa.Float),
    sa.Column("intensity_index", sa.String(32)),
    key=("postcode", "valid_from"),
)

statement = _table(
    "statement",
    sa.Column("account_number", sa.String(32), nullable=False),
    sa.Column("statement_id", sa.String(64), nullable=False),
    sa.Column("from_date", sa.Date),
    sa.Column("to_date", sa.Date),
    sa.Column("issued_date", sa.Date),
    sa.Column("total_pennies", sa.BigInteger),
    key=("account_number", "statement_id"),
)

meter_reading = _table(
    "meter_reading",
    sa.Column("account_number", sa.String(32), nullable=False),
    sa.Column("meter_id", sa.String(32), nullable=False),
    sa.Column("fuel", sa.String(16), nullable=False),
    sa.Column("read_at", _DT, nullable=False),
    sa.Column("register", sa.String(64), nullable=False),
    sa.Column("value", sa.Float, nullable=False),
    sa.Column("source", sa.String(64)),
    key=("account_number", "meter_id", "read_at", "register"),
)

octoplus = _table(
    "octoplus",
    sa.Column("account_number", sa.String(32), nullable=False),
    sa.Column("queried_at", _DT, nullable=False),
    sa.Column("is_enrolled", sa.Boolean),
    sa.Column("enrollment_status", sa.String(32)),
    key=("account_number", "queried_at"),
)

agreement = _table(
    "agreement",
    sa.Column("account_number", sa.String(32), nullable=False),
    sa.Column("mpan", sa.String(32), nullable=False),
    sa.Column("fuel", sa.String(16), nullable=False),
    sa.Column("is_export", sa.Boolean, nullable=False),
    sa.Column("tariff_code", sa.String(64), nullable=False),
    sa.Column("product_code", sa.String(64)),
    sa.Column("valid_from", _DT, nullable=False),
    sa.Column("valid_to", _DT),
    key=("mpan", "is_export", "tariff_code", "valid_from"),
)

# -- silver: conformed dimensions + the costed fact --------------------------

dim_meter = _table(
    "dim_meter",
    sa.Column("mpan", sa.String(32), nullable=False),
    sa.Column("serial_number", sa.String(32), nullable=False),
    sa.Column("fuel", sa.String(16), nullable=False),
    sa.Column("is_export", sa.Boolean, nullable=False),
    sa.Column("meter_id", sa.String(32)),
    key=("mpan", "serial_number", "fuel", "is_export"),
)

dim_tariff = _table(
    "dim_tariff",
    sa.Column("tariff_code", sa.String(64), nullable=False),
    sa.Column("product_code", sa.String(64)),
    sa.Column("fuel", sa.String(16)),
    key=("tariff_code",),
)

fact_cost = _table(
    "fact_cost",
    sa.Column("account_number", sa.String(32), nullable=False),
    sa.Column("mpan", sa.String(32), nullable=False),
    sa.Column("serial_number", sa.String(32), nullable=False),
    sa.Column("fuel", sa.String(16), nullable=False),
    sa.Column("is_export", sa.Boolean, nullable=False),
    sa.Column("interval_start", _DT, nullable=False),
    sa.Column("interval_end", _DT, nullable=False),
    sa.Column("consumption_kwh", sa.Float),
    sa.Column("tariff_code", sa.String(64)),
    sa.Column("unit_price_inc_vat", _RATE),
    sa.Column("cost_pence", sa.Float),
    key=("mpan", "serial_number", "fuel", "is_export", "interval_start"),
)
