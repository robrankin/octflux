"""Meter -> tariff agreement history (bronze), from the resolved account.

Stores which tariff applied to each meter over time, so the silver cost fact can
join consumption to the rate that was in force.
"""

from __future__ import annotations

from ..core.models import MeterAgreement
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS


class AgreementsCollector:
    name = "agreements"
    datasets = ("agreement",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        rows: list[MeterAgreement] = []
        for mp in ctx.account.meter_points:
            for ag in mp.agreements:
                rows.append(MeterAgreement(
                    account_number=ctx.account.number, mpan=mp.identifier, fuel=mp.fuel,
                    is_export=mp.is_export, tariff_code=ag.tariff_code,
                    product_code=ag.product_code, valid_from=ag.valid_from, valid_to=ag.valid_to,
                ))
        return [Batch(DATASETS["agreement"], rows)]


def build(options: dict) -> AgreementsCollector:
    return AgreementsCollector()
