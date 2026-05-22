from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fakes.clients import FakeGraphQl, FakeRest

from octflux.account import parse_rest_account, product_code, resolve_account
from octflux.core.models import Fuel

REST = {"number": "A-1", "properties": [{
    "electricity_meter_points": [{
        "mpan": "159", "is_export": False, "meters": [{"serial_number": "23J"}],
        "agreements": [{"tariff_code": "E-1R-INTELLI-VAR-22-10-14-F",
                        "valid_from": "2024-01-01T00:00:00Z", "valid_to": None}],
    }],
    "gas_meter_points": [{"mprn": "G99", "meters": [{"serial_number": "G4F"}], "agreements": []}],
}]}
META = {"account": {"properties": [{
    "postcode": "NE17 7AD",
    "electricityMeterPoints": [{"mpan": "159", "meters": [{"id": "10172874", "serialNumber": "23J"}]}],
    "gasMeterPoints": [],
}]}}


def _settings():
    return SimpleNamespace(account_number="A-1", postcode=None)


def test_product_code():
    assert product_code("E-1R-GO-VAR-22-10-14-F") == "GO-VAR-22-10-14"
    assert product_code("not-a-tariff") == "not-a-tariff"


def test_parse_rest_account():
    a = parse_rest_account(REST)
    assert a.number == "A-1"
    elec = a.electricity[0]
    assert (elec.identifier, elec.fuel, elec.is_export) == ("159", Fuel.ELECTRICITY, False)
    assert elec.meters[0].serial_number == "23J" and elec.meters[0].meter_id is None
    assert a.gas[0].identifier == "G99"


def test_agreement_without_valid_from_does_not_crash_is_intelligent():
    # regression: missing valid_from used to fall back to a *naive* datetime.min and
    # raise TypeError when compared with the aware `when`.
    rest = {"number": "A-1", "properties": [{"electricity_meter_points": [{
        "mpan": "159", "is_export": False, "meters": [{"serial_number": "23J"}],
        "agreements": [{"tariff_code": "E-1R-INTELLI-VAR-22-10-14-F"}],
    }], "gas_meter_points": []}]}
    a = parse_rest_account(rest)
    assert a.is_intelligent(datetime(2026, 1, 1, tzinfo=UTC)) is True


@pytest.mark.integration
async def test_resolve_account_merges_meter_ids_and_postcode():
    acct = await resolve_account(FakeRest(account=REST), FakeGraphQl({"AccountMeta": META}), _settings())
    assert acct.postcode == "NE17 7AD"
    assert acct.electricity[0].meters[0].meter_id == "10172874"


@pytest.mark.integration
async def test_resolve_account_survives_graphql_failure():
    # FakeGraphQl with no matching response raises -> enrichment is best-effort, REST stands.
    acct = await resolve_account(FakeRest(account=REST), FakeGraphQl({}), _settings())
    assert acct.number == "A-1" and acct.postcode is None
    assert acct.electricity[0].meters[0].meter_id is None
