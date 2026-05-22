"""Generic SQL sink (SQLAlchemy Core, async) shared by all SQL dialects.

Change-detection is done by diffing each batch against the existing rows in
Python rather than via dialect-specific ``ON CONFLICT`` clauses, so the exact
same logic runs on Postgres, SQLite and MySQL: only genuinely new rows are
inserted and only genuinely changed rows are updated -- no write churn, and the
inserted/updated/skipped counts are accurate on every backend.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import islice

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import create_async_engine

from ..core.protocols import Batch, WriteResult
from ..core.time import now_naive, to_naive_utc
from ..schema.compat import create_compat_views
from ..schema.datasets import DatasetSpec
from ..schema.medallion import create_gold
from ..schema.medallion import refresh_silver as _refresh_silver
from ..schema.tables import metadata
from ..schema.timescale import create_hypertables

log = structlog.get_logger(__name__)


def _to_db(col_type: sa.types.TypeEngine, v: object) -> object:
    """The value as it should be written/looked-up (uniform across dialects)."""
    if isinstance(col_type, sa.DateTime):
        return to_naive_utc(v)
    return v


def _norm(col_type: sa.types.TypeEngine, v: object) -> object:
    """Normalise a value so DB-returned and incoming forms compare equal."""
    if v is None:
        return None
    if isinstance(col_type, (sa.Numeric, sa.Float)):
        return round(float(v), 6)
    if isinstance(col_type, sa.Boolean):
        return bool(v)
    if isinstance(col_type, sa.DateTime):
        return to_naive_utc(v)
    if isinstance(v, Decimal):
        return float(v)
    return v


def _chunks(seq, size):
    it = iter(seq)
    while batch := list(islice(it, size)):
        yield batch


class SqlSink:
    """A SQL output. ``url`` is a SQLAlchemy async URL (the dialect drivers in
    this package just build the right URL and hand it here)."""

    def __init__(self, name: str, url: str, *, auto_create: bool = True, retention_days: int = 0):
        self.name = name
        self._url = url
        self._auto_create = auto_create
        self._retention_days = retention_days
        self._engine = None

    async def start(self) -> None:
        self._engine = create_async_engine(self._url, pool_pre_ping=True)
        if self._auto_create:
            async with self._engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
                await conn.run_sync(create_hypertables)  # no-op unless PG + Timescale
                await conn.run_sync(create_compat_views)  # v1 octopus_* views
            # Gold (continuous aggregates + policies) needs autocommit; no-op off Timescale.
            auto = self._engine.execution_options(isolation_level="AUTOCOMMIT")
            async with auto.connect() as conn:
                await conn.run_sync(lambda c: create_gold(c, retention_days=self._retention_days))

    async def refresh_silver(self, window_days: int = 7) -> int:
        async with self._engine.begin() as conn:
            return await conn.run_sync(lambda c: _refresh_silver(c, window_days))

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    @staticmethod
    def _dedupe(rows: list[dict], key: tuple[str, ...]) -> list[dict]:
        seen: dict[tuple, dict] = {}
        for r in rows:
            seen[tuple(r[c] for c in key)] = r  # last write wins within a batch
        return list(seen.values())

    async def _fetch_existing(self, conn, spec: DatasetSpec, rows: list[dict]) -> dict:
        cols = [spec.table.c[c] for c in (*spec.key, *spec.value_cols)]
        keytuple = sa.tuple_(*[spec.table.c[c] for c in spec.key])
        existing: dict[tuple, dict] = {}
        for chunk in _chunks(rows, 500):
            values = [tuple(r[c] for c in spec.key) for r in chunk]
            result = await conn.execute(sa.select(*cols).where(keytuple.in_(values)))
            for row in result.mappings():
                existing[tuple(row[c] for c in spec.key)] = dict(row)
        return existing

    def _changed(self, spec: DatasetSpec, old: dict, new: dict) -> bool:
        for c in spec.value_cols:
            t = spec.table.c[c].type
            if _norm(t, old.get(c)) != _norm(t, new.get(c)):
                return True
        return False

    @staticmethod
    def _normalize(spec: DatasetSpec, row: dict) -> dict:
        return {c: _to_db(spec.table.c[c].type, v) for c, v in row.items()}

    async def write(self, batch: Batch) -> WriteResult:
        spec = batch.spec
        rows = [self._normalize(spec, spec.to_row(r)) for r in batch.records]
        if not rows:
            return WriteResult()
        rows = self._dedupe(rows, spec.key)
        now = now_naive()  # collected_at column is naive UTC
        inserts: list[dict] = []
        updates: list[dict] = []
        skipped = 0
        async with self._engine.begin() as conn:
            existing = await self._fetch_existing(conn, spec, rows)
            for r in rows:
                k = tuple(r[c] for c in spec.key)
                if k not in existing:
                    inserts.append(r)
                elif self._changed(spec, existing[k], r):
                    updates.append(r)
                else:
                    skipped += 1
            if inserts:
                await conn.execute(
                    sa.insert(spec.table), [{**r, "collected_at": now} for r in inserts]
                )
            for r in updates:
                await conn.execute(
                    sa.update(spec.table)
                    .where(*[spec.table.c[c] == r[c] for c in spec.key])
                    .values(**{c: r[c] for c in spec.value_cols}, collected_at=now)
                )
        result = WriteResult(inserted=len(inserts), updated=len(updates), skipped=skipped)
        log.info("rows_written", sink=self.name, table=spec.name, **result.as_log())
        return result

    async def recent(self, spec: DatasetSpec, limit: int = 50) -> list[dict]:
        """Most recently collected rows of a dataset (for the control API)."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                sa.select(spec.table).order_by(spec.table.c.collected_at.desc()).limit(limit)
            )
            return [dict(r) for r in result.mappings()]
