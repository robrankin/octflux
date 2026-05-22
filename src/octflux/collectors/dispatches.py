"""Intelligent Octopus smart-charging dispatches (GraphQL).

Gated on the account being Intelligent: otherwise the query errors with "Unable
to find device for given account", so non-IO accounts simply yield nothing.
"""

from __future__ import annotations

import structlog

from ..clients.queries import DISPATCHES
from ..core.models import Dispatch, DispatchStatus
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS
from ._util import dt, opt_float

log = structlog.get_logger(__name__)


def _first_dt(node: dict, *keys: str):
    for k in keys:
        if node.get(k):
            return dt(node[k])
    return None


def parse_dispatches(items: list[dict], account_number: str, status: DispatchStatus) -> list[Dispatch]:
    out = []
    for n in items:
        start = _first_dt(n, "start", "startDt", "startDtUtc")
        end = _first_dt(n, "end", "endDt", "endDtUtc")
        if start is None or end is None:  # start_at is in the PK; end_at is NOT NULL
            continue
        meta = n.get("meta") or {}
        out.append(Dispatch(
            account_number=account_number, status=status, start=start, end=end,
            delta_kwh=opt_float(n.get("delta", n.get("deltaKwh"))),
            source=meta.get("source"), location=meta.get("location"),
        ))
    return out


class DispatchesCollector:
    name = "dispatches"
    datasets = ("dispatch",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        if not ctx.account.is_intelligent(ctx.now):
            log.info("dispatches_skipped", reason="not_intelligent_account")
            return []
        acc = ctx.settings.account_number
        data = await ctx.graphql.execute(DISPATCHES, {"accountNumber": acc})
        rows = parse_dispatches(data.get("plannedDispatches") or [], acc, DispatchStatus.PLANNED)
        rows += parse_dispatches(data.get("completedDispatches") or [], acc, DispatchStatus.COMPLETED)
        return [Batch(DATASETS["dispatch"], rows)]


def build(options: dict) -> DispatchesCollector:
    return DispatchesCollector()
