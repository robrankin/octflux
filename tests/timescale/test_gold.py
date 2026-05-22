"""Real-TimescaleDB tests: hypertables, gold continuous aggregates, compression,
retention, bill views, compat views, and the cross-impl sink contract on Postgres.
Shares one container (session-scoped); tests isolate by distinct meter keys."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from octflux.core.models import ConsumptionInterval, Fuel, MeterAgreement, UnitRate
from octflux.core.protocols import Batch
from octflux.schema.datasets import DATASETS
from octflux.sinks.base import SqlSink

pytestmark = pytest.mark.timescale


async def _sink(url, **kw):
    s = SqlSink("pg", url, auto_create=True, **kw)
    await s.start()
    return s


def _scalar(url, sql):
    eng = sa.create_engine(url)
    try:
        with eng.connect() as c:
            return c.execute(sa.text(sql)).scalar()
    finally:
        eng.dispose()


def _set(url, sql):
    eng = sa.create_engine(url)
    try:
        with eng.connect() as c:
            return {r[0] for r in c.execute(sa.text(sql))}
    finally:
        eng.dispose()


async def test_hypertables_caggs_and_views_built(timescale):
    sink = await _sink(timescale)
    try:
        hyper = _set(timescale, "SELECT hypertable_name FROM timescaledb_information.hypertables")
        caggs = _set(timescale, "SELECT view_name FROM timescaledb_information.continuous_aggregates")
        views = _set(timescale, "SELECT table_name FROM information_schema.views WHERE table_schema='public'")
        assert {"consumption", "fact_cost", "unit_rate", "carbon_intensity"} <= hyper
        assert {"cagg_consumption_daily", "cagg_cost_daily", "cagg_consumption_monthly"} <= caggs
        assert {"bill_daily", "bill_monthly", "octopus_consumption"} <= views
        # compression policies exist on the big hypertables
        comp = _set(timescale, "SELECT hypertable_name FROM timescaledb_information.jobs "
                               "WHERE proc_name='policy_compression'")
        assert {"consumption", "fact_cost"} <= comp
    finally:
        await sink.close()


async def test_sink_contract_on_timescale(timescale):
    sink = await _sink(timescale)
    spec = DATASETS["consumption"]

    def rec(v):
        return ConsumptionInterval("MX-CONTRACT", "S", Fuel.ELECTRICITY, False,
                                   datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 1, 0, 30, tzinfo=UTC), v)
    try:
        assert (await sink.write(Batch(spec, [rec(1.0)]))).inserted == 1
        r = await sink.write(Batch(spec, [rec(1.0)]))
        assert (r.inserted, r.updated, r.skipped) == (0, 0, 1)
        r = await sink.write(Batch(spec, [rec(2.5)]))
        assert (r.inserted, r.updated, r.skipped) == (0, 1, 0)
    finally:
        await sink.close()


async def test_fact_cost_and_caggs_end_to_end(timescale):
    sink = await _sink(timescale)
    mpan = "159-E2E"
    start, end = datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 5, 1, 0, 30, tzinfo=UTC)
    try:
        await sink.write(Batch(DATASETS["consumption"], [
            ConsumptionInterval(mpan, "23J", Fuel.ELECTRICITY, False, start, end, 2.0)]))
        await sink.write(Batch(DATASETS["agreement"], [
            MeterAgreement("A-1", mpan, Fuel.ELECTRICITY, False, "E-1R-GO-F", "GO",
                           datetime(2024, 1, 1, tzinfo=UTC), None)]))
        await sink.write(Batch(DATASETS["unit_rate"], [
            UnitRate("E-1R-GO-F", "GO", False, start, end, 9.5, 10.0)]))
        await sink.refresh_silver(window_days=3650)

        cost = _scalar(timescale, f"SELECT cost_pence FROM fact_cost WHERE mpan='{mpan}'")
        kwh = _scalar(timescale, f"SELECT sum(kwh) FROM cagg_consumption_daily WHERE mpan='{mpan}'")
        assert cost == pytest.approx(20.0)        # 2.0 kWh * 10.0 p/kWh
        assert float(kwh) == pytest.approx(2.0)   # real-time cagg returns it immediately
    finally:
        await sink.close()


async def test_compat_view_maps_fuel_to_meter_type(timescale):
    sink = await _sink(timescale)
    try:
        await sink.write(Batch(DATASETS["consumption"], [
            ConsumptionInterval("COMPAT", "S", Fuel.GAS, False,
                                datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 1, 0, 30, tzinfo=UTC), 5.0)]))
        mt = _scalar(timescale, "SELECT meter_type FROM octopus_consumption WHERE mpan='COMPAT'")
        assert mt == "gas"
    finally:
        await sink.close()


def _has_retention(url) -> bool:
    return "policy_retention" in _set(
        url, "SELECT proc_name FROM timescaledb_information.jobs WHERE proc_name='policy_retention'")


async def test_retention_policy_can_be_enabled_and_disabled(timescale):
    # enable -> policy present
    s1 = await _sink(timescale, retention_days=400)
    await s1.close()
    assert _has_retention(timescale)
    # disable (default 0 = keep forever) -> policy reconciled away
    s2 = await _sink(timescale, retention_days=0)
    await s2.close()
    assert not _has_retention(timescale)
