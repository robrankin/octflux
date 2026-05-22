"""Property-based tests (hypothesis) for the load-bearing invariants."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from octflux.core.models import ConsumptionInterval, Fuel
from octflux.core.protocols import Batch
from octflux.core.time import to_naive_utc
from octflux.schema.datasets import DATASETS
from octflux.sinks.base import SqlSink

_BASE = datetime(2026, 5, 1, tzinfo=UTC)


@given(st.datetimes(timezones=st.one_of(st.none(), st.timezones())))
def test_to_naive_utc_is_idempotent_and_naive(dt):
    once = to_naive_utc(dt)
    assert once.tzinfo is None
    assert to_naive_utc(once) == once  # second pass is a no-op


def _records(values):
    return [
        ConsumptionInterval("159", "23J", Fuel.ELECTRICITY, False,
                            _BASE + timedelta(minutes=30 * i), _BASE + timedelta(minutes=30 * (i + 1)), v)
        for i, v in enumerate(values)
    ]


async def _fresh_sink():
    sink = SqlSink("p", f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/p.db", auto_create=True)
    await sink.start()
    return sink


_FLOATS = st.lists(
    st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    min_size=1, max_size=15,
)


@settings(max_examples=25, deadline=None)
@given(values=_FLOATS)
def test_change_detection_idempotent(values):
    async def run():
        sink = await _fresh_sink()
        try:
            spec, recs = DATASETS["consumption"], _records(values)
            r1 = await sink.write(Batch(spec, recs))
            assert (r1.inserted, r1.updated, r1.skipped) == (len(recs), 0, 0)  # all new (distinct keys)
            r2 = await sink.write(Batch(spec, recs))
            assert (r2.inserted, r2.updated, r2.skipped) == (0, 0, len(recs))  # identical -> all skipped
        finally:
            await sink.close()
    asyncio.run(run())


@settings(max_examples=20, deadline=None)
@given(values=_FLOATS)
def test_change_detection_updates_only_changed(values):
    async def run():
        sink = await _fresh_sink()
        try:
            spec, recs = DATASETS["consumption"], _records(values)
            await sink.write(Batch(spec, recs))
            first = recs[0]
            bumped = [ConsumptionInterval("159", "23J", Fuel.ELECTRICITY, False,
                                          first.interval_start, first.interval_end,
                                          first.consumption + 1.0), *recs[1:]]
            r = await sink.write(Batch(spec, bumped))
            assert (r.inserted, r.updated, r.skipped) == (0, 1, len(recs) - 1)
        finally:
            await sink.close()
    asyncio.run(run())
