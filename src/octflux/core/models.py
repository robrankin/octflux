"""Domain models -- frozen dataclasses that flow collectors -> sinks.

Deliberately inert: no I/O, no DB or API knowledge. Parsers build them from raw
API JSON; the dataset specs in :mod:`octflux.schema.datasets` map them to rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Fuel(StrEnum):
    ELECTRICITY = "electricity"
    GAS = "gas"


class DispatchStatus(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"


# -- account discovery (not stored; used by collectors) -----------------------


@dataclass(frozen=True, slots=True)
class Agreement:
    fuel: Fuel
    tariff_code: str
    product_code: str
    valid_from: datetime
    valid_to: datetime | None
    is_export: bool

    def is_active_at(self, when: datetime) -> bool:
        if when < self.valid_from:
            return False
        return self.valid_to is None or when < self.valid_to


@dataclass(frozen=True, slots=True)
class Meter:
    serial_number: str
    meter_id: str | None  # Kraken internal id (needed by some GraphQL queries)


@dataclass(frozen=True, slots=True)
class MeterPoint:
    fuel: Fuel
    identifier: str  # MPAN or MPRN
    is_export: bool
    meters: tuple[Meter, ...]
    agreements: tuple[Agreement, ...]

    def active_agreement(self, when: datetime) -> Agreement | None:
        candidates = [a for a in self.agreements if a.is_active_at(when)]
        return max(candidates, key=lambda a: a.valid_from) if candidates else None


@dataclass(frozen=True, slots=True)
class Account:
    number: str
    postcode: str | None
    meter_points: tuple[MeterPoint, ...]

    @property
    def electricity(self) -> tuple[MeterPoint, ...]:
        return tuple(m for m in self.meter_points if m.fuel is Fuel.ELECTRICITY)

    @property
    def gas(self) -> tuple[MeterPoint, ...]:
        return tuple(m for m in self.meter_points if m.fuel is Fuel.GAS)

    def is_intelligent(self, when: datetime) -> bool:
        for mp in self.electricity:
            if mp.is_export:
                continue
            a = mp.active_agreement(when)
            if a is not None and "INTELLI" in a.product_code.upper():
                return True
        return False


# -- stored datasets ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UnitRate:
    tariff_code: str
    product_code: str
    is_export: bool
    valid_from: datetime
    valid_to: datetime | None
    value_exc_vat: float
    value_inc_vat: float


@dataclass(frozen=True, slots=True)
class StandingCharge:
    tariff_code: str
    product_code: str
    valid_from: datetime
    valid_to: datetime | None
    value_exc_vat: float
    value_inc_vat: float


@dataclass(frozen=True, slots=True)
class ConsumptionInterval:
    mpan: str  # MPAN or MPRN
    serial_number: str
    fuel: Fuel
    is_export: bool
    interval_start: datetime
    interval_end: datetime
    consumption: float


@dataclass(frozen=True, slots=True)
class AccountBalance:
    account_number: str
    queried_at: datetime
    balance_pennies: int


@dataclass(frozen=True, slots=True)
class LedgerTransaction:
    account_number: str
    transaction_id: str
    posted_date: date | None
    created_at: datetime | None
    amount_pennies: int
    balance_carried_forward_pennies: int | None
    is_credit: bool | None
    title: str | None
    transaction_type: str | None


@dataclass(frozen=True, slots=True)
class Dispatch:
    account_number: str
    status: DispatchStatus
    start: datetime
    end: datetime
    delta_kwh: float | None
    source: str | None
    location: str | None


@dataclass(frozen=True, slots=True)
class CarbonIntensity:
    postcode: str
    valid_from: datetime
    valid_to: datetime | None
    intensity_gco2_kwh: float | None
    index: str | None  # e.g. "low" / "moderate" / "high"


@dataclass(frozen=True, slots=True)
class Statement:
    account_number: str
    statement_id: str
    from_date: date | None
    to_date: date | None
    issued_date: date | None
    total_pennies: int | None


@dataclass(frozen=True, slots=True)
class MeterReading:
    account_number: str
    meter_id: str
    fuel: Fuel
    read_at: datetime
    register: str  # register identifier (a read can have several, e.g. day/night)
    value: float
    source: str | None  # reading type / source


@dataclass(frozen=True, slots=True)
class DimMeter:
    mpan: str
    serial_number: str
    fuel: Fuel
    is_export: bool
    meter_id: str | None


@dataclass(frozen=True, slots=True)
class DimTariff:
    tariff_code: str
    product_code: str
    fuel: Fuel


@dataclass(frozen=True, slots=True)
class MeterAgreement:
    """A stored meter->tariff agreement window (which tariff applied when)."""

    account_number: str
    mpan: str
    fuel: Fuel
    is_export: bool
    tariff_code: str
    product_code: str
    valid_from: datetime
    valid_to: datetime | None


@dataclass(frozen=True, slots=True)
class OctoplusInfo:
    account_number: str
    queried_at: datetime
    is_enrolled: bool | None
    enrollment_status: str | None
