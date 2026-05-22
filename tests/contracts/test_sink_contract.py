"""Contract every SQL sink must satisfy: insert new, skip unchanged, update
changed, and stay idempotent. Runs on SQLite always; add a live Postgres URL via
OCTFLUX_TEST_PG_URL to run the same contract there.
"""

from __future__ import annotations

import os

import pytest

from octflux.core.models import ConsumptionInterval, Fuel
from octflux.core.protocols import Batch
from octflux.schema.datasets import DATASETS
from octflux.sinks.base import SqlSink

from datetime import UTC, datetime


def _sinks(tmp_path):
    yield SqlSink("sqlite", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}", auto_create=True)
    pg = os.environ.get("OCTFLUX_TEST_PG_URL")
    if pg:
        yield SqlSink("postgres", pg, auto_create=True)


def _rec(val):
    return ConsumptionInterval(
        "1591016047308", "23J", Fuel.ELECTRICITY, False,
        datetime(2026, 5, 1, 0, 0, tzinfo=UTC), datetime(2026, 5, 1, 0, 30, tzinfo=UTC), val,
    )


@pytest.mark.contract
async def test_sink_insert_skip_update_idempotent(tmp_path):
    spec = DATASETS["consumption"]
    for sink in _sinks(tmp_path):
        await sink.start()
        try:
            r_new = await sink.write(Batch(spec, [_rec(1.0)]))
            assert (r_new.inserted, r_new.updated, r_new.skipped) == (1, 0, 0)
            r_same = await sink.write(Batch(spec, [_rec(1.0)]))
            assert (r_same.inserted, r_same.updated, r_same.skipped) == (0, 0, 1)
            r_chg = await sink.write(Batch(spec, [_rec(2.5)]))
            assert (r_chg.inserted, r_chg.updated, r_chg.skipped) == (0, 1, 0)
            rows = await sink.recent(spec, 10)
            assert len(rows) == 1 and rows[0]["consumption"] == 2.5
        finally:
            await sink.close()


@pytest.mark.contract
async def test_sink_empty_batch_noop(tmp_path):
    sink = SqlSink("sqlite", f"sqlite+aiosqlite:///{tmp_path / 'e.db'}", auto_create=True)
    await sink.start()
    try:
        r = await sink.write(Batch(DATASETS["consumption"], []))
        assert (r.inserted, r.updated, r.skipped) == (0, 0, 0)
    finally:
        await sink.close()
