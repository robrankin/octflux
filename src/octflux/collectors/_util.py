"""Tiny shared parse helpers for collectors."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import structlog

from ..core.time import parse_dt as dt

__all__ = ["d", "dt", "opt_float", "opt_int", "paginate_edges"]

log = structlog.get_logger(__name__)


def d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def opt_float(value) -> float | None:
    return None if value is None else float(value)


def opt_int(value) -> int | None:
    return None if value is None else int(value)


async def paginate_edges(graphql, query: str, variables: dict, path: Sequence[str], *,
                         page_size: int, max_pages: int, warn_event: str | None = None) -> list[dict]:
    """Walk a Relay-style connection at ``path`` (e.g. ("account","transactions"))
    and return all its ``edges``. Logs ``warn_event`` if ``max_pages`` is hit."""
    after = None
    edges: list[dict] = []
    for _ in range(max_pages):
        data = await graphql.execute(query, {**variables, "first": page_size, "after": after})
        conn = data
        for key in path:
            conn = (conn or {}).get(key) or {}
        edges.extend(conn.get("edges") or [])
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
    else:
        if warn_event:
            log.warning(warn_event, max_pages=max_pages)
    return edges
