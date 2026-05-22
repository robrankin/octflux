"""Statements / bills (GraphQL ``account.bills`` -> StatementType)."""

from __future__ import annotations

import structlog

from ..clients.queries import STATEMENTS
from ..core.models import Statement
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS
from ._util import d, opt_int, paginate_edges

log = structlog.get_logger(__name__)


def parse_statements(edges: list[dict], account_number: str) -> list[Statement]:
    out = []
    for e in edges:
        n = e.get("node") or {}
        out.append(Statement(
            account_number=account_number, statement_id=str(n["id"]),
            from_date=d(n.get("fromDate")), to_date=d(n.get("toDate")),
            issued_date=d(n.get("issuedDate")), total_pennies=opt_int(n.get("closingBalance")),
        ))
    return out


class StatementsCollector:
    name = "statements"
    datasets = ("statement",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        acc = ctx.settings.account_number
        edges = await paginate_edges(
            ctx.graphql, STATEMENTS, {"accountNumber": acc}, ("account", "bills"),
            page_size=ctx.options.get("page_size", 50), max_pages=ctx.options.get("max_pages", 20),
            warn_event="statements_truncated",
        )
        return [Batch(DATASETS["statement"], parse_statements(edges, acc))]


def build(options: dict) -> StatementsCollector:
    return StatementsCollector()
