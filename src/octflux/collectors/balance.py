"""Account balance snapshot + ledger transactions (GraphQL)."""

from __future__ import annotations

import structlog

from ..clients.queries import ACCOUNT_BALANCE, ACCOUNT_TRANSACTIONS
from ..core.models import AccountBalance, LedgerTransaction
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS
from ._util import d, dt, opt_int, paginate_edges

log = structlog.get_logger(__name__)


def parse_transactions(edges: list[dict], account_number: str) -> list[LedgerTransaction]:
    out = []
    for e in edges:
        n = e.get("node") or {}
        out.append(LedgerTransaction(
            account_number=account_number, transaction_id=str(n["id"]),
            posted_date=d(n.get("postedDate")), created_at=dt(n.get("createdAt")),
            amount_pennies=int(n.get("amount") or 0),
            balance_carried_forward_pennies=opt_int(n.get("balanceCarriedForward")),
            is_credit=n.get("isCredit"), title=n.get("title"),
            transaction_type=n.get("__typename"),
        ))
    return out


class BalanceCollector:
    name = "balance"
    datasets = ("account_balance", "ledger_transaction")

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        acc = ctx.settings.account_number
        page_size = ctx.options.get("page_size", 100)
        max_pages = ctx.options.get("max_pages", 50)

        data = await ctx.graphql.execute(ACCOUNT_BALANCE, {"accountNumber": acc})
        balance = AccountBalance(
            account_number=acc, queried_at=ctx.now,
            balance_pennies=int(data["account"]["balance"]),
        )

        edges = await paginate_edges(
            ctx.graphql, ACCOUNT_TRANSACTIONS, {"accountNumber": acc}, ("account", "transactions"),
            page_size=page_size, max_pages=max_pages, warn_event="transactions_truncated",
        )
        return [
            Batch(DATASETS["account_balance"], [balance]),
            Batch(DATASETS["ledger_transaction"], parse_transactions(edges, acc)),
        ]


def build(options: dict) -> BalanceCollector:
    return BalanceCollector()
