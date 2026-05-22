"""Dataset specs: bind a domain model to its table, natural key, the columns
that count as a "change", and a model->row mapper.

The generic SQL sink and the MQTT sink are written entirely against ``DatasetSpec``
so they need no per-dataset code. Adding a stored dataset = a table, a model, and
one entry here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from . import tables as t


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    table: sa.Table
    key: tuple[str, ...]
    value_cols: tuple[str, ...]
    to_row: Callable[[Any], dict]


def _spec(name, table, key, value_cols, to_row) -> DatasetSpec:
    return DatasetSpec(name, table, key, value_cols, to_row)


DATASETS: dict[str, DatasetSpec] = {
    "unit_rate": _spec(
        "unit_rate", t.unit_rate,
        ("tariff_code", "is_export", "valid_from"),
        ("product_code", "valid_to", "value_exc_vat", "value_inc_vat"),
        lambda r: dict(
            tariff_code=r.tariff_code, product_code=r.product_code, is_export=r.is_export,
            valid_from=r.valid_from, valid_to=r.valid_to,
            value_exc_vat=r.value_exc_vat, value_inc_vat=r.value_inc_vat,
        ),
    ),
    "standing_charge": _spec(
        "standing_charge", t.standing_charge,
        ("tariff_code", "valid_from"),
        ("product_code", "valid_to", "value_exc_vat", "value_inc_vat"),
        lambda r: dict(
            tariff_code=r.tariff_code, product_code=r.product_code,
            valid_from=r.valid_from, valid_to=r.valid_to,
            value_exc_vat=r.value_exc_vat, value_inc_vat=r.value_inc_vat,
        ),
    ),
    "consumption": _spec(
        "consumption", t.consumption,
        ("mpan", "serial_number", "fuel", "is_export", "interval_start"),
        ("interval_end", "consumption"),
        lambda r: dict(
            mpan=r.mpan, serial_number=r.serial_number, fuel=r.fuel.value,
            is_export=r.is_export, interval_start=r.interval_start,
            interval_end=r.interval_end, consumption=r.consumption,
        ),
    ),
    "account_balance": _spec(
        "account_balance", t.account_balance,
        ("account_number", "queried_at"), ("balance_pennies",),
        lambda r: dict(account_number=r.account_number, queried_at=r.queried_at,
                       balance_pennies=r.balance_pennies),
    ),
    "ledger_transaction": _spec(
        "ledger_transaction", t.ledger_transaction,
        ("transaction_id",),
        ("account_number", "posted_date", "created_at", "amount_pennies",
         "balance_carried_forward_pennies", "is_credit", "title", "transaction_type"),
        lambda r: dict(
            transaction_id=r.transaction_id, account_number=r.account_number,
            posted_date=r.posted_date, created_at=r.created_at, amount_pennies=r.amount_pennies,
            balance_carried_forward_pennies=r.balance_carried_forward_pennies,
            is_credit=r.is_credit, title=r.title, transaction_type=r.transaction_type,
        ),
    ),
    "dispatch": _spec(
        "dispatch", t.dispatch,
        ("account_number", "status", "start_at"),
        ("end_at", "delta_kwh", "source", "location"),
        lambda r: dict(
            account_number=r.account_number, status=r.status.value, start_at=r.start,
            end_at=r.end, delta_kwh=r.delta_kwh, source=r.source, location=r.location,
        ),
    ),
    "carbon_intensity": _spec(
        "carbon_intensity", t.carbon_intensity,
        ("postcode", "valid_from"),
        ("valid_to", "intensity_gco2_kwh", "intensity_index"),
        lambda r: dict(
            postcode=r.postcode, valid_from=r.valid_from, valid_to=r.valid_to,
            intensity_gco2_kwh=r.intensity_gco2_kwh, intensity_index=r.index,
        ),
    ),
    "statement": _spec(
        "statement", t.statement,
        ("account_number", "statement_id"),
        ("from_date", "to_date", "issued_date", "total_pennies"),
        lambda r: dict(
            account_number=r.account_number, statement_id=r.statement_id,
            from_date=r.from_date, to_date=r.to_date, issued_date=r.issued_date,
            total_pennies=r.total_pennies,
        ),
    ),
    "meter_reading": _spec(
        "meter_reading", t.meter_reading,
        ("account_number", "meter_id", "read_at", "register"),
        ("fuel", "value", "source"),
        lambda r: dict(
            account_number=r.account_number, meter_id=r.meter_id, fuel=r.fuel.value,
            read_at=r.read_at, register=r.register, value=r.value, source=r.source,
        ),
    ),
    "octoplus": _spec(
        "octoplus", t.octoplus,
        ("account_number", "queried_at"), ("is_enrolled", "enrollment_status"),
        lambda r: dict(account_number=r.account_number, queried_at=r.queried_at,
                       is_enrolled=r.is_enrolled, enrollment_status=r.enrollment_status),
    ),
    "agreement": _spec(
        "agreement", t.agreement,
        ("mpan", "is_export", "tariff_code", "valid_from"),
        ("account_number", "fuel", "product_code", "valid_to"),
        lambda r: dict(
            account_number=r.account_number, mpan=r.mpan, fuel=r.fuel.value,
            is_export=r.is_export, tariff_code=r.tariff_code, product_code=r.product_code,
            valid_from=r.valid_from, valid_to=r.valid_to,
        ),
    ),
    # -- silver dimensions (written by collectors from the account) ----------
    "dim_meter": _spec(
        "dim_meter", t.dim_meter,
        ("mpan", "serial_number", "fuel", "is_export"), ("meter_id",),
        lambda r: dict(mpan=r.mpan, serial_number=r.serial_number, fuel=r.fuel.value,
                       is_export=r.is_export, meter_id=r.meter_id),
    ),
    "dim_tariff": _spec(
        "dim_tariff", t.dim_tariff,
        ("tariff_code",), ("product_code", "fuel"),
        lambda r: dict(tariff_code=r.tariff_code, product_code=r.product_code, fuel=r.fuel.value),
    ),
    # -- silver fact (built by the medallion transform; present so /data can read it) --
    "fact_cost": _spec(
        "fact_cost", t.fact_cost,
        ("mpan", "serial_number", "fuel", "is_export", "interval_start"),
        ("interval_end", "consumption_kwh", "tariff_code", "unit_price_inc_vat", "cost_pence"),
        lambda r: r,
    ),
}
