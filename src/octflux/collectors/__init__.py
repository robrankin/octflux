"""Collector registry: driver name -> builder(options) -> Collector."""

from __future__ import annotations

from collections.abc import Callable

from ..core.protocols import Collector
from . import (
    agreements,
    balance,
    carbon,
    consumption,
    dimensions,
    dispatches,
    meter_readings,
    octoplus,
    statements,
    tariffs,
)

CollectorBuilder = Callable[[dict], Collector]

COLLECTOR_BUILDERS: dict[str, CollectorBuilder] = {
    "tariffs": tariffs.build,
    "consumption": consumption.build,
    "agreements": agreements.build,
    "balance": balance.build,
    "dispatches": dispatches.build,
    "carbon_intensity": carbon.build,
    "statements": statements.build,
    "meter_readings": meter_readings.build,
    "octoplus": octoplus.build,
    "dim_meter": dimensions.build_meter,
    "dim_tariff": dimensions.build_tariff,
}


def build_collector(driver: str, options: dict) -> Collector:
    try:
        builder = COLLECTOR_BUILDERS[driver]
    except KeyError:
        raise ValueError(
            f"unknown collector driver {driver!r}; known: {sorted(COLLECTOR_BUILDERS)}"
        ) from None
    return builder(options)
