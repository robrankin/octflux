from __future__ import annotations

import pytest
from fakes.clients import FakeGraphQl, FakeRest

from octflux.config.schema import (
    ApiConfig,
    CollectorConfig,
    Config,
    McpConfig,
    OctopusSettings,
    SinkConfig,
)
from octflux.core.engine import Engine

ACCOUNT = {
    "number": "A-1",
    "properties": [{
        "electricity_meter_points": [{
            "mpan": "1591016047308", "is_export": False,
            "meters": [{"serial_number": "23J"}],
            "agreements": [{"tariff_code": "E-1R-GO-VAR-22-10-14-F",
                            "valid_from": "2024-01-01T00:00:00Z", "valid_to": None}],
        }],
        "gas_meter_points": [],
    }],
}
META = {"account": {"properties": [{
    "postcode": "NE17 7AD",
    "electricityMeterPoints": [{"mpan": "1591016047308", "meters": [{"id": "10172874", "serialNumber": "23J"}]}],
    "gasMeterPoints": [],
}]}}
RATES = [{"valid_from": "2026-05-01T00:00:00Z", "valid_to": None, "value_exc_vat": 8.21, "value_inc_vat": 8.62}]
SC = [{"valid_from": "2026-05-01T00:00:00Z", "valid_to": None, "value_exc_vat": 40, "value_inc_vat": 42}]
CONS = [{"consumption": 0.1, "interval_start": "2026-05-01T00:00:00Z", "interval_end": "2026-05-01T00:30:00Z"}]
GQL = {
    "AccountMeta": META,
    "AccountBalance": {"account": {"balance": 0}},
    "AccountTransactions": {"account": {"transactions": {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "edges": [{"node": {"id": 1, "__typename": "Charge", "postedDate": "2026-04-27",
                            "createdAt": "2026-04-27T10:00:00Z", "amount": -100,
                            "balanceCarriedForward": 0, "isCredit": False, "title": "Electricity"}}],
    }}},
}


def _config(tmp_path) -> Config:
    return Config(
        octopus=OctopusSettings(api_key="x", account_number="A-1"),
        collectors={
            "tariffs": CollectorConfig(schedule="3600s"),
            "consumption": CollectorConfig(schedule="3600s"),
            "balance": CollectorConfig(schedule="3600s"),
        },
        sinks={"local": SinkConfig(driver="sqlite", options={"path": str(tmp_path / "t.db")})},
        api=ApiConfig(enabled=False),
        mcp=McpConfig(enabled=False),
    )


@pytest.mark.integration
async def test_engine_end_to_end(tmp_path):
    engine = Engine(_config(tmp_path))
    engine._rest = FakeRest(account=ACCOUNT, unit_rates=RATES, standing=SC, consumption=CONS)
    engine._graphql = FakeGraphQl(GQL)
    await engine.start(schedule=False, run_initial=False)
    try:
        await engine.run_collector("tariffs")
        await engine.run_collector("consumption")
        await engine.run_collector("balance")

        assert len(await engine.query("unit_rate", 10)) == 1
        assert len(await engine.query("standing_charge", 10)) == 1
        assert len(await engine.query("consumption", 10)) == 1
        assert len(await engine.query("account_balance", 10)) == 1
        assert len(await engine.query("ledger_transaction", 10)) == 1

        # idempotent: a second consumption run changes nothing
        summary = await engine.run_collector("consumption")
        assert summary["consumption"]["sinks"]["local"]["skipped"] == 1

        status = engine.status()
        names = {c["name"] for c in status["collectors"]}
        assert names == {"tariffs", "consumption", "balance"}
        assert all(c["last_ok"] for c in status["collectors"])
    finally:
        await engine.stop()
