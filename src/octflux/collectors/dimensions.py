"""Silver dimension collectors, populated from the resolved account.

Maintained at collection time (the account is the source of truth for meters and
their tariffs), rather than derived in SQL -- the meter<->serial<->kraken-id link
only exists in the account, not in any single bronze table.
"""

from __future__ import annotations

from ..core.models import DimMeter, DimTariff
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS


class DimMeterCollector:
    name = "dim_meter"
    datasets = ("dim_meter",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        rows = [
            DimMeter(mp.identifier, m.serial_number, mp.fuel, mp.is_export, m.meter_id)
            for mp in ctx.account.meter_points
            for m in mp.meters
        ]
        return [Batch(DATASETS["dim_meter"], rows)]


class DimTariffCollector:
    name = "dim_tariff"
    datasets = ("dim_tariff",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        seen: dict[str, DimTariff] = {}
        for mp in ctx.account.meter_points:
            for ag in mp.agreements:
                seen[ag.tariff_code] = DimTariff(ag.tariff_code, ag.product_code, mp.fuel)
        return [Batch(DATASETS["dim_tariff"], list(seen.values()))]


def build_meter(options: dict) -> DimMeterCollector:
    return DimMeterCollector()


def build_tariff(options: dict) -> DimTariffCollector:
    return DimTariffCollector()
