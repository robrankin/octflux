"""v1-compatibility views.

Present octflux's tables under the old v1 ``octopus_*`` names/columns (notably
``fuel`` -> ``meter_type``) so legacy v1 Grafana dashboards/queries run unchanged
against the octflux database. Created on every sink start so they survive a DB
rebuild. Plain SQL views -- work on Postgres and SQLite.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

# view name -> SELECT body (NULL cast written portably for PG + SQLite)
COMPAT_VIEWS: dict[str, str] = {
    "octopus_consumption":
        "SELECT mpan, serial_number, fuel AS meter_type, is_export, "
        "interval_start, interval_end, consumption, collected_at AS created_at "
        "FROM consumption",
    "octopus_tariff":
        "SELECT CAST(NULL AS BIGINT) AS octopus_tariff_id, collected_at AS created_at, "
        "valid_from, valid_to, value_exc_vat, value_inc_vat, "
        "product_code AS product, tariff_code AS tariffcode, is_export FROM unit_rate",
    "octopus_standing_charge":
        "SELECT CAST(NULL AS BIGINT) AS octopus_standing_charge_id, collected_at AS created_at, "
        "valid_from, valid_to, value_exc_vat, value_inc_vat FROM standing_charge",
    "octopus_account_balance":
        "SELECT account_number, queried_at, balance_pennies FROM account_balance",
    "octopus_transaction":
        "SELECT account_number, transaction_id, posted_date, created_at, amount_pennies, "
        "balance_carried_forward_pennies, is_credit, title, transaction_type FROM ledger_transaction",
    "octopus_dispatch":
        "SELECT account_number, status, start_at, end_at, delta_kwh, source, location FROM dispatch",
}


def create_compat_views(conn) -> list[str]:
    """Create/refresh the octopus_* compatibility views. Sync connection."""
    pg = conn.dialect.name == "postgresql"
    for name, body in COMPAT_VIEWS.items():
        if pg:
            conn.exec_driver_sql(f"CREATE OR REPLACE VIEW {name} AS {body}")
        else:  # SQLite has no CREATE OR REPLACE VIEW
            conn.exec_driver_sql(f"DROP VIEW IF EXISTS {name}")
            conn.exec_driver_sql(f"CREATE VIEW {name} AS {body}")
    log.info("compat_views_created", views=list(COMPAT_VIEWS))
    return list(COMPAT_VIEWS)
