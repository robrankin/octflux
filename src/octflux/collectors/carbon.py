"""Projected regional carbon intensity for the supply postcode (GraphQL)."""

from __future__ import annotations

import structlog

from ..clients.queries import CARBON_INTENSITY
from ..core.models import CarbonIntensity
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS
from ._util import dt, opt_float

log = structlog.get_logger(__name__)


def parse_carbon(points: list[dict], postcode: str) -> list[CarbonIntensity]:
    rows = sorted(
        (CarbonIntensity(postcode=postcode, valid_from=dt(p["periodStart"]), valid_to=None,
                         intensity_gco2_kwh=opt_float(p.get("value")), index=p.get("index"))
         for p in points),
        key=lambda r: r.valid_from,
    )
    # Close each window with the next period's start. The final, still-open period is
    # dropped so it isn't re-UPDATEd (gaining a valid_to) on the next overlapping fetch
    # -- it reappears, closed, on the following cycle.
    return [
        CarbonIntensity(r.postcode, r.valid_from, rows[i + 1].valid_from,
                        r.intensity_gco2_kwh, r.index)
        for i, r in enumerate(rows[:-1])
    ]


class CarbonIntensityCollector:
    name = "carbon_intensity"
    datasets = ("carbon_intensity",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        postcode = ctx.account.postcode or ctx.settings.postcode
        if not postcode:
            log.warning("carbon_skipped", reason="no_postcode")
            return []
        data = await ctx.graphql.execute(CARBON_INTENSITY, {"postcode": postcode})
        points = (data.get("getProjectedRegionalCarbonIntensity") or {}).get(
            "projectedRegionalCarbonIntensity"
        ) or []
        return [Batch(DATASETS["carbon_intensity"], parse_carbon(points, postcode))]


def build(options: dict) -> CarbonIntensityCollector:
    return CarbonIntensityCollector()
