"""Half-hourly consumption for every electricity and gas meter (REST).

``days_back`` is configurable so the same collector can run hourly with a short
window and weekly with a wide one (the deep resync). Change-detection in the SQL
sink makes the wide window cheap.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from ..core.models import ConsumptionInterval, Meter, MeterPoint
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS
from ._util import dt


def parse_consumption(results: list[dict], mp: MeterPoint, meter: Meter) -> list[ConsumptionInterval]:
    return [
        ConsumptionInterval(
            mpan=mp.identifier, serial_number=meter.serial_number, fuel=mp.fuel,
            is_export=mp.is_export, interval_start=dt(r["interval_start"]),
            interval_end=dt(r["interval_end"]), consumption=r["consumption"],
        )
        for r in results
    ]


class ConsumptionCollector:
    name = "consumption"
    datasets = ("consumption",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        pf = ctx.now - timedelta(days=ctx.options.get("days_back", 1))
        pt = ctx.now
        targets = [(mp, meter)
                   for mp in (*ctx.account.electricity, *ctx.account.gas)
                   for meter in mp.meters]
        results = await asyncio.gather(*(
            ctx.rest.get_consumption(fuel=mp.fuel.value, identifier=mp.identifier,
                                     serial_number=meter.serial_number, period_from=pf, period_to=pt)
            for mp, meter in targets
        ))
        intervals = [iv for (mp, meter), res in zip(targets, results, strict=True)
                     for iv in parse_consumption(res, mp, meter)]
        return [Batch(DATASETS["consumption"], intervals)]


def build(options: dict) -> ConsumptionCollector:
    return ConsumptionCollector()
