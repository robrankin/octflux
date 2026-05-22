from __future__ import annotations

from datetime import UTC, datetime

from octflux.collectors.balance import parse_transactions
from octflux.collectors.carbon import parse_carbon
from octflux.collectors.consumption import parse_consumption
from octflux.collectors.dispatches import parse_dispatches
from octflux.collectors.meter_readings import parse_readings
from octflux.collectors.statements import parse_statements
from octflux.collectors.tariffs import parse_unit_rates
from octflux.core.models import Agreement, DispatchStatus, Fuel, Meter, MeterPoint


def _ag():
    return Agreement(Fuel.ELECTRICITY, "E-1R-GO-VAR-22-10-14-F", "GO-VAR-22-10-14",
                     datetime(2024, 1, 1, tzinfo=UTC), None, False)


def test_parse_unit_rates():
    rows = parse_unit_rates(
        [{"valid_from": "2026-05-01T00:00:00Z", "valid_to": None,
          "value_exc_vat": 8.21, "value_inc_vat": 8.62}],
        _ag(), is_export=False,
    )
    assert rows[0].product_code == "GO-VAR-22-10-14"
    assert rows[0].value_inc_vat == 8.62


def test_parse_consumption():
    mp = MeterPoint(Fuel.ELECTRICITY, "1591016047308", False, (Meter("23J", None),), ())
    rows = parse_consumption(
        [{"consumption": 0.123, "interval_start": "2026-05-01T00:00:00Z",
          "interval_end": "2026-05-01T00:30:00Z"}],
        mp, mp.meters[0],
    )
    assert rows[0].consumption == 0.123
    assert rows[0].fuel is Fuel.ELECTRICITY


def test_parse_transactions():
    rows = parse_transactions(
        [{"node": {"id": 7, "__typename": "Charge", "postedDate": "2026-04-27",
                   "createdAt": "2026-04-27T10:00:00Z", "amount": -5272,
                   "balanceCarriedForward": 100, "isCredit": False, "title": "Electricity"}}],
        "A-1",
    )
    assert rows[0].transaction_id == "7"
    assert rows[0].amount_pennies == -5272
    assert rows[0].transaction_type == "Charge"


def test_parse_dispatches_alt_fields():
    rows = parse_dispatches(
        [{"startDtUtc": "2026-05-01T11:00:00Z", "endDtUtc": "2026-05-01T12:00:00Z"}],
        "A-1", DispatchStatus.PLANNED,
    )
    assert rows[0].delta_kwh is None
    assert rows[0].source is None


def test_parse_carbon_closes_window_and_drops_open_period():
    rows = parse_carbon(
        [{"periodStart": "2026-05-01T01:00:00Z", "value": 120, "index": "moderate"},
         {"periodStart": "2026-05-01T00:00:00Z", "value": 90, "index": "low"}],
        "NE17 7AD",
    )
    # the still-open final period (01:00, no next) is dropped; only the closed one remains
    assert len(rows) == 1
    assert rows[0].valid_from == datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    assert rows[0].valid_to == datetime(2026, 5, 1, 1, 0, tzinfo=UTC)
    assert rows[0].intensity_gco2_kwh == 90.0


def test_parse_statements():
    rows = parse_statements(
        [{"node": {"id": "410", "fromDate": "2026-03-30", "toDate": "2026-04-29",
                   "issuedDate": "2026-05-01", "closingBalance": 1234}}],
        "A-1",
    )
    assert rows[0].statement_id == "410"
    assert rows[0].total_pennies == 1234


def test_parse_readings_per_register_skips_null():
    rows = parse_readings(
        [{"node": {"readAt": "2026-04-09T00:00:00Z", "readingType": "Smart meter reading",
                   "registers": [{"identifier": "1", "value": 1000.5},
                                 {"identifier": "2", "value": None}]}}],
        "A-1", "10172874", Fuel.ELECTRICITY,
    )
    assert len(rows) == 1  # null register dropped
    assert rows[0].register == "1"
    assert rows[0].value == 1000.5
