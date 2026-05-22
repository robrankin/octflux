"""Drive each collector's collect() with fakes (the parse_* fns are unit-tested
separately; this covers the collect/pagination/gating logic)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fakes.clients import FakeGraphQl, FakeRest

from octflux.collectors import build_collector
from octflux.core.models import Account, Agreement, Fuel, Meter, MeterPoint
from octflux.core.protocols import CollectContext

pytestmark = pytest.mark.integration
NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _account(*, intelligent=False, postcode="NE17 7AD") -> Account:
    pc = "INTELLI-VAR-22-10-14" if intelligent else "GO-VAR-22-10-14"
    elec = MeterPoint(Fuel.ELECTRICITY, "159", False, (Meter("23J", "10172874"),),
                      (Agreement(Fuel.ELECTRICITY, f"E-1R-{pc}-F", pc,
                                 datetime(2024, 1, 1, tzinfo=UTC), None, False),))
    gas = MeterPoint(Fuel.GAS, "G99", False, (Meter("G4F", "20000001"),),
                     (Agreement(Fuel.GAS, "G-1R-GAS-F", "GAS",
                                datetime(2024, 1, 1, tzinfo=UTC), None, False),))
    return Account("A-1", postcode, (elec, gas))


def _ctx(account, responses=None, *, rest=None, options=None) -> CollectContext:
    return CollectContext(
        rest=rest or FakeRest(), graphql=FakeGraphQl(responses or {}),
        settings=SimpleNamespace(account_number="A-1", postcode=None),
        now=NOW, account=account, options=options or {},
    )


async def _rows(name, account, responses=None, **kw):
    batches = await build_collector(name, {}).collect(_ctx(account, responses, **kw))
    return [r for b in batches for r in b.records]


async def test_agreements_from_account():
    rows = await _rows("agreements", _account())
    assert {r.tariff_code for r in rows} == {"E-1R-GO-VAR-22-10-14-F", "G-1R-GAS-F"}
    assert all(r.account_number == "A-1" for r in rows)


async def test_dim_meter_from_account():
    rows = await _rows("dim_meter", _account())
    assert {(r.mpan, r.serial_number, r.meter_id) for r in rows} == {
        ("159", "23J", "10172874"), ("G99", "G4F", "20000001")}


async def test_dim_tariff_distinct():
    rows = await _rows("dim_tariff", _account())
    assert {r.tariff_code for r in rows} == {"E-1R-GO-VAR-22-10-14-F", "G-1R-GAS-F"}


async def test_dispatches_skipped_when_not_intelligent():
    assert await _rows("dispatches", _account(intelligent=False)) == []


async def test_dispatches_parsed_when_intelligent():
    resp = {"Dispatches": {
        "plannedDispatches": [{"startDtUtc": "2026-05-01T11:00:00Z", "endDtUtc": "2026-05-01T12:00:00Z"}],
        "completedDispatches": []}}
    rows = await _rows("dispatches", _account(intelligent=True), resp)
    assert len(rows) == 1 and rows[0].status.value == "planned"


async def test_dispatches_skips_rows_missing_timestamp():
    resp = {"Dispatches": {"plannedDispatches": [{"startDtUtc": "2026-05-01T11:00:00Z"}],  # no end
                           "completedDispatches": []}}
    assert await _rows("dispatches", _account(intelligent=True), resp) == []


async def test_carbon_skipped_without_postcode():
    assert await _rows("carbon_intensity", _account(postcode=None)) == []


async def test_carbon_parsed_drops_open_period():
    resp = {"Carbon": {"getProjectedRegionalCarbonIntensity": {"projectedRegionalCarbonIntensity": [
        {"periodStart": "2026-05-01T00:00:00Z", "value": 90, "index": "low"},
        {"periodStart": "2026-05-01T00:30:00Z", "value": 100, "index": "moderate"}]}}}
    rows = await _rows("carbon_intensity", _account(), resp)
    assert len(rows) == 1 and rows[0].valid_to is not None


async def test_octoplus_snapshot():
    resp = {"Octoplus": {"octoplusAccountInfo": {"isOctoplusEnrolled": True, "enrollmentStatus": "ENROLLED"}}}
    rows = await _rows("octoplus", _account(), resp)
    assert rows[0].is_enrolled is True and rows[0].enrollment_status == "ENROLLED"


async def test_meter_readings_per_fuel():
    node = {"readAt": "2026-04-09T00:00:00Z", "readingType": "Smart",
            "registers": [{"identifier": "1", "value": 1000.5}]}
    resp = {
        "ElecReadings": {"electricityMeterReadings": {"pageInfo": {"hasNextPage": False}, "edges": [{"node": node}]}},
        "GasReadings": {"gasMeterReadings": {"pageInfo": {"hasNextPage": False}, "edges": [{"node": node}]}},
    }
    rows = await _rows("meter_readings", _account(), resp)
    assert {r.fuel for r in rows} == {Fuel.ELECTRICITY, Fuel.GAS} and len(rows) == 2


async def test_statements_pagination_single_page():
    resp = {"Statements": {"account": {"bills": {"pageInfo": {"hasNextPage": False}, "edges": [
        {"node": {"id": "410", "fromDate": "2026-03-30", "toDate": "2026-04-29",
                  "issuedDate": "2026-05-01", "closingBalance": 1234}}]}}}}
    rows = await _rows("statements", _account(), resp)
    assert len(rows) == 1 and rows[0].statement_id == "410" and rows[0].total_pennies == 1234
