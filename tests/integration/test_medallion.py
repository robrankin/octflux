"""Silver fact_cost transform: consumption x agreement x unit_rate -> cost."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import sqlalchemy as sa

from octflux.core.models import ConsumptionInterval, Fuel, MeterAgreement, UnitRate
from octflux.core.protocols import Batch
from octflux.schema.datasets import DATASETS
from octflux.sinks.sqlite import build


@pytest.mark.integration
async def test_fact_cost_join(tmp_path):
    sink = build("local", {"path": str(tmp_path / "m.db")})
    await sink.start()
    try:
        start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 5, 1, 0, 30, tzinfo=UTC)
        await sink.write(Batch(DATASETS["consumption"], [
            ConsumptionInterval("159", "23J", Fuel.ELECTRICITY, False, start, end, 2.0),
        ]))
        await sink.write(Batch(DATASETS["agreement"], [
            MeterAgreement("A-1", "159", Fuel.ELECTRICITY, False,
                           "E-1R-GO-VAR-22-10-14-F", "GO-VAR-22-10-14",
                           datetime(2024, 1, 1, tzinfo=UTC), None),
        ]))
        await sink.write(Batch(DATASETS["unit_rate"], [
            UnitRate("E-1R-GO-VAR-22-10-14-F", "GO-VAR-22-10-14", False, start, end, 9.5, 10.0),
        ]))

        n = await sink.refresh_silver(window_days=3650)
        assert n == 1
        rows = await sink.recent(DATASETS["fact_cost"], 10)
        assert len(rows) == 1
        assert rows[0]["consumption_kwh"] == 2.0
        assert rows[0]["tariff_code"] == "E-1R-GO-VAR-22-10-14-F"
        assert rows[0]["cost_pence"] == pytest.approx(20.0)  # 2.0 kWh * 10.0 p/kWh

        # idempotent: refreshing again recomputes the same single row
        assert await sink.refresh_silver(window_days=3650) == 1
    finally:
        await sink.close()


@pytest.mark.integration
async def test_compat_views_created_on_start(tmp_path):
    """The v1 octopus_* compat views exist after start and map fuel->meter_type."""
    sink = build("local", {"path": str(tmp_path / "compat.db")})
    await sink.start()
    try:
        start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 5, 1, 0, 30, tzinfo=UTC)
        await sink.write(Batch(DATASETS["consumption"], [
            ConsumptionInterval("159", "23J", Fuel.ELECTRICITY, False, start, end, 1.5),
        ]))
        async with sink._engine.connect() as conn:
            rows = (await conn.execute(
                sa.text("SELECT meter_type, consumption FROM octopus_consumption")
            )).all()
        assert rows == [("electricity", 1.5)]
    finally:
        await sink.close()
