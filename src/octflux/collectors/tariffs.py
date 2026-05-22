"""Unit rates (import + export) and standing charges for the active tariffs (REST)."""

from __future__ import annotations

from datetime import timedelta

from ..core.models import Agreement, StandingCharge, UnitRate
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS
from ._util import dt


def parse_unit_rates(results: list[dict], ag: Agreement, *, is_export: bool) -> list[UnitRate]:
    return [
        UnitRate(
            tariff_code=ag.tariff_code, product_code=ag.product_code, is_export=is_export,
            valid_from=dt(r["valid_from"]), valid_to=dt(r.get("valid_to")),
            value_exc_vat=r["value_exc_vat"], value_inc_vat=r["value_inc_vat"],
        )
        for r in results
    ]


def parse_standing_charges(results: list[dict], ag: Agreement) -> list[StandingCharge]:
    return [
        StandingCharge(
            tariff_code=ag.tariff_code, product_code=ag.product_code,
            valid_from=dt(r["valid_from"]), valid_to=dt(r.get("valid_to")),
            value_exc_vat=r["value_exc_vat"], value_inc_vat=r["value_inc_vat"],
        )
        for r in results
    ]


class TariffsCollector:
    name = "tariffs"
    datasets = ("unit_rate", "standing_charge")

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        days_back = ctx.options.get("days_back", 1)
        days_forward = ctx.options.get("days_forward", 2)
        pf = ctx.now - timedelta(days=days_back)
        pt = ctx.now + timedelta(days=days_forward)
        rates: list[UnitRate] = []
        charges: list[StandingCharge] = []
        for mp in ctx.account.electricity:
            ag = mp.active_agreement(ctx.now)
            if ag is None:
                continue
            rr = await ctx.rest.get_unit_rates(
                product_code=ag.product_code, tariff_code=ag.tariff_code,
                period_from=pf, period_to=pt,
            )
            rates += parse_unit_rates(rr, ag, is_export=mp.is_export)
            if not mp.is_export:
                sc = await ctx.rest.get_standing_charges(
                    product_code=ag.product_code, tariff_code=ag.tariff_code,
                    period_from=pf, period_to=pt,
                )
                charges += parse_standing_charges(sc, ag)
        return [Batch(DATASETS["unit_rate"], rates), Batch(DATASETS["standing_charge"], charges)]


def build(options: dict) -> TariffsCollector:
    return TariffsCollector()
