"""Cumulative meter register readings (GraphQL), per electricity/gas meter id."""

from __future__ import annotations

from ..clients.queries import ELECTRICITY_METER_READINGS, GAS_METER_READINGS
from ..core.models import Fuel, MeterReading
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS
from ._util import dt, opt_float, paginate_edges


def parse_readings(edges: list[dict], account_number: str, meter_id: str, fuel: Fuel) -> list[MeterReading]:
    out = []
    for e in edges:
        n = e.get("node") or {}
        read_at = dt(n.get("readAt"))
        if read_at is None:  # read_at is in the PK
            continue
        source = n.get("readingType") or n.get("source")
        for reg in n.get("registers") or []:
            value = opt_float(reg.get("value"))
            if value is None:
                continue
            out.append(MeterReading(
                account_number=account_number, meter_id=meter_id, fuel=fuel,
                read_at=read_at, register=reg.get("identifier") or "default",
                value=value, source=source,
            ))
    return out


class MeterReadingsCollector:
    name = "meter_readings"
    datasets = ("meter_reading",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        acc = ctx.settings.account_number
        page_size = ctx.options.get("page_size", 100)
        max_pages = ctx.options.get("max_pages", 1)
        rows: list[MeterReading] = []
        for mp in ctx.account.meter_points:
            elec = mp.fuel is Fuel.ELECTRICITY
            query = ELECTRICITY_METER_READINGS if elec else GAS_METER_READINGS
            field = "electricityMeterReadings" if elec else "gasMeterReadings"
            for meter in mp.meters:
                if not meter.meter_id:
                    continue
                edges = await paginate_edges(
                    ctx.graphql, query, {"accountNumber": acc, "meterId": meter.meter_id},
                    (field,), page_size=page_size, max_pages=max_pages,
                )
                rows += parse_readings(edges, acc, meter.meter_id, mp.fuel)
        return [Batch(DATASETS["meter_reading"], rows)]


def build(options: dict) -> MeterReadingsCollector:
    return MeterReadingsCollector()
